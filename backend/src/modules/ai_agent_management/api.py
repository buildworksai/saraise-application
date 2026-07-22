"""Governed API v2 boundary for the tenant-owned AI agent runtime."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import QuerySet
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated, NotFound, PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.access.entitlements import Quota
from src.core.access.permissions import RequiresAccess
from src.core.api import GovernedAPIViewMixin, OperationFailed
from src.core.async_jobs.models import AsyncJob
from src.core.auth_utils import get_user_tenant_id

from .authentication import GovernedSessionAuthentication
from .approval_models import ApprovalRequest, SoDPolicy, SoDViolation
from .audit_models import AuditEvent, AuditTrail
from .egress_models import EgressRequest, EgressRule, Secret, SecretAccess
from .models import Agent, AgentExecution, AgentSchedulerTask
from .quota_models import KillSwitch, QuotaUsage, ShardSaturation
from .serializers import (
    AgentCreateSerializer,
    AgentDetailSerializer,
    AgentExecutionDetailSerializer,
    AgentExecutionListSerializer,
    AgentListSerializer,
    AgentUpdateSerializer,
    ApprovalCreateSerializer,
    ApprovalDecisionSerializer,
    ApprovalRequestSerializer,
    AsyncJobSerializer,
    AuditEventSerializer,
    AuditTrailSerializer,
    CostRecalculationSerializer,
    CostRecordSerializer,
    CostSummarySerializer,
    EgressRequestSerializer,
    EgressRuleSerializer,
    EgressRuleWriteSerializer,
    EvaluationStartSerializer,
    ExecuteAgentSerializer,
    KillSwitchActivateSerializer,
    KillSwitchDeactivateSerializer,
    KillSwitchSerializer,
    QuotaSerializer,
    QuotaUsageSerializer,
    ScheduleCreateSerializer,
    ScheduleSerializer,
    SecretAccessSerializer,
    SecretCreateSerializer,
    SecretMetadataSerializer,
    SecretRotateSerializer,
    ShardSaturationSerializer,
    SoDPolicySerializer,
    SoDPolicyWriteSerializer,
    SoDViolationSerializer,
    TokenUsageSerializer,
    ToolInvocationSerializer,
    ToolSerializer,
    ToolValidationSerializer,
    ToolWriteSerializer,
    TransitionExecutionSerializer,
    TransitionKeySerializer,
)
from .services import (
    AGGREGATE_COST_COMMAND,
    AgentService,
    ApprovalService,
    EgressService,
    EvaluationService,
    ExecutionService,
    KillSwitchService,
    ScheduleService,
    SecretService,
    SoDService,
    ToolService,
    AgentServiceError,
)
from src.core.state_machine import IdempotencyConflictError, IllegalTransitionError
from .token_models import CostRecord, CostSummary, TokenUsage
from .tool_models import Tool, ToolInvocation


def _principal_id(user: object) -> UUID:
    """Return a stable UUID for the authenticated principal.

    Deployments with UUID user keys preserve that key.  Legacy Django integer
    users receive a deterministic namespace UUID, never a caller supplied ID.
    """

    raw = str(getattr(user, "pk", ""))
    try:
        return UUID(raw)
    except (ValueError, TypeError, AttributeError):
        if not raw:
            raise NotAuthenticated("An authenticated principal is required.")
        return uuid5(NAMESPACE_URL, f"saraise:user:{raw}")


class GovernedTenantViewSet(GovernedAPIViewMixin, viewsets.GenericViewSet):
    """Common deny-by-default access and tenant boundary."""

    authentication_classes = (GovernedSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    required_permission = ""
    required_entitlement = "ai_agent_management"
    quota_resource = "ai_agent_management.api"
    quota_cost = 1
    filter_backends = (SearchFilter, OrderingFilter)
    ordering = ("-created_at", "id")
    ordering_fields: tuple[str, ...] = ()
    search_fields: tuple[str, ...] = ()
    permission_map: Mapping[str, str] = {}

    def tenant_id(self) -> UUID:
        tenant = get_user_tenant_id(self.request.user)
        if not tenant:
            raise PermissionDenied("A tenant-scoped identity is required.")
        try:
            return UUID(str(tenant))
        except (ValueError, TypeError) as exc:
            raise PermissionDenied("The tenant identity is invalid.") from exc

    def actor_id(self) -> UUID:
        return _principal_id(self.request.user)

    def check_permissions(self, request: object) -> None:
        if not getattr(getattr(request, "user", None), "is_authenticated", False):
            raise NotAuthenticated("Authentication credentials were not provided.")
        setattr(request, "tenant_id", self.tenant_id())
        self.required_permission = self.permission_map.get(getattr(self, "action", ""), self.required_permission)
        self.required_entitlement = self.required_permission
        self.quota_resource = self.required_permission
        super().check_permissions(request)

    def handle_exception(self, exc: Exception) -> Response:
        # Tenant-filtered lookups deliberately collapse absent and foreign
        # identifiers to the same response so object existence cannot leak.
        if isinstance(exc, ObjectDoesNotExist):
            exc = NotFound("The requested resource was not found.")
        elif isinstance(exc, DjangoValidationError):
            detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or str(exc)
            exc = ValidationError(detail)
        elif isinstance(exc, (IllegalTransitionError, IdempotencyConflictError, IntegrityError)):
            exc = OperationFailed(
                error_code="STATE_CONFLICT",
                message="The requested change conflicts with the current resource state.",
                http_status=status.HTTP_409_CONFLICT,
            )
        elif isinstance(exc, AgentServiceError):
            unavailable = "UNAVAILABLE" in exc.code or exc.code.endswith("_REQUIRED")
            exc = OperationFailed(
                error_code=exc.code,
                message=str(exc),
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE if unavailable else status.HTTP_409_CONFLICT,
            )
        return super().handle_exception(exc)


class AgentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedTenantViewSet):
    queryset = Agent.objects.none()
    serializer_class = AgentDetailSerializer
    search_fields = ("name", "description")
    ordering_fields = ("name", "created_at", "updated_at")
    permission_map = {
        "list": "ai.agent:view", "retrieve": "ai.agent:view", "create": "ai.agent:create",
        "update": "ai.agent:update", "partial_update": "ai.agent:update", "destroy": "ai.agent:delete",
        "activate": "ai.agent:update", "disable": "ai.agent:update", "retire": "ai.agent:delete",
        "execute": "ai.agent:execute", "evaluate": "ai.evaluation:run",
    }

    def get_queryset(self) -> QuerySet[Agent]:
        filters = {key: self.request.query_params.get(key) for key in ("status", "identity_type", "runner_key", "subject_id")}
        filters["search"] = self.request.query_params.get("search")
        filters["ordering"] = self.request.query_params.get("ordering", "name")
        return AgentService.list_agents(self.tenant_id(), filters)

    def get_serializer_class(self):
        return AgentListSerializer if self.action == "list" else AgentDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = AgentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        agent = AgentService.create_agent(self.tenant_id(), self.actor_id(), serializer.validated_data)
        return Response(AgentDetailSerializer(agent).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        agent = self.get_object()
        serializer = AgentUpdateSerializer(data=request.data, partial=kwargs.get("partial", False), context={"agent": agent})
        serializer.is_valid(raise_exception=True)
        updated = AgentService.update_agent(self.tenant_id(), self.actor_id(), agent.id, serializer.validated_data)
        return Response(AgentDetailSerializer(updated).data)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        agent = self.get_object()
        retired = AgentService.retire_agent(self.tenant_id(), self.actor_id(), agent.id, "api_delete", f"retire:{agent.id}")
        return Response(AgentDetailSerializer(retired).data)

    def _transition(self, request, command: str) -> Response:
        agent = self.get_object()
        serializer = TransitionKeySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if command == "activate":
            value = AgentService.activate_agent(self.tenant_id(), self.actor_id(), agent.id, values["transition_key"])
        elif command == "disable":
            value = AgentService.disable_agent(self.tenant_id(), self.actor_id(), agent.id, values["reason"], values["transition_key"])
        else:
            value = AgentService.retire_agent(self.tenant_id(), self.actor_id(), agent.id, values["reason"], values["transition_key"])
        return Response(AgentDetailSerializer(value).data)

    @action(detail=True, methods=("post",))
    def activate(self, request, pk=None): return self._transition(request, "activate")

    @action(detail=True, methods=("post",))
    def disable(self, request, pk=None): return self._transition(request, "disable")

    @action(detail=True, methods=("post",))
    def retire(self, request, pk=None): return self._transition(request, "retire")

    @action(detail=True, methods=("post",))
    def execute(self, request, pk=None):
        agent = self.get_object()
        serializer = ExecuteAgentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        result = ExecutionService.execute(self.tenant_id(), self.actor_id(), agent.id, values["task"], values["idempotency_key"], values.get("schedule_at"))
        execution = result.unwrap()
        return Response(AgentExecutionDetailSerializer(execution).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=("post",))
    def evaluate(self, request, pk=None):
        agent = self.get_object()
        serializer = EvaluationStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        method = EvaluationService.start_red_team if values["red_team"] else EvaluationService.start_evaluation
        job = method(self.tenant_id(), self.actor_id(), agent.id, values["suite_key"], values["idempotency_key"]).unwrap()
        return Response(AsyncJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class AgentExecutionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedTenantViewSet):
    queryset = AgentExecution.objects.none()
    serializer_class = AgentExecutionDetailSerializer
    ordering_fields = ("created_at", "started_at", "completed_at")
    permission_map = {"list": "ai.execution:view", "retrieve": "ai.execution:view", "pause": "ai.agent:pause", "resume": "ai.agent:resume", "terminate": "ai.agent:terminate"}

    def get_queryset(self):
        return ExecutionService.list_executions(self.tenant_id(), self.request.query_params)

    def get_serializer_class(self):
        return AgentExecutionListSerializer if self.action == "list" else AgentExecutionDetailSerializer

    def _transition(self, request, command: str):
        execution = self.get_object()
        serializer = TransitionExecutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        method = {"pause": ExecutionService.pause, "resume": ExecutionService.resume, "terminate": ExecutionService.terminate}[command]
        supplied_agent_id = values.get("agent_id")
        if supplied_agent_id is not None and supplied_agent_id != execution.agent_id:
            raise NotFound("The requested execution was not found for that agent.")
        args = (self.tenant_id(), self.actor_id(), execution.agent_id, execution.id)
        value = method(*args, values.get("reason", ""), values["transition_key"]) if command == "terminate" else method(*args, values["transition_key"])
        return Response(AgentExecutionDetailSerializer(value).data)

    @action(detail=True, methods=("post",))
    def pause(self, request, pk=None): return self._transition(request, "pause")

    @action(detail=True, methods=("post",))
    def resume(self, request, pk=None): return self._transition(request, "resume")

    @action(detail=True, methods=("post",))
    def terminate(self, request, pk=None): return self._transition(request, "terminate")


class ScheduleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedTenantViewSet):
    serializer_class = ScheduleSerializer
    queryset = AgentSchedulerTask.objects.none()
    ordering_fields = ("priority", "scheduled_at")
    permission_map = {"list": "ai.execution:view", "retrieve": "ai.execution:view", "create": "ai.schedule:manage", "cancel": "ai.schedule:manage"}

    def get_queryset(self): return ScheduleService.list_schedules(self.tenant_id(), self.request.query_params)

    def create(self, request, *args, **kwargs):
        serializer = ScheduleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data); agent_id = values.pop("agent_id")
        value = ScheduleService.create_schedule(self.tenant_id(), self.actor_id(), agent_id, values)
        return Response(ScheduleSerializer(value).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("post",))
    def cancel(self, request, pk=None):
        schedule = self.get_object(); serializer = TransitionKeySerializer(data=request.data); serializer.is_valid(raise_exception=True)
        value = ScheduleService.cancel_schedule(self.tenant_id(), self.actor_id(), schedule.id, serializer.validated_data["transition_key"])
        return Response(ScheduleSerializer(value).data)


class ApprovalRequestViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedTenantViewSet):
    serializer_class = ApprovalRequestSerializer; queryset = ApprovalRequest.objects.none()
    permission_map = {"list": "ai.approval:view", "retrieve": "ai.approval:view", "create": "ai.approval:request", "approve": "ai.approval:decide", "reject": "ai.approval:decide", "cancel": "ai.approval:request"}
    def get_queryset(self): return ApprovalService.list_requests(self.tenant_id(), self.request.query_params)
    def create(self, request, *args, **kwargs):
        serializer = ApprovalCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True); values = dict(serializer.validated_data)
        execution_id, invocation_id = values.pop("execution_id"), values.pop("invocation_id", None)
        value = ApprovalService.create_request(self.tenant_id(), self.actor_id(), execution_id, invocation_id, values)
        return Response(ApprovalRequestSerializer(value).data, status=status.HTTP_201_CREATED)
    def _decision(self, request, command):
        approval = self.get_object(); serializer = ApprovalDecisionSerializer(data=request.data); serializer.is_valid(raise_exception=True); values = serializer.validated_data
        if command == "approve": value = ApprovalService.approve(self.tenant_id(), self.actor_id(), approval.id, values["transition_key"])
        elif command == "reject": value = ApprovalService.reject(self.tenant_id(), self.actor_id(), approval.id, values["reason"], values["transition_key"])
        else: value = ApprovalService.cancel(self.tenant_id(), self.actor_id(), approval.id, values["transition_key"])
        return Response(ApprovalRequestSerializer(value).data)
    @action(detail=True, methods=("post",))
    def approve(self, request, pk=None): return self._decision(request, "approve")
    @action(detail=True, methods=("post",))
    def reject(self, request, pk=None): return self._decision(request, "reject")
    @action(detail=True, methods=("post",))
    def cancel(self, request, pk=None): return self._decision(request, "cancel")


class ServiceCrudViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedTenantViewSet):
    """CRUD adapter whose concrete methods always delegate to a service."""
    service = None; write_serializer_class = None
    def create(self, request, *args, **kwargs): return self._write(request, False)
    def update(self, request, *args, **kwargs): return self._write(request, True)
    def partial_update(self, request, *args, **kwargs): return self._write(request, True, partial=True)
    def _write(self, request, updating, partial=False): raise NotImplementedError


class SoDPolicyViewSet(ServiceCrudViewSet):
    queryset = SoDPolicy.objects.none(); serializer_class = SoDPolicySerializer; write_serializer_class = SoDPolicyWriteSerializer
    permission_map = {"list": "ai.governance:view", "retrieve": "ai.governance:view", "create": "ai.governance:manage", "update": "ai.governance:manage", "partial_update": "ai.governance:manage", "destroy": "ai.governance:manage"}
    def get_queryset(self): return SoDService.list_policies(self.tenant_id(), self.request.query_params)
    def _write(self, request, updating, partial=False):
        obj = self.get_object() if updating else None; serializer = SoDPolicyWriteSerializer(data=request.data, partial=partial); serializer.is_valid(raise_exception=True)
        value = SoDService.update_policy(self.tenant_id(), self.actor_id(), obj.id, serializer.validated_data) if obj else SoDService.create_policy(self.tenant_id(), self.actor_id(), serializer.validated_data)
        return Response(SoDPolicySerializer(value).data, status=status.HTTP_200_OK if obj else status.HTTP_201_CREATED)
    def destroy(self, request, *args, **kwargs): return Response(SoDPolicySerializer(SoDService.deactivate_policy(self.tenant_id(), self.actor_id(), self.get_object().id)).data)


class ToolViewSet(ServiceCrudViewSet):
    queryset = Tool.objects.none(); serializer_class = ToolSerializer; search_fields = ("name", "description"); ordering_fields = ("name", "registered_at")
    permission_map = {"list": "ai.tool:view", "retrieve": "ai.tool:view", "create": "ai.tool:register", "update": "ai.tool:update", "partial_update": "ai.tool:update", "destroy": "ai.tool:delete", "validate": "ai.tool:invoke"}
    def get_queryset(self): return ToolService.list_tools(self.tenant_id(), self.request.query_params)
    def _write(self, request, updating, partial=False):
        obj = self.get_object() if updating else None; serializer = ToolWriteSerializer(data=request.data, partial=partial); serializer.is_valid(raise_exception=True)
        value = ToolService.update_tool(self.tenant_id(), self.actor_id(), obj.id, serializer.validated_data) if obj else ToolService.register_tool(self.tenant_id(), self.actor_id(), serializer.validated_data)
        return Response(ToolSerializer(value).data, status=status.HTTP_200_OK if obj else status.HTTP_201_CREATED)
    def destroy(self, request, *args, **kwargs): return Response(ToolSerializer(ToolService.deactivate_tool(self.tenant_id(), self.actor_id(), self.get_object().id)).data)
    @action(detail=True, methods=("post",))
    def validate(self, request, pk=None):
        tool = self.get_object(); serializer = ToolValidationSerializer(data=request.data); serializer.is_valid(raise_exception=True); values = serializer.validated_data
        method = ToolService.validate_input if values["direction"] == "input" else ToolService.validate_output; method(self.tenant_id(), tool.id, values["value"])
        return Response({"valid": True, "direction": values["direction"], "issues": []})


class EgressRuleViewSet(ServiceCrudViewSet):
    queryset = EgressRule.objects.none(); serializer_class = EgressRuleSerializer
    permission_map = {"list": "ai.governance:view", "retrieve": "ai.governance:view", "create": "ai.governance:manage", "update": "ai.governance:manage", "partial_update": "ai.governance:manage", "destroy": "ai.governance:manage"}
    def get_queryset(self): return EgressService.list_rules(self.tenant_id(), self.request.query_params)
    def _write(self, request, updating, partial=False):
        obj = self.get_object() if updating else None; serializer = EgressRuleWriteSerializer(data=request.data, partial=partial); serializer.is_valid(raise_exception=True)
        value = EgressService.update_rule(self.tenant_id(), self.actor_id(), obj.id, serializer.validated_data) if obj else EgressService.create_rule(self.tenant_id(), self.actor_id(), serializer.validated_data)
        return Response(EgressRuleSerializer(value).data, status=status.HTTP_200_OK if obj else status.HTTP_201_CREATED)
    def destroy(self, request, *args, **kwargs): return Response(EgressRuleSerializer(EgressService.deactivate_rule(self.tenant_id(), self.actor_id(), self.get_object().id)).data)


class SecretViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedTenantViewSet):
    queryset = Secret.objects.none(); serializer_class = SecretMetadataSerializer
    permission_map = {"list": "ai.secret:view", "retrieve": "ai.secret:view", "create": "ai.secret:manage", "rotate": "ai.secret:manage", "deactivate": "ai.secret:manage"}
    def get_queryset(self): return SecretService.list_metadata(self.tenant_id(), self.request.query_params)
    def create(self, request, *args, **kwargs):
        serializer = SecretCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True); value = SecretService.create_secret(self.tenant_id(), self.actor_id(), serializer.validated_data)
        return Response(SecretMetadataSerializer(value).data, status=status.HTTP_201_CREATED)
    @action(detail=True, methods=("post",))
    def rotate(self, request, pk=None):
        secret = self.get_object(); serializer = SecretRotateSerializer(data=request.data); serializer.is_valid(raise_exception=True); value = SecretService.rotate_secret(self.tenant_id(), self.actor_id(), secret.id, serializer.validated_data["plaintext"]); return Response(SecretMetadataSerializer(value).data)
    @action(detail=True, methods=("post",))
    def deactivate(self, request, pk=None): return Response(SecretMetadataSerializer(SecretService.deactivate_secret(self.tenant_id(), self.actor_id(), self.get_object().id)).data)


class KillSwitchViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedTenantViewSet):
    queryset = KillSwitch.objects.none(); serializer_class = KillSwitchSerializer
    permission_map = {"list": "ai.governance:view", "retrieve": "ai.governance:view", "create": "ai.governance:manage", "deactivate": "ai.governance:manage"}
    def get_queryset(self): return KillSwitch.objects.filter(tenant_id=self.tenant_id()).order_by("-created_at", "id")
    def create(self, request, *args, **kwargs):
        serializer = KillSwitchActivateSerializer(data=request.data); serializer.is_valid(raise_exception=True); values = serializer.validated_data
        value = KillSwitchService.activate(self.tenant_id(), self.actor_id(), values["scope"], values.get("scope_id"), values["reason"], values["transition_key"]); return Response(KillSwitchSerializer(value).data, status=status.HTTP_201_CREATED)
    @action(detail=True, methods=("post",))
    def deactivate(self, request, pk=None):
        switch = self.get_object(); serializer = KillSwitchDeactivateSerializer(data=request.data); serializer.is_valid(raise_exception=True); values = serializer.validated_data
        value = KillSwitchService.deactivate(self.tenant_id(), self.actor_id(), switch.id, values["reason"], values["transition_key"]); return Response(KillSwitchSerializer(value).data)


class TenantReadOnlyViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GovernedTenantViewSet):
    # Each evidence model has its own canonical event timestamp.  Preserve the
    # explicit queryset ordering below instead of applying the mutable-model
    # default (``created_at``), which append-only projections need not have.
    ordering = ()
    permission_map = {"list": "ai.governance:view", "retrieve": "ai.governance:view"}
    def get_queryset(self):
        model = self.queryset.model
        names = {field.name for field in model._meta.fields}
        timestamp = next(
            (name for name in ("created_at", "requested_at", "invoked_at", "event_timestamp", "cost_timestamp", "usage_timestamp", "measured_at", "accessed_at", "violation_at") if name in names),
            None,
        )
        ordering = (f"-{timestamp}", "id") if timestamp else ("id",)
        return model.objects.filter(tenant_id=self.tenant_id()).order_by(*ordering)


class SoDViolationViewSet(TenantReadOnlyViewSet): queryset = SoDViolation.objects.none(); serializer_class = SoDViolationSerializer
class ToolInvocationViewSet(TenantReadOnlyViewSet): queryset = ToolInvocation.objects.none(); serializer_class = ToolInvocationSerializer
class EgressRequestViewSet(TenantReadOnlyViewSet): queryset = EgressRequest.objects.none(); serializer_class = EgressRequestSerializer
class SecretAccessViewSet(TenantReadOnlyViewSet): queryset = SecretAccess.objects.none(); serializer_class = SecretAccessSerializer
class QuotaUsageViewSet(TenantReadOnlyViewSet): queryset = QuotaUsage.objects.none(); serializer_class = QuotaUsageSerializer; permission_map = {"list": "ai.usage:view", "retrieve": "ai.usage:view"}
class ShardSaturationViewSet(TenantReadOnlyViewSet): queryset = ShardSaturation.objects.none(); serializer_class = ShardSaturationSerializer; permission_map = {"list": "ai.usage:view", "retrieve": "ai.usage:view"}
class TokenUsageViewSet(TenantReadOnlyViewSet): queryset = TokenUsage.objects.none(); serializer_class = TokenUsageSerializer; permission_map = {"list": "ai.usage:view", "retrieve": "ai.usage:view"}
class CostRecordViewSet(TenantReadOnlyViewSet): queryset = CostRecord.objects.none(); serializer_class = CostRecordSerializer; permission_map = {"list": "ai.usage:view", "retrieve": "ai.usage:view"}
class AuditEventViewSet(TenantReadOnlyViewSet): queryset = AuditEvent.objects.none(); serializer_class = AuditEventSerializer; permission_map = {"list": "ai.audit:view", "retrieve": "ai.audit:view"}
class AuditTrailViewSet(TenantReadOnlyViewSet): queryset = AuditTrail.objects.none(); serializer_class = AuditTrailSerializer; permission_map = {"list": "ai.audit:view", "retrieve": "ai.audit:view"}


class QuotaViewSet(TenantReadOnlyViewSet):
    queryset = Quota.objects.none(); serializer_class = QuotaSerializer; permission_map = {"list": "ai.usage:view", "retrieve": "ai.usage:view"}


class CostSummaryViewSet(TenantReadOnlyViewSet):
    queryset = CostSummary.objects.none(); serializer_class = CostSummarySerializer; permission_map = {"list": "ai.usage:view", "retrieve": "ai.usage:view", "recalculate": "ai.usage:view"}
    @action(detail=False, methods=("post",))
    def recalculate(self, request):
        serializer = CostRecalculationSerializer(data=request.data); serializer.is_valid(raise_exception=True); values = serializer.validated_data
        from src.core.async_jobs.services import enqueue
        job = enqueue(self.tenant_id(), self.actor_id(), AGGREGATE_COST_COMMAND, {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in values.items() if key != "idempotency_key"}, values["idempotency_key"])
        return Response(AsyncJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class AsyncJobViewSet(TenantReadOnlyViewSet):
    queryset = AsyncJob.objects.none(); serializer_class = AsyncJobSerializer; permission_map = {"list": "ai.execution:view", "retrieve": "ai.execution:view"}
    def get_queryset(self): return AsyncJob.objects.filter(tenant_id=self.tenant_id(), command__startswith="ai_agent_management.").order_by("-created_at", "id")


# Compatibility names kept importable; both now project core access quotas.
AgentSchedulerTaskViewSet = ScheduleViewSet
TenantQuotaViewSet = QuotaViewSet
