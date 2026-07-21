"""Governed API v2 controllers for technical DAG orchestration.

Controllers perform request adaptation only.  Ownership, graph invariants,
state transitions, idempotency and durable queuing remain service concerns.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any, TypeVar

from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db.models import Case, Count, ExpressionWrapper, F, FloatField, Max, Q, Value, When
from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.access.permissions import RequiresAccess
from src.core.api.profile import GovernedAPIViewMixin
from src.core.api.results import CapabilityUnavailable, OperationFailed

from .health import sanitized_health_payload
from .models import (
    OrchestrationDefinition,
    OrchestrationEdge,
    OrchestrationEvent,
    OrchestrationNode,
    OrchestrationRun,
    OrchestrationSchedule,
    OrchestrationTaskRun,
)
from .node_registry import list_node_catalog
from .permissions import (
    CATALOG_VIEW,
    DEFINITION_MANAGE,
    DEFINITION_PUBLISH,
    DEFINITION_VIEW,
    RUN_CONTROL,
    RUN_EXECUTE,
    RUN_RETRY,
    RUN_VIEW,
    SCHEDULE_MANAGE,
    SCHEDULE_VIEW,
    AccessRequirement,
    read_access,
    write_access,
)
from .serializers import (
    DefinitionCreateSerializer,
    DefinitionDetailSerializer,
    DefinitionListSerializer,
    DefinitionUpdateSerializer,
    EdgeCreateSerializer,
    EdgeSerializer,
    EdgeUpdateSerializer,
    GraphValidationSerializer,
    NodeCreateSerializer,
    NodeDescriptorSerializer,
    NodeDetailSerializer,
    NodeListSerializer,
    NodeUpdateSerializer,
    OrchestrationEventSerializer,
    RunControlSerializer,
    RunDetailSerializer,
    RunListSerializer,
    RunRetrySerializer,
    RunStartSerializer,
    ScheduleCreateSerializer,
    ScheduleDetailSerializer,
    ScheduleListSerializer,
    ScheduleUpdateSerializer,
    TaskRetrySerializer,
    TaskRunDetailSerializer,
    TaskRunListSerializer,
)
from .services import (
    DefinitionService,
    ExecutionService,
    IdempotencyConflictError,
    OrchestrationServiceError,
    ScheduleService,
    StateConflictError,
)

T = TypeVar("T")


def _service_call(operation: Callable[[], T]) -> T:
    """Normalize domain validation without disclosing implementation errors."""

    try:
        return operation()
    except ObjectDoesNotExist as exc:
        raise NotFound("The requested resource was not found") from exc
    except (StateConflictError, IdempotencyConflictError) as exc:
        raise OperationFailed(
            error_code=exc.code,
            message=str(exc),
            http_status=status.HTTP_409_CONFLICT,
        ) from exc
    except DjangoValidationError as exc:
        detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or ["Request is invalid"]
        raise ValidationError(detail) from exc
    except (ValueError, TypeError) as exc:
        raise ValidationError({"non_field_errors": [str(exc)]}) from exc
    except OrchestrationServiceError as exc:
        raise OperationFailed(error_code=exc.code, message=str(exc)) from exc


def _as_uuid(value: object, field_name: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValidationError({field_name: ["Must be a valid UUID"]}) from exc


def _actor_id(request: Request) -> uuid.UUID:
    """Represent legacy integer user IDs in the UUID audit namespace."""

    raw = getattr(request.user, "id", None)
    if raw is None:
        raise PermissionDenied("Authenticated identity is incomplete")
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{raw}")


def _tenant_from_request(request: Request) -> uuid.UUID:
    raw = getattr(request, "tenant_id", None)
    if raw is None:
        profile = getattr(request.user, "profile", None)
        raw = getattr(profile, "tenant_id", None)
    if raw is None:
        raise PermissionDenied("A tenant context is required")
    return _as_uuid(raw, "tenant_id")


class RequiredSessionAuthentication(SessionAuthentication):
    """Use Django sessions while preserving the v2 unauthenticated 401 contract."""

    def authenticate_header(self, request: Request) -> str:
        del request
        return "Session"


class GovernedTenantViewSet(GovernedAPIViewMixin, viewsets.GenericViewSet[Any]):
    """Shared session, tenant, access and filtering behavior."""

    authentication_classes = (RequiredSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    access_by_action: dict[str, AccessRequirement] = {}

    def get_access_requirement(self) -> AccessRequirement | None:
        return self.access_by_action.get(getattr(self, "action", ""))

    def get_permissions(self) -> list[object]:
        # AccessDecisionPipeline consumes request.tenant_id.  The canonical
        # profile is the same identity source used by TenantContextMiddleware.
        try:
            self.request.tenant_id = _tenant_from_request(self.request)
        except PermissionDenied:
            pass
        requirement = self.get_access_requirement()
        if requirement is None:
            self.required_permission = None
            self.required_entitlement = None
            self.quota_resource = None
            self.quota_cost = 0
        else:
            self.required_permission = requirement.permission
            self.required_entitlement = requirement.entitlement
            self.quota_resource = requirement.quota_resource
            self.quota_cost = requirement.quota_cost
        return super().get_permissions()

    @property
    def tenant_id(self) -> uuid.UUID:
        return _tenant_from_request(self.request)

    @property
    def actor_id(self) -> uuid.UUID:
        return _actor_id(self.request)

    @staticmethod
    def _ordered(queryset: Any, request: Request, allowed: dict[str, str], default: str) -> Any:
        requested = request.query_params.get("ordering", default)
        descending = requested.startswith("-")
        key = requested[1:] if descending else requested
        field = allowed.get(key, allowed[default.lstrip("-")])
        return queryset.order_by(f"-{field}" if descending else field)

    def _paginate(self, queryset: Any, serializer_class: type, *, context: dict[str, object] | None = None) -> Response:
        page = self.paginate_queryset(queryset)
        serializer = serializer_class(page if page is not None else queryset, many=True, context=context or {})
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class DefinitionViewSet(GovernedTenantViewSet):
    service = DefinitionService()
    access_by_action = {
        "list": read_access(DEFINITION_VIEW),
        "retrieve": read_access(DEFINITION_VIEW),
        "create": write_access(DEFINITION_MANAGE),
        "partial_update": write_access(DEFINITION_MANAGE),
        "destroy": write_access(DEFINITION_MANAGE),
        "validate_graph": write_access(DEFINITION_MANAGE),
        "publish": write_access(DEFINITION_PUBLISH),
        "clone": write_access(DEFINITION_MANAGE),
        "retire": write_access(DEFINITION_PUBLISH),
        "nodes": read_access(DEFINITION_VIEW),
        "edges": read_access(DEFINITION_VIEW),
        "snapshot": read_access(DEFINITION_VIEW),
    }

    def get_access_requirement(self) -> AccessRequirement | None:
        if getattr(self, "action", "") in {"nodes", "edges"} and self.request.method == "POST":
            return write_access(DEFINITION_MANAGE)
        return super().get_access_requirement()

    def get_queryset(self):
        queryset = OrchestrationDefinition.objects.for_tenant(self.tenant_id).filter(is_deleted=False)
        if self.action == "list":
            queryset = queryset.annotate(
                node_count=Count("nodes", filter=Q(nodes__is_deleted=False), distinct=True),
                schedule_count=Count("schedules", filter=Q(schedules__is_deleted=False), distinct=True),
                last_run_at=Max("runs__created_at"),
                terminal_run_count=Count(
                    "runs", filter=Q(runs__status__in=("succeeded", "failed", "cancelled")), distinct=True
                ),
                succeeded_run_count=Count("runs", filter=Q(runs__status="succeeded"), distinct=True),
            ).annotate(
                success_rate=Case(
                    When(terminal_run_count=0, then=Value(None)),
                    default=ExpressionWrapper(
                        100.0 * F("succeeded_run_count") / F("terminal_run_count"), output_field=FloatField()
                    ),
                    output_field=FloatField(),
                )
            )
        return queryset

    def list(self, request: Request) -> Response:
        queryset = self.get_queryset()
        if status_value := request.query_params.get("status"):
            queryset = queryset.filter(status=status_value)
        if key := request.query_params.get("key"):
            queryset = queryset.filter(key=key)
        if (current := request.query_params.get("is_current")) is not None:
            if current.lower() not in {"true", "false"}:
                raise ValidationError({"is_current": ["Use true or false"]})
            queryset = queryset.filter(is_current=current.lower() == "true")
        if search := request.query_params.get("search"):
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(key__icontains=search) | Q(description__icontains=search)
            )
        queryset = self._ordered(
            queryset,
            request,
            {"updated_at": "updated_at", "name": "name", "version": "version"},
            "-updated_at",
        )
        return self._paginate(queryset, DefinitionListSerializer)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        definition = self.get_object()
        return Response(DefinitionDetailSerializer(definition).data)

    def create(self, request: Request) -> Response:
        serializer = DefinitionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        definition = _service_call(
            lambda: self.service.create_definition(self.tenant_id, self.actor_id, dict(serializer.validated_data))
        )
        return Response(DefinitionDetailSerializer(definition).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        current = self.get_object()
        serializer = DefinitionUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changes = dict(serializer.validated_data)
        transition_key = str(changes.pop("transition_key", "update_draft"))
        expected_revision = changes.pop("expected_revision", None)
        if expected_revision is not None and expected_revision != current.graph_revision:
            raise OperationFailed(
                error_code="GRAPH_REVISION_CONFLICT",
                message="The graph changed after it was loaded. Refresh and reconcile your edits.",
                detail={"current_revision": current.graph_revision},
                http_status=status.HTTP_409_CONFLICT,
            )
        definition = _service_call(
            lambda: self.service.update_draft(
                self.tenant_id, _as_uuid(pk, "id"), self.actor_id, changes, transition_key
            )
        )
        return Response(DefinitionDetailSerializer(definition).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        _service_call(lambda: self.service.delete_draft(self.tenant_id, _as_uuid(pk, "id"), self.actor_id))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",), url_path="validate")
    def validate_graph(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        result = _service_call(lambda: self.service.validate_graph(self.tenant_id, _as_uuid(pk, "id")))
        return Response(GraphValidationSerializer(result).data)

    @action(detail=True, methods=("post",))
    def publish(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        control = RunControlSerializer(data=request.data)
        control.is_valid(raise_exception=True)
        definition = _service_call(
            lambda: self.service.publish(
                self.tenant_id, _as_uuid(pk, "id"), self.actor_id, control.validated_data["transition_key"]
            )
        )
        return Response(DefinitionDetailSerializer(definition).data)

    @action(detail=True, methods=("post",), url_path="clone")
    def clone(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        definition = _service_call(
            lambda: self.service.clone_version(self.tenant_id, _as_uuid(pk, "id"), self.actor_id)
        )
        return Response(DefinitionDetailSerializer(definition).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("post",))
    def retire(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        control = RunControlSerializer(data=request.data)
        control.is_valid(raise_exception=True)
        definition = _service_call(
            lambda: self.service.retire(
                self.tenant_id, _as_uuid(pk, "id"), self.actor_id, control.validated_data["transition_key"]
            )
        )
        return Response(DefinitionDetailSerializer(definition).data)

    @action(detail=True, methods=("get", "post"))
    def nodes(self, request: Request, pk: str | None = None) -> Response:
        definition = self.get_object()
        if request.method == "GET":
            queryset = (
                OrchestrationNode.objects.for_tenant(self.tenant_id)
                .filter(definition=definition, is_deleted=False)
                .order_by("-priority", "key")
            )
            return self._paginate(queryset, NodeListSerializer)
        serializer = NodeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        node = _service_call(
            lambda: self.service.add_node(self.tenant_id, definition.id, self.actor_id, dict(serializer.validated_data))
        )
        return Response(NodeDetailSerializer(node).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("get", "post"))
    def edges(self, request: Request, pk: str | None = None) -> Response:
        definition = self.get_object()
        if request.method == "GET":
            queryset = (
                OrchestrationEdge.objects.for_tenant(self.tenant_id)
                .filter(definition=definition, is_deleted=False)
                .order_by("-priority", "created_at")
            )
            return self._paginate(queryset, EdgeSerializer)
        serializer = EdgeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        edge = _service_call(
            lambda: self.service.add_edge(self.tenant_id, definition.id, self.actor_id, dict(serializer.validated_data))
        )
        return Response(EdgeSerializer(edge).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("get",))
    def snapshot(self, request: Request, pk: str | None = None) -> Response:
        definition = self.get_object()
        response = Response(DefinitionDetailSerializer(definition).data)
        response["ETag"] = f'"graph-{definition.graph_revision}"'
        return response


class NodeViewSet(GovernedTenantViewSet):
    service = DefinitionService()
    access_by_action = {
        "retrieve": read_access(DEFINITION_VIEW),
        "partial_update": write_access(DEFINITION_MANAGE),
        "destroy": write_access(DEFINITION_MANAGE),
    }

    def get_queryset(self):
        return OrchestrationNode.objects.for_tenant(self.tenant_id).filter(is_deleted=False)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(NodeDetailSerializer(self.get_object()).data)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = NodeUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        node = _service_call(
            lambda: self.service.update_node(
                self.tenant_id, _as_uuid(pk, "id"), self.actor_id, dict(serializer.validated_data)
            )
        )
        return Response(NodeDetailSerializer(node).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        _service_call(lambda: self.service.remove_node(self.tenant_id, _as_uuid(pk, "id"), self.actor_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class EdgeViewSet(GovernedTenantViewSet):
    service = DefinitionService()
    access_by_action = {
        "retrieve": read_access(DEFINITION_VIEW),
        "partial_update": write_access(DEFINITION_MANAGE),
        "destroy": write_access(DEFINITION_MANAGE),
    }

    def get_queryset(self):
        return OrchestrationEdge.objects.for_tenant(self.tenant_id).filter(is_deleted=False)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(EdgeSerializer(self.get_object()).data)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = EdgeUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        edge = _service_call(
            lambda: self.service.update_edge(
                self.tenant_id, _as_uuid(pk, "id"), self.actor_id, dict(serializer.validated_data)
            )
        )
        return Response(EdgeSerializer(edge).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        _service_call(lambda: self.service.remove_edge(self.tenant_id, _as_uuid(pk, "id"), self.actor_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class ScheduleViewSet(GovernedTenantViewSet):
    service = ScheduleService()
    access_by_action = {
        "list": read_access(SCHEDULE_VIEW),
        "retrieve": read_access(SCHEDULE_VIEW),
        "create": write_access(SCHEDULE_MANAGE),
        "partial_update": write_access(SCHEDULE_MANAGE),
        "destroy": write_access(SCHEDULE_MANAGE),
        "pause": write_access(SCHEDULE_MANAGE),
        "resume": write_access(SCHEDULE_MANAGE),
        "retire": write_access(SCHEDULE_MANAGE),
    }

    def get_queryset(self):
        return (
            OrchestrationSchedule.objects.for_tenant(self.tenant_id)
            .filter(is_deleted=False)
            .select_related("definition")
        )

    def list(self, request: Request) -> Response:
        queryset = self.get_queryset()
        if value := request.query_params.get("status"):
            queryset = queryset.filter(status=value)
        if value := request.query_params.get("definition_id"):
            queryset = queryset.filter(definition_id=_as_uuid(value, "definition_id"))
        if value := request.query_params.get("due_before"):
            parsed = parse_datetime(value)
            if parsed is None:
                raise ValidationError({"due_before": ["Use an ISO-8601 date-time"]})
            queryset = queryset.filter(next_run_at__lte=parsed)
        if value := request.query_params.get("search"):
            queryset = queryset.filter(name__icontains=value)
        queryset = self._ordered(queryset, request, {"next_run_at": "next_run_at", "name": "name"}, "next_run_at")
        return self._paginate(queryset, ScheduleListSerializer)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(ScheduleDetailSerializer(self.get_object()).data)

    def create(self, request: Request) -> Response:
        serializer = ScheduleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        schedule = _service_call(
            lambda: self.service.create_schedule(self.tenant_id, self.actor_id, dict(serializer.validated_data))
        )
        return Response(ScheduleDetailSerializer(schedule).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = ScheduleUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changes = dict(serializer.validated_data)
        changes.pop("transition_key", None)
        schedule = _service_call(
            lambda: self.service.update_schedule(self.tenant_id, _as_uuid(pk, "id"), self.actor_id, changes)
        )
        return Response(ScheduleDetailSerializer(schedule).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        _service_call(lambda: self.service.delete_schedule(self.tenant_id, _as_uuid(pk, "id"), self.actor_id))
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _transition(
        self, request: Request, pk: str | None, operation: Callable[..., OrchestrationSchedule]
    ) -> Response:
        self.get_object()
        serializer = RunControlSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        schedule = _service_call(
            lambda: operation(
                self.tenant_id, _as_uuid(pk, "id"), self.actor_id, serializer.validated_data["transition_key"]
            )
        )
        return Response(ScheduleDetailSerializer(schedule).data)

    @action(detail=True, methods=("post",))
    def pause(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, pk, self.service.pause_schedule)

    @action(detail=True, methods=("post",))
    def resume(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, pk, self.service.resume_schedule)

    @action(detail=True, methods=("post",))
    def retire(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, pk, self.service.retire_schedule)


class RunViewSet(GovernedTenantViewSet):
    service = ExecutionService()
    access_by_action = {
        "list": read_access(RUN_VIEW),
        "retrieve": read_access(RUN_VIEW),
        "create": write_access(RUN_EXECUTE, cost=1),
        "pause": write_access(RUN_CONTROL),
        "resume": write_access(RUN_CONTROL),
        "cancel": write_access(RUN_CONTROL),
        "retry": write_access(RUN_RETRY, cost=1),
        "task_runs": read_access(RUN_VIEW),
        "events": read_access(RUN_VIEW),
    }

    def get_queryset(self):
        return OrchestrationRun.objects.for_tenant(self.tenant_id).select_related(
            "definition", "schedule", "parent_run"
        )

    def list(self, request: Request) -> Response:
        queryset = self.get_queryset()
        exact_filters = {
            "status": "status",
            "trigger_type": "trigger_type",
            "correlation_id": "correlation_id",
        }
        for parameter, field in exact_filters.items():
            if value := request.query_params.get(parameter):
                queryset = queryset.filter(**{field: value})
        for parameter, field in (("definition_id", "definition_id"), ("schedule_id", "schedule_id")):
            if value := request.query_params.get(parameter):
                queryset = queryset.filter(**{field: _as_uuid(value, parameter)})
        for parameter, lookup in (("created_from", "created_at__gte"), ("created_to", "created_at__lte")):
            if value := request.query_params.get(parameter):
                parsed = parse_datetime(value)
                if parsed is None:
                    raise ValidationError({parameter: ["Use an ISO-8601 date-time"]})
                queryset = queryset.filter(**{lookup: parsed})
        queryset = self._ordered(
            queryset, request, {"created_at": "created_at", "completed_at": "completed_at"}, "-created_at"
        )
        return self._paginate(queryset, RunListSerializer)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(RunDetailSerializer(self.get_object()).data)

    def create(self, request: Request) -> Response:
        serializer = RunStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        run = _service_call(
            lambda: self.service.start_run(
                self.tenant_id,
                data["definition_id"],
                self.actor_id,
                data["input"],
                data["idempotency_key"],
                data["trigger_type"],
                data.get("schedule_id"),
            )
        )
        return Response(RunDetailSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    def _control(self, request: Request, pk: str | None, operation: Callable[..., OrchestrationRun]) -> Response:
        self.get_object()
        serializer = RunControlSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = _service_call(
            lambda: operation(
                self.tenant_id, _as_uuid(pk, "id"), self.actor_id, serializer.validated_data["transition_key"]
            )
        )
        return Response(RunDetailSerializer(run).data)

    @action(detail=True, methods=("post",))
    def pause(self, request: Request, pk: str | None = None) -> Response:
        return self._control(request, pk, self.service.pause_run)

    @action(detail=True, methods=("post",))
    def resume(self, request: Request, pk: str | None = None) -> Response:
        return self._control(request, pk, self.service.resume_run)

    @action(detail=True, methods=("post",))
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        return self._control(request, pk, self.service.cancel_run)

    @action(detail=True, methods=("post",))
    def retry(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = RunRetrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = _service_call(
            lambda: self.service.retry_run(
                self.tenant_id, _as_uuid(pk, "id"), self.actor_id, serializer.validated_data["idempotency_key"]
            )
        )
        return Response(RunDetailSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=("get",), url_path="task-runs")
    def task_runs(self, request: Request, pk: str | None = None) -> Response:
        run = self.get_object()
        queryset = OrchestrationTaskRun.objects.for_tenant(self.tenant_id).filter(run=run).select_related("node")
        if value := request.query_params.get("status"):
            queryset = queryset.filter(status=value)
        if value := request.query_params.get("node_id"):
            queryset = queryset.filter(node_id=_as_uuid(value, "node_id"))
        queryset = self._ordered(
            queryset,
            request,
            {"created_at": "created_at", "started_at": "started_at", "completed_at": "completed_at"},
            "created_at",
        )
        return self._paginate(queryset, TaskRunListSerializer)

    @action(detail=True, methods=("get",))
    def events(self, request: Request, pk: str | None = None) -> Response:
        run = self.get_object()
        queryset = (
            OrchestrationEvent.objects.for_tenant(self.tenant_id)
            .filter(correlation_id=run.correlation_id)
            .order_by("occurred_at", "id")
        )
        return self._paginate(queryset, OrchestrationEventSerializer)


class TaskRunViewSet(GovernedTenantViewSet):
    service = ExecutionService()
    access_by_action = {
        "retrieve": read_access(RUN_VIEW),
        "retry": write_access(RUN_RETRY, cost=1),
    }

    def get_queryset(self):
        return (
            OrchestrationTaskRun.objects.for_tenant(self.tenant_id)
            .select_related("run", "node")
            .prefetch_related("attempts")
        )

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(TaskRunDetailSerializer(self.get_object()).data)

    @action(detail=True, methods=("post",))
    def retry(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = TaskRetrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task_run = _service_call(
            lambda: self.service.retry_task(
                self.tenant_id, _as_uuid(pk, "id"), self.actor_id, serializer.validated_data["idempotency_key"]
            )
        )
        return Response(TaskRunDetailSerializer(task_run).data, status=status.HTTP_202_ACCEPTED)


class NodeTypeViewSet(GovernedTenantViewSet):
    access_by_action = {"list": read_access(CATALOG_VIEW)}

    def list(self, request: Request) -> Response:
        # Catalog discovery deliberately includes safe locked/setup entries so
        # the OSS palette remains an extension funnel. Execution authorization
        # is evaluated independently and still fails closed in the worker.
        descriptors = list_node_catalog(getattr(request, "access_decision", None))
        return self._paginate(descriptors, NodeDescriptorSerializer)


class OrchestrationHealthView(GovernedAPIViewMixin, APIView):
    authentication_classes = (RequiredSessionAuthentication,)
    permission_classes = (IsAuthenticated,)

    def get(self, request: Request) -> Response:
        del request
        payload, status_code = sanitized_health_payload()
        if status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            raise CapabilityUnavailable(
                capability="automation_orchestration.runtime",
                message="The orchestration runtime is not ready.",
                detail=payload,
            )
        return Response(payload, status=status_code)


__all__ = [
    "DefinitionViewSet",
    "EdgeViewSet",
    "NodeTypeViewSet",
    "NodeViewSet",
    "OrchestrationHealthView",
    "RunViewSet",
    "ScheduleViewSet",
    "TaskRunViewSet",
]
