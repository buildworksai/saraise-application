"""Governed, tenant-isolated API v2 endpoints for disaster recovery."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db.models import Q, QuerySet
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from src.core.access import RequiresAccess
from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination
from src.core.api.results import OperationFailed
from src.core.async_jobs.models import AsyncJob
from src.core.views.tenant_scoped import TenantScopedModelViewSet

from .models import (
    DRExercise,
    DRRunbook,
    DRStepExecution,
    RecoveryPoint,
    RestoreRun,
    RunbookStep,
    TargetEnvironment,
)
from .permissions import (
    BACKUP_EXECUTE,
    BACKUP_READ,
    EXERCISE_CREATE,
    EXERCISE_EXECUTE,
    EXERCISE_UPDATE,
    READ,
    REPORT_READ,
    RESTORE_CREATE,
    RESTORE_EXECUTE,
    RUNBOOK_CREATE,
    RUNBOOK_DELETE,
    RUNBOOK_PUBLISH,
    RUNBOOK_UPDATE,
    VERIFY_POINT,
    AccessRule,
)
from .serializers import (
    BackupExecutionCreateSerializer,
    BackupExecutionReceiptSerializer,
    BackupExecutionStatusSerializer,
    DRExerciseCancelSerializer,
    DRExerciseCreateSerializer,
    DRExerciseDetailSerializer,
    DRExerciseListSerializer,
    DRExerciseStartSerializer,
    DRExerciseUpdateSerializer,
    DRRunbookCloneSerializer,
    DRRunbookCreateSerializer,
    DRRunbookDetailSerializer,
    DRRunbookListSerializer,
    DRRunbookUpdateSerializer,
    DRStepExecutionDetailSerializer,
    DRStepExecutionListSerializer,
    ObjectiveReportQuerySerializer,
    ObjectiveReportSerializer,
    ReadinessSummarySerializer,
    RecoveryPointDetailSerializer,
    RecoveryPointListSerializer,
    RecoveryPointVerifySerializer,
    RestoreRunCancelSerializer,
    RestoreRunCreateSerializer,
    RestoreRunDetailSerializer,
    RestoreRunExecuteSerializer,
    RestoreRunListSerializer,
    RunbookStepCreateSerializer,
    RunbookStepDetailSerializer,
    RunbookStepListSerializer,
    RunbookStepReorderSerializer,
    RunbookStepUpdateSerializer,
)
from .services import (
    BDRDomainError,
    BackupExecutionFacade,
    BackupRequestCommand,
    DependencyUnavailable,
    DRExerciseService,
    ExerciseCommand,
    RecoveryObjectiveService,
    RecoveryPointService,
    RestoreRunCommand,
    RestoreService,
    RunbookCommand,
    RunbookService,
    RunbookStepCommand,
    dataclass_payload,
)


class CsrfSessionAuthentication(SessionAuthentication):
    """Normal session auth with CSRF and an explicit 401 challenge."""

    def authenticate_header(self, request: Request) -> str:
        del request
        return "Session"


def _actor_id(request: Request) -> UUID:
    """Map the legacy integer auth subject into the domain's UUID audit type."""

    value = getattr(request.user, "id", None)
    if isinstance(value, UUID):
        return value
    return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{value}")


