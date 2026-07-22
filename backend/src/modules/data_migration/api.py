"""Governed, tenant-isolated and service-only data-migration API v2."""

from __future__ import annotations

import csv
import io
import json
import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import asdict, is_dataclass
from typing import Any
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db.models import QuerySet
from django.http import StreamingHttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination, OperationFailed
from src.core.api.envelope import correlation_id_for_request
from src.core.auth_utils import get_user_tenant_id

from .filters import FilterValidationError, MigrationJobFilterSet, MigrationRunFilterSet, MigrationRunIssueFilterSet
from .models import (
    DataMigrationConfigurationAudit,
    ExternalConnection,
    MigrationJob,
    MigrationJobVersion,
    MigrationMapping,
    MigrationRollback,
    MigrationRun,
    MigrationRunIssue,
    ValidationRule,
)
from .permissions import (
    CONNECTION_ACTION_PERMISSIONS,
    CONFIGURATION_ACTION_PERMISSIONS,
    JOB_ACTION_PERMISSIONS,
    MAPPING_ACTION_PERMISSIONS,
    ROLLBACK_ACTION_PERMISSIONS,
    RULE_ACTION_PERMISSIONS,
    RUN_ACTION_PERMISSIONS,
    ActionAccessMixin,
    is_platform_operator,
)
from .serializers import (
    CancelRunSerializer,
    ConnectionTestResultSerializer,
    CredentialRotationSerializer,
    DefinitionImportSerializer,
    DataMigrationConfigurationAuditSerializer,
    DataMigrationConfigurationImportSerializer,
    DataMigrationConfigurationPreviewSerializer,
    DataMigrationConfigurationRestoreSerializer,
    DataMigrationConfigurationSerializer,
    DataMigrationConfigurationUpdateSerializer,
    ExpectedVersionSerializer,
    ExternalConnectionManagementSerializer,
    ExternalConnectionReferenceSerializer,
    InspectionRequestSerializer,
    MappingSuggestionApplySerializer,
    MappingSuggestionRequestSerializer,
    MigrationJobCreateSerializer,
    MigrationJobDetailSerializer,
    MigrationJobListSerializer,
    MigrationJobUpdateSerializer,
    MigrationJobVersionSerializer,
    MigrationMappingReadSerializer,
    MigrationMappingWriteSerializer,
    MigrationRollbackSerializer,
    MigrationRunIssueSerializer,
    MigrationRunRequestSerializer,
    MigrationRunSerializer,
    RestoreVersionSerializer,
    SourceAttachmentSerializer,
    TransitionSerializer,
    ValidationRuleReadSerializer,
    ValidationRuleWriteSerializer,
)
from .services import (
    DataMigrationConfigurationService,
    ExternalConnectionService,
    MigrationExecutionService,
    MigrationJobService,
    MigrationMappingService,
    RollbackService,
    SourceInspectionService,
    ValidationRuleService,
)

IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}$")
V1_SUNSET = "Thu, 31 Dec 2026 23:59:59 GMT"
V2_SUCCESSOR = '</api/v2/data-migration/>; rel="successor-version"'


def _tenant(request: Request) -> UUID:
    value = get_user_tenant_id(request.user)
    try:
        tenant = value if isinstance(value, UUID) else UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise PermissionDenied("Authenticated identity has no valid tenant context.") from exc
    request.tenant_id = tenant  # type: ignore[attr-defined]
    return tenant


def _actor(request: Request) -> UUID:
    value = getattr(request.user, "pk", None)
    if isinstance(value, UUID):
        return value
    if value is None:
        raise PermissionDenied("Authenticated identity has no actor identifier.")
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{value}")


def _idempotency_key(request: Request) -> str:
    value = request.headers.get("Idempotency-Key", "")
    if not IDEMPOTENCY_PATTERN.fullmatch(value):
        raise ValidationError({"Idempotency-Key": "A valid Idempotency-Key header is required."})
    return value


def _translate_error(exc: Exception) -> Exception:
    if isinstance(exc, ObjectDoesNotExist):
        return NotFound()
    if isinstance(exc, DjangoValidationError):
        return ValidationError(getattr(exc, "message_dict", {"non_field_errors": exc.messages}))
    if isinstance(exc, FilterValidationError):
        return ValidationError(exc.errors)
    if isinstance(exc, ValueError):
        return ValidationError({"non_field_errors": [str(exc)]})
    name = type(exc).__name__.lower()
    code = str(getattr(exc, "code", ""))
    if code in {"VERSION_CONFLICT", "IDEMPOTENCY_CONFLICT", "ROLLBACK_CONFLICT"}:
        return OperationFailed(error_code=code, message=str(exc), http_status=409)
    if code in {"CAPABILITY_UNAVAILABLE", "DEPENDENCY_UNAVAILABLE", "UNVERIFIED_SOURCE", "UNVERIFIED_WRITE"}:
        return OperationFailed(
            error_code=code,
            message="The requested data migration capability is currently unavailable.",
            http_status=503,
        )
    if code:
        return OperationFailed(error_code=code, message=str(exc), http_status=400)
    if "notfound" in name or "not_found" in name:
        return NotFound()
    if "conflict" in name or "version" in name and "error" in name:
        return OperationFailed(error_code="CONFLICT", message=str(exc), http_status=409)
    if "unavailable" in name or "circuit" in name or "timeout" in name:
        return OperationFailed(
            error_code="DEPENDENCY_UNAVAILABLE",
            message="A required data migration dependency is unavailable.",
            http_status=503,
        )
    return exc


def _call(operation: Callable[..., Any], *args: object, **kwargs: object) -> Any:
    try:
        return operation(*args, **kwargs)
    except Exception as exc:
        translated = _translate_error(exc)
        if translated is exc:
            raise
        raise translated from exc


def _result_data(value: object) -> object:
    """Normalize typed operation results without exposing internal payloads."""

    if hasattr(value, "value"):
        return getattr(value, "value")
    if hasattr(value, "data") and not isinstance(value, (dict, list, tuple)):
        return getattr(value, "data")
    if is_dataclass(value):
        return asdict(value)
    return value


class TenantGovernedViewSet(GovernedAPIViewMixin, ActionAccessMixin, viewsets.GenericViewSet[Any]):
    """Shared v2 boundary with mandatory pagination and explicit tenant scope."""

    pagination_class = GovernedPageNumberPagination
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    @property
    def tenant_id(self) -> UUID:
        return _tenant(self.request)

    @property
    def actor_id(self) -> UUID:
        return _actor(self.request)

    @property
    def correlation_id(self) -> str:
        return correlation_id_for_request(self.request)

    def paginated(self, queryset: QuerySet[Any], serializer: type, **context: object) -> Response:
        page = self.paginate_queryset(queryset)
        if page is None:
            raise RuntimeError("Governed pagination is mandatory for collections")
        return self.get_paginated_response(serializer(page, many=True, context={"request": self.request, **context}).data)

    def filtered(self, filter_type: type, queryset: QuerySet[Any]) -> QuerySet[Any]:
        filters = filter_type(self.request.query_params, queryset)
        if not filters.is_valid():
            raise ValidationError(filters.errors)
        return filters.qs

    def handle_exception(self, exc: Exception) -> Response:
        return super().handle_exception(_translate_error(exc))

    def finalize_response(self, request: Request, response: Response, *args: object, **kwargs: object) -> Response:
        response = super().finalize_response(request, response, *args, **kwargs)
        if request.path.startswith("/api/v1/data-migration/"):
            response["Deprecation"] = "true"
            response["Sunset"] = V1_SUNSET
            response["Link"] = V2_SUCCESSOR
        return response