def _parse_uuid(value: object, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({field: "Must be a valid UUID."}) from exc


def _parse_date(value: str | None, field: str) -> datetime | None:
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValidationError({field: "Must be an ISO-8601 date-time."})
    return parsed


class GovernedBDRViewSet(GovernedAPIViewMixin, TenantScopedModelViewSet):
    """Shared deny-default access and safe service-error translation."""

    authentication_classes = (CsrfSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    pagination_class = GovernedPageNumberPagination
    access_map: Mapping[str, AccessRule] = {}
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def check_permissions(self, request: Request) -> None:
        if request.method.lower() not in self.http_method_names:
            raise MethodNotAllowed(request.method)
        tenant_id = self._get_tenant_id()
        if tenant_id is not None:
            request.tenant_id = tenant_id  # type: ignore[attr-defined]
        rule = self.access_map.get(getattr(self, "action", ""))
        if rule is None:
            self.required_permission = ""
            self.required_entitlement = ""
            self.quota_resource = ""
            self.quota_cost = 1
        else:
            self.required_permission = rule.permission
            self.required_entitlement = rule.entitlement
            self.quota_resource = rule.quota_resource
            self.quota_cost = rule.quota_cost
        super().check_permissions(request)

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, BDRDomainError):
            exc = OperationFailed(
                error_code=exc.code,
                message=exc.public_message,
                http_status=exc.http_status,
            )
        return super().handle_exception(exc)

    def tenant_id(self) -> UUID:
        return self._require_tenant_id()

    def _validate_query(self, allowed: set[str]) -> None:
        common = {"page", "page_size", "search", "ordering", "format"}
        unknown = set(self.request.query_params) - allowed - common
        if unknown:
            raise ValidationError({key: "Unknown query parameter." for key in sorted(unknown)})


class BackupExecutionViewSet(GovernedBDRViewSet):
    queryset = RecoveryPoint.objects.all()
    serializer_class = BackupExecutionStatusSerializer
    http_method_names = ["get", "post", "head", "options"]
    access_map = {"create": BACKUP_EXECUTE, "retrieve": BACKUP_READ}

    def create(self, request: Request) -> Response:
        serializer = BackupExecutionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        result = BackupExecutionFacade().request_backup(
            self.tenant_id(),
            _actor_id(request),
            BackupRequestCommand(
                backup_type=str(values["backup_type"]),
                scope_type=str(values["scope_type"]),
                scope_ref=str(values["scope_ref"]),
                idempotency_key=str(values["idempotency_key"]),
            ),
        )
        receipt = result.unwrap()
        payload = dataclass_payload(receipt)
        payload["status"] = receipt.status.value
        job = AsyncJob.objects.for_tenant(self.tenant_id()).get(
            idempotency_key=f"bdr:backup:{values['idempotency_key']}"
        )
        payload["async_job_id"] = job.id
        payload["requested_at"] = job.created_at
        return Response(BackupExecutionReceiptSerializer(payload).data, status=status.HTTP_202_ACCEPTED)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        del request
        snapshot = BackupExecutionFacade().get_backup_status(
            self.tenant_id(), _parse_uuid(pk, "backup_job_id")
        )
        payload = dataclass_payload(snapshot)
        payload["status"] = snapshot.status.value
        point = (
            RecoveryPoint.objects.for_tenant(self.tenant_id())
            .filter(backup_job_id=snapshot.backup_job_id)
            .only("id")
            .first()
        )
        payload["recovery_point_id"] = point.id if point else None
        payload["error_message"] = ""
        return Response(BackupExecutionStatusSerializer(payload).data)


class RecoveryPointViewSet(GovernedBDRViewSet):
    queryset = RecoveryPoint.objects.all()
    serializer_class = RecoveryPointDetailSerializer
    http_method_names = ["get", "post", "head", "options"]
    access_map = {"list": READ, "retrieve": READ, "verify": VERIFY_POINT, "expire": VERIFY_POINT}

    def get_queryset(self) -> QuerySet[RecoveryPoint]:
        if not hasattr(self, "request"):
            return RecoveryPoint.objects.none()
        self._validate_query({"status", "scope_type", "scope_ref", "captured_after", "captured_before"})
        filters: dict[str, object] = {
            "status": self.request.query_params.get("status"),
            "scope_type": self.request.query_params.get("scope_type"),
            "scope_ref": self.request.query_params.get("scope_ref"),
            "captured_after": _parse_date(self.request.query_params.get("captured_after"), "captured_after"),
            "captured_before": _parse_date(self.request.query_params.get("captured_before"), "captured_before"),
        }
        queryset = RecoveryPointService().list_recovery_points(self.tenant_id(), filters)
        search = self.request.query_params.get("search", "").strip()
        if search:
            predicate = Q(scope_ref__icontains=search)
            try:
                predicate |= Q(backup_job_id=UUID(search))
            except ValueError:
                pass
            queryset = queryset.filter(predicate)
        ordering = self.request.query_params.get("ordering", "-captured_at")
        allowed = {"captured_at", "expires_at", "size_bytes"}
        fields = ordering.split(",")
        if any(field.lstrip("-") not in allowed for field in fields):
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return queryset.order_by(*fields, "-id")

    def get_serializer_class(self) -> type[Any]:
        return RecoveryPointListSerializer if self.action == "list" else RecoveryPointDetailSerializer

    @action(detail=True, methods=["post"])
    def verify(self, request: Request, pk: str | None = None) -> Response:
        serializer = RecoveryPointVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = RecoveryPointService().request_verification(
            self.tenant_id(),
            _actor_id(request),
            _parse_uuid(pk, "id"),
            str(serializer.validated_data["idempotency_key"]),
        )
        return Response(
            {"async_job_id": job.id, "status": job.status, "accepted_at": job.created_at},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def expire(self, request: Request, pk: str | None = None) -> Response:
        transition_key = request.data.get("transition_key")
        if not isinstance(transition_key, str) or not transition_key.strip():
            raise ValidationError({"transition_key": "This field is required."})
        point = RecoveryPointService().expire_recovery_point(
            self.tenant_id(), _actor_id(request), _parse_uuid(pk, "id"), transition_key
        )
        return Response(RecoveryPointDetailSerializer(point).data)


class RestoreRunViewSet(GovernedBDRViewSet):
    queryset = RestoreRun.objects.all()
    serializer_class = RestoreRunDetailSerializer
    access_map = {
        "list": READ,
        "retrieve": READ,
        "create": RESTORE_CREATE,
        "execute": RESTORE_EXECUTE,
        "cancel": RESTORE_EXECUTE,
    }

    def get_queryset(self) -> QuerySet[RestoreRun]:
        if not hasattr(self, "request"):
            return RestoreRun.objects.none()
        self._validate_query(
            {"status", "target_environment", "recovery_point", "requested_after", "requested_before"}
        )
        filters: dict[str, object] = {
            "status": self.request.query_params.get("status"),
            "target_environment": self.request.query_params.get("target_environment"),
            "recovery_point": self.request.query_params.get("recovery_point"),
            "requested_after": _parse_date(self.request.query_params.get("requested_after"), "requested_after"),
            "requested_before": _parse_date(self.request.query_params.get("requested_before"), "requested_before"),
        }
        return RestoreService().list_restore_runs(self.tenant_id(), filters)

    def get_serializer_class(self) -> type[Any]:
        if self.action == "list":
            return RestoreRunListSerializer
        if self.action == "create":
            return RestoreRunCreateSerializer
        return RestoreRunDetailSerializer

    def create(self, request: Request) -> Response:
        serializer = RestoreRunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if values["target_environment"] == TargetEnvironment.PRODUCTION:
            # The current foundation does not expose a verifier for fresh step-up
            # proofs.  Do not convert possession of an opaque token into approval.
            raise DependencyUnavailable("production restore step-up verification")
        run = RestoreService().create_restore_run(
            self.tenant_id(),
            _actor_id(request),
            RestoreRunCommand(
                recovery_point_id=values["recovery_point_id"],
                runbook_id=values.get("runbook_id"),
                exercise_id=values.get("exercise_id"),
                target_environment=str(values["target_environment"]),
                target_ref=str(values["target_ref"]),
                restore_mode=str(values["restore_mode"]),
                selected_components=tuple(values.get("selected_components", [])),
                idempotency_key=str(values["idempotency_key"]),
            ),
        )
        return Response(RestoreRunDetailSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def execute(self, request: Request, pk: str | None = None) -> Response:
        serializer = RestoreRunExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = RestoreService().execute_restore(
            self.tenant_id(),
            _actor_id(request),
            _parse_uuid(pk, "id"),
            str(serializer.validated_data["idempotency_key"]),
        )
        return Response(
            {"async_job_id": job.id, "status": job.status, "accepted_at": job.created_at},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        serializer = RestoreRunCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = RestoreService().cancel_restore(
            self.tenant_id(),
            _actor_id(request),
            _parse_uuid(pk, "id"),
            str(serializer.validated_data["transition_key"]),
        )
        return Response(RestoreRunDetailSerializer(run).data)


class DRRunbookViewSet(GovernedBDRViewSet):
    queryset = DRRunbook.objects.all()
    serializer_class = DRRunbookDetailSerializer
    access_map = {
        "list": READ,
        "retrieve": READ,
        "create": RUNBOOK_CREATE,
        "partial_update": RUNBOOK_UPDATE,
        "destroy": RUNBOOK_DELETE,
        "clone": RUNBOOK_CREATE,
        "publish": RUNBOOK_PUBLISH,
        "retire": RUNBOOK_PUBLISH,
        "reorder_steps": RUNBOOK_UPDATE,
    }

    def get_queryset(self) -> QuerySet[DRRunbook]:
        if not hasattr(self, "request"):
            return DRRunbook.objects.none()
        self._validate_query({"status", "scope_type", "owner_id"})
        filters: dict[str, object] = {
            "status": self.request.query_params.get("status"),
            "scope_type": self.request.query_params.get("scope_type"),
            "owner_id": self.request.query_params.get("owner_id"),
        }
        queryset = RunbookService().list_runbooks(self.tenant_id(), filters)
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(slug__icontains=search))
        ordering = self.request.query_params.get("ordering", "-updated_at")
        fields = ordering.split(",")
        if any(field.lstrip("-") not in {"updated_at", "name", "version"} for field in fields):
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return queryset.order_by(*fields, "-id")

    def get_serializer_class(self) -> type[Any]:
        if self.action == "list":
            return DRRunbookListSerializer
        if self.action == "create":
            return DRRunbookCreateSerializer
        if self.action == "partial_update":
            return DRRunbookUpdateSerializer
        return DRRunbookDetailSerializer

    def create(self, request: Request) -> Response:
        serializer = DRRunbookCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        runbook = RunbookService().create_runbook(
            self.tenant_id(),
            _actor_id(request),
            RunbookCommand(
                name=str(values["name"]),
                slug=str(values["slug"]),
                description=str(values.get("description", "")),
                scope_type=str(values["scope_type"]),
                scope_ref=str(values["scope_ref"]),
                backup_schedule_id=values.get("backup_schedule_id"),
                adapter_key=str(
                    getattr(settings, "BDR_STORAGE_ADAPTER_KEY", "local-filesystem")
                ),
                rpo_target_seconds=int(values["rpo_target_seconds"]),
                rto_target_seconds=int(values["rto_target_seconds"]),
                owner_id=_actor_id(request),
            ),
        )
        return Response(DRRunbookDetailSerializer(runbook).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        serializer = DRRunbookUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        runbook = RunbookService().update_draft(
            self.tenant_id(), _actor_id(request), _parse_uuid(pk, "id"), serializer.validated_data
        )
        return Response(DRRunbookDetailSerializer(runbook).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        RunbookService().soft_delete_draft(self.tenant_id(), _actor_id(request), _parse_uuid(pk, "id"))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def clone(self, request: Request, pk: str | None = None) -> Response:
        serializer = DRRunbookCloneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        runbook = RunbookService().clone_version(self.tenant_id(), _actor_id(request), _parse_uuid(pk, "id"))
        if serializer.validated_data.get("name"):
            runbook = RunbookService().update_draft(
                self.tenant_id(), _actor_id(request), runbook.id, {"name": serializer.validated_data["name"]}
            )
        return Response(DRRunbookDetailSerializer(runbook).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def publish(self, request: Request, pk: str | None = None) -> Response:
        key = request.data.get("transition_key")
        if not isinstance(key, str) or not key.strip():
            raise ValidationError({"transition_key": "This field is required."})
        runbook = RunbookService().publish(self.tenant_id(), _actor_id(request), _parse_uuid(pk, "id"), key)
        return Response(DRRunbookDetailSerializer(runbook).data)

    @action(detail=True, methods=["post"])
    def retire(self, request: Request, pk: str | None = None) -> Response:
        key = request.data.get("transition_key")
        if not isinstance(key, str) or not key.strip():
            raise ValidationError({"transition_key": "This field is required."})
        runbook = RunbookService().retire(self.tenant_id(), _actor_id(request), _parse_uuid(pk, "id"), key)
        return Response(DRRunbookDetailSerializer(runbook).data)

    @action(detail=True, methods=["post"], url_path="reorder-steps")
    def reorder_steps(self, request: Request, pk: str | None = None) -> Response:
        serializer = RunbookStepReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        steps = RunbookService().reorder_steps(
            self.tenant_id(),
            _actor_id(request),
            _parse_uuid(pk, "id"),
            serializer.validated_data["step_ids"],
        )
        return Response(RunbookStepDetailSerializer(steps, many=True).data)


class RunbookStepViewSet(GovernedBDRViewSet):
    queryset = RunbookStep.objects.all()
    serializer_class = RunbookStepDetailSerializer
    access_map = {
        "list": READ,
        "retrieve": READ,
        "create": RUNBOOK_UPDATE,
        "partial_update": RUNBOOK_UPDATE,
        "destroy": RUNBOOK_UPDATE,
    }

    def get_queryset(self) -> QuerySet[RunbookStep]:
        if not hasattr(self, "request"):
            return RunbookStep.objects.none()
        self._validate_query({"runbook_id"})
        queryset = RunbookStep.objects.for_tenant(self.tenant_id()).filter(deleted_at__isnull=True).select_related("runbook")
        runbook_id = self.request.query_params.get("runbook_id")
        if self.action == "list" and not runbook_id:
            raise ValidationError({"runbook_id": "This filter is required."})
        if runbook_id:
            queryset = queryset.filter(runbook_id=_parse_uuid(runbook_id, "runbook_id"))
        return queryset.order_by("position", "id")

    def get_serializer_class(self) -> type[Any]:
        if self.action == "list":
            return RunbookStepListSerializer
        if self.action == "create":
            return RunbookStepCreateSerializer
        if self.action == "partial_update":
            return RunbookStepUpdateSerializer
        return RunbookStepDetailSerializer

    def create(self, request: Request) -> Response:
        serializer = RunbookStepCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        step = RunbookService().create_step(
            self.tenant_id(),
            _actor_id(request),
            RunbookStepCommand(
                runbook_id=values["runbook_id"],
                step_key=str(values["step_key"]),
                position=int(values["position"]),
                name=str(values["name"]),
                description=str(values.get("description", "")),
                action_type=str(values["action_type"]),
                extension_action_key=values.get("extension_action_key"),
                parameters=values["parameters"],
                timeout_seconds=int(values["timeout_seconds"]),
                retry_limit=int(values["retry_limit"]),
                on_failure=str(values["on_failure"]),
                approval_permission=values.get("approval_permission"),
            ),
        )
        return Response(RunbookStepDetailSerializer(step).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        current = self.get_object()
        serializer = RunbookStepUpdateSerializer(current, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        step = RunbookService().update_step(
            self.tenant_id(), _actor_id(request), _parse_uuid(pk, "id"), serializer.validated_data
        )
        return Response(RunbookStepDetailSerializer(step).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        RunbookService().soft_delete_step(self.tenant_id(), _actor_id(request), _parse_uuid(pk, "id"))
        return Response(status=status.HTTP_204_NO_CONTENT)


class DRExerciseViewSet(GovernedBDRViewSet):
    queryset = DRExercise.objects.all()
    serializer_class = DRExerciseDetailSerializer
    access_map = {
        "list": READ,
        "retrieve": READ,
        "create": EXERCISE_CREATE,
        "partial_update": EXERCISE_UPDATE,
        "start": EXERCISE_EXECUTE,
        "cancel": EXERCISE_EXECUTE,
    }

    def get_queryset(self) -> QuerySet[DRExercise]:
        if not hasattr(self, "request"):
            return DRExercise.objects.none()
        self._validate_query({"status", "exercise_type", "runbook", "scheduled_after", "scheduled_before"})
        filters: dict[str, object] = {
            "status": self.request.query_params.get("status"),
            "exercise_type": self.request.query_params.get("exercise_type"),
            "runbook": self.request.query_params.get("runbook"),
            "scheduled_after": _parse_date(self.request.query_params.get("scheduled_after"), "scheduled_after"),
            "scheduled_before": _parse_date(self.request.query_params.get("scheduled_before"), "scheduled_before"),
        }
        return DRExerciseService().list_exercises(self.tenant_id(), filters)

    def get_serializer_class(self) -> type[Any]:
        if self.action == "list":
            return DRExerciseListSerializer
        if self.action == "create":
            return DRExerciseCreateSerializer
        if self.action == "partial_update":
            return DRExerciseUpdateSerializer
        return DRExerciseDetailSerializer

    def create(self, request: Request) -> Response:
        serializer = DRExerciseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        exercise = DRExerciseService().schedule_exercise(
            self.tenant_id(), _actor_id(request), ExerciseCommand(**serializer.validated_data)
        )
        return Response(DRExerciseDetailSerializer(exercise).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        serializer = DRExerciseUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        exercise = DRExerciseService().update_scheduled_exercise(
            self.tenant_id(), _actor_id(request), _parse_uuid(pk, "id"), serializer.validated_data
        )
        return Response(DRExerciseDetailSerializer(exercise).data)

    @action(detail=True, methods=["post"])
    def start(self, request: Request, pk: str | None = None) -> Response:
        serializer = DRExerciseStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = DRExerciseService().start_exercise(
            self.tenant_id(), _actor_id(request), _parse_uuid(pk, "id"), str(serializer.validated_data["idempotency_key"])
        )
        return Response(
            {"async_job_id": job.id, "status": job.status, "accepted_at": job.created_at},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        serializer = DRExerciseCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        exercise = DRExerciseService().cancel_exercise(
            self.tenant_id(), _actor_id(request), _parse_uuid(pk, "id"), str(serializer.validated_data["transition_key"])
        )
        return Response(DRExerciseDetailSerializer(exercise).data)


class DRStepExecutionViewSet(GovernedBDRViewSet):
    queryset = DRStepExecution.objects.all()
    serializer_class = DRStepExecutionDetailSerializer
    http_method_names = ["get", "head", "options"]
    access_map = {"list": READ, "retrieve": READ}

    def get_queryset(self) -> QuerySet[DRStepExecution]:
        if not hasattr(self, "request"):
            return DRStepExecution.objects.none()
        self._validate_query({"exercise", "runbook_step", "status"})
        queryset = DRStepExecution.objects.for_tenant(self.tenant_id()).select_related("exercise", "runbook_step")
        for field in ("exercise", "runbook_step", "status"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset.order_by("created_at", "id")

    def get_serializer_class(self) -> type[Any]:
        return DRStepExecutionListSerializer if self.action == "list" else DRStepExecutionDetailSerializer


class ObjectiveReportViewSet(GovernedBDRViewSet):
    queryset = RestoreRun.objects.all()
    serializer_class = ObjectiveReportSerializer
    http_method_names = ["get", "head", "options"]
    access_map = {"list": REPORT_READ}

    def list(self, request: Request) -> Response:
        self._validate_query({"runbook_id", "from", "to", "bucket"})
        data = request.query_params.copy()
        if "from" in data:
            data["from_at"] = data.pop("from")
        serializer = ObjectiveReportQuerySerializer(data=data)
        serializer.is_valid(raise_exception=True)
        report = RecoveryObjectiveService().report_objectives(self.tenant_id(), serializer.validated_data)
        return Response(ObjectiveReportSerializer(dataclass_payload(report)).data)


class ReadinessViewSet(GovernedBDRViewSet):
    queryset = RecoveryPoint.objects.all()
    serializer_class = ReadinessSummarySerializer
    http_method_names = ["get", "head", "options"]
    access_map = {"list": REPORT_READ}

    def list(self, request: Request) -> Response:
        del request
        summary = RecoveryObjectiveService().get_readiness_summary(self.tenant_id())
        payload = {
            "calculated_at": summary.calculated_at,
            "rpo_compliance_percent": summary.rpo_compliance_percent,
            "rto_compliance_percent": summary.rto_compliance_percent,
            "last_verified_recovery_point": summary.last_verified_recovery_point,
            "latest_passed_exercise": summary.latest_passed_exercise,
            "latest_successful_restore": summary.latest_successful_restore,
            "latest_failed_restore": summary.latest_failed_restore,
            "next_scheduled_exercise": summary.next_scheduled_exercise,
            "stale_runbook_count": summary.stale_runbook_count,
            "unpublished_runbook_count": summary.unpublished_runbook_count,
            "current_rpo_breaches": summary.current_rpo_breaches,
            "current_rto_breaches": summary.current_rto_breaches,
            "provider_state": summary.provider_state,
            "queue_state": summary.queue_state,
            "provider_message": summary.provider_message,
        }
        return Response(ReadinessSummarySerializer(payload).data)


__all__ = [name for name in globals() if name.endswith("ViewSet")]