class MigrationJobViewSet(TenantGovernedViewSet):
    queryset = MigrationJob.objects.all()
    action_permissions = JOB_ACTION_PERMISSIONS
    method_permissions = {
        "mappings": {"GET": "data_migration.job:read", "POST": "data_migration.mapping:manage"},
        "validation_rules": {"GET": "data_migration.job:read", "POST": "data_migration.rule:manage"},
        "runs": {"GET": "data_migration.job:read", "POST": "data_migration.run:execute"},
    }
    action_quotas = {"inspect": "data_migration.inspections", "runs": "data_migration.jobs", "request_dry_run": "data_migration.jobs"}

    def get_queryset(self) -> QuerySet[MigrationJob]:
        return MigrationJob.objects.filter(tenant_id=self.tenant_id, is_deleted=False)

    def get_object(self) -> MigrationJob:
        try:
            return self.get_queryset().get(pk=self.kwargs["pk"])
        except (MigrationJob.DoesNotExist, ValueError, TypeError) as exc:
            raise NotFound() from exc

    def list(self, request: Request) -> Response:
        del request
        queryset = self.filtered(MigrationJobFilterSet, self.get_queryset())
        return self.paginated(queryset, MigrationJobListSerializer)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        return Response(MigrationJobDetailSerializer(self.get_object()).data)

    def create(self, request: Request) -> Response:
        serializer = MigrationJobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = _call(MigrationJobService.create, self.tenant_id, self.actor_id, serializer.validated_data)
        return Response(MigrationJobDetailSerializer(job).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        serializer = MigrationJobUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        expected_version = values.pop("expected_version")
        job = _call(MigrationJobService.update, self.tenant_id, self.kwargs["pk"], self.actor_id, values, expected_version)
        return Response(MigrationJobDetailSerializer(job).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        _call(MigrationJobService.soft_delete, self.tenant_id, self.kwargs["pk"], self.actor_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",), url_path="validate")
    def validate_definition(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        result = _call(MigrationJobService.validate_definition, self.tenant_id, self.kwargs["pk"], self.actor_id)
        return Response(_result_data(result))

    @action(detail=True, methods=("post",))
    def archive(self, request: Request, pk: str | None = None) -> Response:
        del pk
        body = TransitionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        self.get_object()
        job = _call(MigrationJobService.archive, self.tenant_id, self.kwargs["pk"], self.actor_id, body.validated_data["transition_key"])
        return Response(MigrationJobDetailSerializer(job).data)

    @action(detail=True, methods=("post",))
    def restore(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        try:
            job = _call(MigrationJobService.restore_deleted, self.tenant_id, self.kwargs["pk"], self.actor_id)
        except NotFound:
            raise
        return Response(MigrationJobDetailSerializer(job).data)

    @action(detail=True, methods=("post",), url_path="source")
    def attach_source(self, request: Request, pk: str | None = None) -> Response:
        del pk
        body = SourceAttachmentSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        self.get_object()
        # Source attachment is a versioned job update; artifact tenancy is
        # validated by the service/DMS boundary, never by accepting a path.
        job = _call(
            MigrationJobService.update,
            self.tenant_id,
            self.kwargs["pk"],
            self.actor_id,
            {"source_artifact_id": body.validated_data["source_artifact_id"]},
            body.validated_data["expected_version"],
        )
        return Response(MigrationJobDetailSerializer(job).data)

    @action(detail=True, methods=("post",))
    def inspect(self, request: Request, pk: str | None = None) -> Response:
        del pk
        body = InspectionRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        self.get_object()
        async_job = _call(
            SourceInspectionService.request_inspection,
            self.tenant_id,
            self.kwargs["pk"],
            self.actor_id,
            _idempotency_key(request),
        )
        return Response({"async_job_id": str(async_job.id), "status": async_job.status}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=("get",))
    def preview(self, request: Request, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        raw_limit = request.query_params.get("limit", "25")
        body = ExpectedVersionSerializer(data={"expected_version": 1})  # ensure common strict serializer initializes
        del body
        try:
            limit = int(raw_limit)
        except ValueError as exc:
            raise ValidationError({"limit": "Must be an integer from 1 through 100."}) from exc
        if not 1 <= limit <= 100:
            raise ValidationError({"limit": "Must be an integer from 1 through 100."})
        result = _call(SourceInspectionService.preview, self.tenant_id, self.kwargs["pk"], limit)
        return Response(_result_data(result))

    @action(detail=True, methods=("get",), url_path="export")
    def export_definition(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        return Response(_result_data(_call(MigrationJobService.export_definition, self.tenant_id, self.kwargs["pk"])))

    @action(detail=False, methods=("post",), url_path="import")
    def import_definition(self, request: Request) -> Response:
        serializer = DefinitionImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = serializer.validated_data["document"]
        if serializer.validated_data["preview_only"]:
            return Response({"job": None, "diff": {"from_version": None, "to_version": 1, "entries": [{"path": "job", "operation": "add"}], "warnings": []}, "checksum_valid": True})
        job = _call(MigrationJobService.import_definition, self.tenant_id, self.actor_id, document)
        return Response({"job": MigrationJobDetailSerializer(job).data, "diff": {"from_version": None, "to_version": 1, "entries": [{"path": "job", "operation": "add"}], "warnings": []}, "checksum_valid": True}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("get",))
    def versions(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        queryset = MigrationJobVersion.objects.filter(tenant_id=self.tenant_id, job_id=self.kwargs["pk"]).order_by("-version")
        return self.paginated(queryset, MigrationJobVersionSerializer)

    @action(detail=True, methods=("post",), url_path=r"versions/(?P<version>[0-9]+)/restore")
    def restore_version(self, request: Request, pk: str | None = None, version: str | None = None) -> Response:
        del pk
        body = RestoreVersionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        self.get_object()
        job = _call(
            MigrationJobService.restore_version,
            self.tenant_id,
            self.kwargs["pk"],
            int(version or 0),
            self.actor_id,
            body.validated_data["expected_version"],
        )
        return Response(MigrationJobDetailSerializer(job).data)

    @action(detail=True, methods=("get", "post"))
    def mappings(self, request: Request, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        if request.method == "GET":
            return self.paginated(
                MigrationMapping.objects.filter(tenant_id=self.tenant_id, job_id=self.kwargs["pk"]).order_by("position", "id"),
                MigrationMappingReadSerializer,
            )
        body = MigrationMappingWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        mapping = _call(MigrationMappingService.create, self.tenant_id, self.kwargs["pk"], self.actor_id, body.validated_data)
        return Response(MigrationMappingReadSerializer(mapping).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("post",), url_path="mappings/suggest")
    def suggest_mappings(self, request: Request, pk: str | None = None) -> Response:
        del pk
        body = MappingSuggestionRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        self.get_object()
        if body.validated_data["provider"] != "deterministic":
            raise OperationFailed(error_code="CAPABILITY_UNAVAILABLE", message="No mapping suggestion extension is registered.", http_status=503)
        return Response(_call(MigrationMappingService.suggest_deterministic, self.tenant_id, self.kwargs["pk"]))

    @action(detail=True, methods=("post",), url_path="mappings/apply")
    def apply_mappings(self, request: Request, pk: str | None = None) -> Response:
        del pk
        body = MappingSuggestionApplySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        self.get_object()
        mappings = _call(
            MigrationMappingService.apply_suggestions,
            self.tenant_id,
            self.kwargs["pk"],
            self.actor_id,
            body.validated_data["suggestion_ids"],
        )
        return Response(MigrationMappingReadSerializer(mappings, many=True).data)

    @action(detail=True, methods=("get", "post"), url_path="validation-rules")
    def validation_rules(self, request: Request, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        if request.method == "GET":
            queryset = ValidationRule.objects.filter(tenant_id=self.tenant_id, job_id=self.kwargs["pk"]).order_by("position", "id")
            return self.paginated(queryset, ValidationRuleReadSerializer)
        body = ValidationRuleWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        rule = _call(ValidationRuleService.create, self.tenant_id, self.kwargs["pk"], self.actor_id, body.validated_data)
        return Response(ValidationRuleReadSerializer(rule).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("get", "post"))
    def runs(self, request: Request, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        if request.method == "GET":
            queryset = self.filtered(
                MigrationRunFilterSet,
                MigrationRun.objects.filter(tenant_id=self.tenant_id, job_id=self.kwargs["pk"]),
            )
            return self.paginated(queryset, MigrationRunSerializer)
        body = MigrationRunRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        run = _call(
            MigrationExecutionService.request_run,
            self.tenant_id,
            self.kwargs["pk"],
            self.actor_id,
            "commit",
            _idempotency_key(request),
        )
        return Response(MigrationRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=("post",), url_path="dry-runs")
    def request_dry_run(self, request: Request, pk: str | None = None) -> Response:
        del pk
        body = MigrationRunRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        self.get_object()
        run = _call(
            MigrationExecutionService.request_run,
            self.tenant_id,
            self.kwargs["pk"],
            self.actor_id,
            "dry_run",
            _idempotency_key(request),
        )
        return Response(MigrationRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class MigrationMappingViewSet(TenantGovernedViewSet):
    queryset = MigrationMapping.objects.all()
    action_permissions = MAPPING_ACTION_PERMISSIONS

    def get_queryset(self) -> QuerySet[MigrationMapping]:
        return MigrationMapping.objects.filter(tenant_id=self.tenant_id)

    def get_object(self) -> MigrationMapping:
        try:
            return self.get_queryset().get(pk=self.kwargs["pk"])
        except (MigrationMapping.DoesNotExist, ValueError, TypeError) as exc:
            raise NotFound() from exc

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        return Response(MigrationMappingReadSerializer(self.get_object()).data)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        body = MigrationMappingWriteSerializer(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        mapping = _call(MigrationMappingService.update, self.tenant_id, self.kwargs["pk"], self.actor_id, body.validated_data)
        return Response(MigrationMappingReadSerializer(mapping).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        _call(MigrationMappingService.delete, self.tenant_id, self.kwargs["pk"], self.actor_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ValidationRuleViewSet(TenantGovernedViewSet):
    queryset = ValidationRule.objects.all()
    action_permissions = RULE_ACTION_PERMISSIONS

    def get_queryset(self) -> QuerySet[ValidationRule]:
        return ValidationRule.objects.filter(tenant_id=self.tenant_id)

    def get_object(self) -> ValidationRule:
        try:
            return self.get_queryset().get(pk=self.kwargs["pk"])
        except (ValidationRule.DoesNotExist, ValueError, TypeError) as exc:
            raise NotFound() from exc

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        return Response(ValidationRuleReadSerializer(self.get_object()).data)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        body = ValidationRuleWriteSerializer(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        rule = _call(ValidationRuleService.update, self.tenant_id, self.kwargs["pk"], self.actor_id, body.validated_data)
        return Response(ValidationRuleReadSerializer(rule).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        _call(ValidationRuleService.delete, self.tenant_id, self.kwargs["pk"], self.actor_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _csv_cell(value: object) -> str:
    text = str(value or "")
    return f"'{text}" if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


class _CsvEcho:
    def write(self, value: str) -> str:
        return value


def _issue_csv_rows(issues: Iterable[MigrationRunIssue]) -> Iterable[str]:
    writer = csv.writer(_CsvEcho())
    yield writer.writerow(("row_number", "field_name", "stage", "severity", "code", "message", "redacted_sample"))
    for issue in issues:
        yield writer.writerow(
            tuple(
                _csv_cell(value)
                for value in (
                    issue.row_number,
                    issue.field_name,
                    issue.stage,
                    issue.severity,
                    issue.code,
                    issue.message,
                    json.dumps(issue.redacted_sample, sort_keys=True, separators=(",", ":")),
                )
            )
        )


class MigrationRunViewSet(TenantGovernedViewSet):
    queryset = MigrationRun.objects.all()
    action_permissions = RUN_ACTION_PERMISSIONS

    def get_queryset(self) -> QuerySet[MigrationRun]:
        return MigrationRun.objects.filter(tenant_id=self.tenant_id)

    def get_object(self) -> MigrationRun:
        try:
            return self.get_queryset().get(pk=self.kwargs["pk"])
        except (MigrationRun.DoesNotExist, ValueError, TypeError) as exc:
            raise NotFound() from exc

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        return Response(MigrationRunSerializer(self.get_object()).data)

    @action(detail=True, methods=("get",))
    def issues(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        self.get_object()
        queryset = self.filtered(
            MigrationRunIssueFilterSet,
            MigrationRunIssue.objects.filter(tenant_id=self.tenant_id, run_id=self.kwargs["pk"]),
        )
        return self.paginated(queryset, MigrationRunIssueSerializer)

    @action(detail=True, methods=("get",), url_path="issues/export")
    def export_issues(self, request: Request, pk: str | None = None) -> StreamingHttpResponse:
        del request, pk
        self.get_object()
        issues = MigrationRunIssue.objects.filter(tenant_id=self.tenant_id, run_id=self.kwargs["pk"]).order_by("row_number", "id").iterator(chunk_size=500)
        response = StreamingHttpResponse(_issue_csv_rows(issues), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="migration-run-{self.kwargs["pk"]}-issues.csv"'
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @action(detail=True, methods=("post",))
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        del pk
        body = CancelRunSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        self.get_object()
        run = _call(
            MigrationExecutionService.cancel,
            self.tenant_id,
            self.kwargs["pk"],
            self.actor_id,
            body.validated_data["transition_key"],
        )
        return Response(MigrationRunSerializer(run).data)

    @action(detail=True, methods=("post",))
    def rollback(self, request: Request, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        rollback = _call(RollbackService.request, self.tenant_id, self.kwargs["pk"], self.actor_id, _idempotency_key(request))
        return Response(MigrationRollbackSerializer(rollback).data, status=status.HTTP_202_ACCEPTED)


class MigrationRollbackViewSet(TenantGovernedViewSet):
    queryset = MigrationRollback.objects.all()
    action_permissions = ROLLBACK_ACTION_PERMISSIONS

    def get_queryset(self) -> QuerySet[MigrationRollback]:
        return MigrationRollback.objects.filter(tenant_id=self.tenant_id)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        try:
            rollback = self.get_queryset().get(pk=self.kwargs["pk"])
        except (MigrationRollback.DoesNotExist, ValueError, TypeError) as exc:
            raise NotFound() from exc
        return Response(MigrationRollbackSerializer(rollback).data)


class ExternalConnectionViewSet(TenantGovernedViewSet):
    queryset = ExternalConnection.objects.all()
    action_permissions = CONNECTION_ACTION_PERMISSIONS

    def _require_operator(self) -> None:
        if not is_platform_operator(self.request.user):
            raise PermissionDenied("Connection management is restricted to platform operators.")

    def get_queryset(self) -> QuerySet[ExternalConnection]:
        selected_tenant = self.tenant_id
        requested_tenant = self.request.query_params.get("tenant_id")
        if requested_tenant and is_platform_operator(self.request.user):
            try:
                selected_tenant = UUID(requested_tenant)
            except ValueError as exc:
                raise ValidationError({"tenant_id": "Must be a valid UUID."}) from exc
        elif requested_tenant:
            raise ValidationError({"tenant_id": "This filter is restricted to platform operators."})
        queryset = ExternalConnection.objects.filter(tenant_id=selected_tenant)
        if not is_platform_operator(self.request.user):
            queryset = queryset.filter(is_active=True)
        return queryset.order_by("name", "id")

    def get_object(self) -> ExternalConnection:
        try:
            return self.get_queryset().get(pk=self.kwargs["pk"])
        except (ExternalConnection.DoesNotExist, ValueError, TypeError) as exc:
            raise NotFound() from exc

    def list(self, request: Request) -> Response:
        del request
        return self.paginated(self.get_queryset(), ExternalConnectionReferenceSerializer)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        connection = self.get_object()
        serializer = ExternalConnectionManagementSerializer if is_platform_operator(self.request.user) else ExternalConnectionReferenceSerializer
        return Response(serializer(connection).data)

    def create(self, request: Request) -> Response:
        self._require_operator()
        body = ExternalConnectionManagementSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        connection = _call(ExternalConnectionService.register, self.tenant_id, self.actor_id, body.validated_data)
        return Response(ExternalConnectionManagementSerializer(connection).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        del pk
        self._require_operator()
        current = self.get_object()
        body = ExternalConnectionManagementSerializer(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        connection = _call(ExternalConnectionService.update, current.tenant_id, self.kwargs["pk"], self.actor_id, body.validated_data)
        return Response(ExternalConnectionManagementSerializer(connection).data)

    @action(detail=True, methods=("post",))
    def deactivate(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        self._require_operator()
        current = self.get_object()
        connection = _call(ExternalConnectionService.deactivate, current.tenant_id, self.kwargs["pk"], self.actor_id)
        return Response(ExternalConnectionManagementSerializer(connection).data)

    @action(detail=True, methods=("post",), url_path="rotate-credential")
    def rotate_credential(self, request: Request, pk: str | None = None) -> Response:
        del pk
        self._require_operator()
        current = self.get_object()
        body = CredentialRotationSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        connection = _call(
            ExternalConnectionService.rotate_credential,
            current.tenant_id,
            self.kwargs["pk"],
            self.actor_id,
            body.validated_data["credential_ref"],
        )
        return Response(ExternalConnectionManagementSerializer(connection).data)

    @action(detail=True, methods=("post",), url_path="test")
    def test_connection(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        self._require_operator()
        current = self.get_object()
        result = _result_data(_call(ExternalConnectionService.test, current.tenant_id, self.kwargs["pk"], self.actor_id))
        return Response(ConnectionTestResultSerializer(result).data)


class DataMigrationConfigurationViewSet(TenantGovernedViewSet):
    """Singleton tenant runtime controls with preview, history and rollback."""

    action_permissions = CONFIGURATION_ACTION_PERMISSIONS

    def retrieve_configuration(self, request: Request) -> Response:
        del request
        config = _call(DataMigrationConfigurationService.get, self.tenant_id)
        return Response(DataMigrationConfigurationSerializer(config).data)

    def update_configuration(self, request: Request) -> Response:
        body = DataMigrationConfigurationUpdateSerializer(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        values = dict(body.validated_data)
        expected_version = values.pop("expected_version")
        config = _call(
            DataMigrationConfigurationService.update,
            self.tenant_id,
            self.actor_id,
            values["document"],
            expected_version,
            self.correlation_id,
        )
        return Response(DataMigrationConfigurationSerializer(config).data)

    def preview_configuration(self, request: Request) -> Response:
        body = DataMigrationConfigurationPreviewSerializer(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        return Response(_call(DataMigrationConfigurationService.preview, self.tenant_id, body.validated_data))

    def configuration_versions(self, request: Request) -> Response:
        del request
        queryset = DataMigrationConfigurationAudit.objects.filter(tenant_id=self.tenant_id).order_by("-version", "-created_at")
        return self.paginated(queryset, DataMigrationConfigurationAuditSerializer)

    def restore_configuration(self, request: Request, version: str) -> Response:
        body = DataMigrationConfigurationRestoreSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            selected_version = int(version)
        except ValueError as exc:
            raise NotFound() from exc
        config = _call(
            DataMigrationConfigurationService.restore,
            self.tenant_id,
            self.actor_id,
            selected_version,
            body.validated_data["expected_version"],
        )
        return Response(DataMigrationConfigurationSerializer(config).data)

    def import_configuration(self, request: Request) -> Response:
        body = DataMigrationConfigurationImportSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        values = dict(body.validated_data)
        expected_version = values.pop("expected_version")
        config = _call(
            DataMigrationConfigurationService.import_document,
            self.tenant_id,
            self.actor_id,
            values,
            expected_version,
        )
        return Response(DataMigrationConfigurationSerializer(config).data)

    def export_configuration(self, request: Request) -> Response:
        del request
        return Response(_call(DataMigrationConfigurationService.export, self.tenant_id))


__all__ = [
    "ExternalConnectionViewSet",
    "DataMigrationConfigurationViewSet",
    "MigrationJobViewSet",
    "MigrationMappingViewSet",
    "MigrationRollbackViewSet",
    "MigrationRunViewSet",
    "ValidationRuleViewSet",
]
