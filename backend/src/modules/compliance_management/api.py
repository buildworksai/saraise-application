"""Governed, tenant-safe API v2 controllers for compliance management."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Callable
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import mixins, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.access import RequiresAccess
from src.core.api import GovernedAPIViewMixin, OperationFailed
from src.core.auth_utils import get_user_tenant_id

from .models import ComplianceConfigurationRevision, EvidenceRequirementLink, RequirementPolicyMapping
from .permissions import requirement_for
from .serializers import (
    ActivitySerializer, AssessmentCreateSerializer, AssessmentSerializer,
    ConfigurationImportSerializer, ConfigurationPreviewSerializer,
    ConfigurationRevisionSerializer, ConfigurationWriteSerializer,
    DashboardSerializer, EvidenceDetailSerializer, EvidenceLinkSerializer,
    EvidenceLinkWriteSerializer, EvidenceListSerializer, EvidenceValidationSerializer,
    EvidenceWriteSerializer, FrameworkDetailSerializer, FrameworkImportSerializer,
    FrameworkListSerializer, FrameworkWriteSerializer, GapSerializer,
    MappingBulkSerializer, MappingSerializer, MappingWriteSerializer,
    PolicyDetailSerializer, PolicyListSerializer, PolicyTransitionSerializer,
    PolicyVersionCreateSerializer, PolicyVersionSerializer, PolicyWriteSerializer,
    RequirementBulkImportSerializer, RequirementDetailSerializer,
    RequirementListSerializer, RequirementWriteSerializer, ScorecardSerializer,
)
from .services import (
    ActivityService, AssessmentService, ComplianceConflict,
    ComplianceDashboardService, ComplianceDependencyUnavailable,
    ComplianceNotFound, ComplianceValidationError, ConfigurationService,
    EvidenceService, FrameworkService, MappingService, PolicyService,
    RequirementService,
)


class RequiredSessionAuthentication(SessionAuthentication):
    """Strict CSRF-enforcing session authentication with a 401 challenge."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


def _tenant(request: Any) -> UUID:
    raw = getattr(request, "tenant_id", None) or get_user_tenant_id(request.user)
    try:
        tenant = raw if isinstance(raw, UUID) else UUID(str(raw))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PermissionDenied("Authenticated tenant context is required.") from exc
    request.tenant_id = tenant
    return tenant


def _correlation(request: Any) -> UUID:
    raw = getattr(request, "correlation_id", "")
    try:
        return UUID(str(raw))
    except (TypeError, ValueError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:request:{raw or uuid.uuid4()}")


def _call(operation: Callable[..., Any], *args: object, **kwargs: object):
    try:
        return operation(*args, **kwargs)
    except ComplianceNotFound as exc:
        raise NotFound() from exc
    except ComplianceConflict as exc:
        raise OperationFailed(error_code="CONFLICT", message=str(exc), http_status=409) from exc
    except ComplianceDependencyUnavailable as exc:
        raise OperationFailed(error_code="DEPENDENCY_UNAVAILABLE", message=str(exc), http_status=503) from exc
    except ComplianceValidationError as exc:
        raise ValidationError(exc.detail) from exc
    except DjangoValidationError as exc:
        raise ValidationError(getattr(exc, "message_dict", {"non_field_errors": exc.messages})) from exc
    except IntegrityError as exc:
        raise OperationFailed(error_code="CONFLICT", message="A conflicting record already exists.", http_status=409) from exc


def _idempotency(request: Any, *, required: bool = True) -> str:
    value = request.headers.get("Idempotency-Key", "").strip()
    if required and not value:
        raise ValidationError({"Idempotency-Key": ["This header is required."]})
    if len(value) > 255:
        raise ValidationError({"Idempotency-Key": ["Must be 255 characters or fewer."]})
    return value


def _as_of(raw: str | None):
    if not raw:
        return None
    parsed = parse_datetime(raw) or parse_date(raw)
    if parsed is None:
        raise ValidationError({"as_of": ["Use an ISO-8601 date or date-time."]})
    return parsed


class GovernedTenantViewSet(GovernedAPIViewMixin, viewsets.GenericViewSet):
    """Fail-closed access metadata, strict sessions, and mandatory pagination."""

    authentication_classes = (RequiredSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    access_name = ""

    def get_permissions(self):
        try:
            _tenant(self.request)
        except PermissionDenied:
            self.request.tenant_id = None
        requirement = requirement_for(self.access_name, getattr(self, "action", ""), self.request.method)
        self.required_permission = requirement.permission if requirement else None
        self.required_entitlement = requirement.entitlement if requirement else None
        self.quota_resource = requirement.quota_resource if requirement else None
        self.quota_cost = requirement.quota_cost if requirement else 0
        return super().get_permissions()

    @property
    def tenant_id(self) -> UUID:
        return _tenant(self.request)

    @property
    def actor(self):
        return self.request.user

    @property
    def correlation_id(self) -> UUID:
        return _correlation(self.request)

    def paginated(self, queryset, serializer_class):
        page = self.paginate_queryset(queryset)
        if page is None:
            raise RuntimeError("Governed pagination is required.")
        return self.get_paginated_response(serializer_class(page, many=True).data)

    def checked(self, obj):
        self.check_object_permissions(self.request, obj)
        return obj

    def handle_exception(self, exc):
        return super().handle_exception(_translate(exc))


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, ComplianceNotFound): return NotFound()
    if isinstance(exc, ComplianceConflict): return OperationFailed(error_code="CONFLICT", message=str(exc), http_status=409)
    if isinstance(exc, ComplianceDependencyUnavailable): return OperationFailed(error_code="DEPENDENCY_UNAVAILABLE", message=str(exc), http_status=503)
    if isinstance(exc, ComplianceValidationError): return ValidationError(exc.detail)
    if isinstance(exc, DjangoValidationError): return ValidationError(getattr(exc, "message_dict", {"non_field_errors": exc.messages}))
    if isinstance(exc, IntegrityError): return OperationFailed(error_code="CONFLICT", message="A conflicting record already exists.", http_status=409)
    return exc


class FrameworkViewSet(GovernedTenantViewSet):
    access_name = "framework"
    service = FrameworkService

    def get_queryset(self):
        filters = {key: self.request.query_params[key] for key in ("status", "category", "source_kind", "search") if key in self.request.query_params}
        return self.service.list_frameworks(self.tenant_id, filters, self.request.query_params.get("ordering", "name"))

    def list(self, request, *args, **kwargs):
        return self.paginated(self.get_queryset(), FrameworkListSerializer)

    def retrieve(self, request, pk=None):
        obj = self.checked(_call(self.service.get_framework, self.tenant_id, pk))
        return Response(FrameworkDetailSerializer(obj).data)

    def create(self, request):
        serializer = FrameworkWriteSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        obj = _call(self.service.create_framework, self.tenant_id, self.actor, serializer.validated_data, self.correlation_id)
        return Response(FrameworkDetailSerializer(obj).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        serializer = FrameworkWriteSerializer(data=request.data, partial=True); serializer.is_valid(raise_exception=True)
        obj = _call(self.service.update_framework, self.tenant_id, self.actor, pk, serializer.validated_data, self.correlation_id)
        return Response(FrameworkDetailSerializer(obj).data)

    def destroy(self, request, pk=None):
        key = _idempotency(request, required=False) or str(self.correlation_id)
        _call(self.service.archive_framework, self.tenant_id, self.actor, pk, key, self.correlation_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def activate(self, request, pk=None):
        obj = _call(self.service.activate_framework, self.tenant_id, self.actor, pk, _idempotency(request), self.correlation_id)
        return Response(FrameworkDetailSerializer(obj).data)

    @action(detail=True, methods=("get",))
    def export(self, request, pk=None):
        return Response(_call(self.service.export_framework, self.tenant_id, pk))

    @action(detail=False, methods=("post",), url_path="import")
    def import_package(self, request):
        serializer = FrameworkImportSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        obj = _call(self.service.import_framework, self.tenant_id, self.actor, serializer.validated_data["package"], _idempotency(request), self.correlation_id)
        return Response(FrameworkDetailSerializer(obj).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("get",))
    def status(self, request, pk=None):
        obj = self.checked(_call(self.service.get_framework, self.tenant_id, pk))
        return Response({"framework": FrameworkDetailSerializer(obj).data, "readiness": AssessmentService.scorecard(self.tenant_id, obj.id), "gaps": MappingService.gap_analysis(self.tenant_id, obj.id)})


class RequirementViewSet(GovernedTenantViewSet):
    access_name = "requirement"; service = RequirementService

    def get_queryset(self):
        filters = {key: self.request.query_params[key] for key in ("framework_id", "status", "applicability", "search") if key in self.request.query_params}
        return self.service.list_requirements(self.tenant_id, filters, self.request.query_params.get("ordering", "sort_order"))

    def list(self, request): return self.paginated(self.get_queryset(), RequirementListSerializer)
    def retrieve(self, request, pk=None): return Response(RequirementDetailSerializer(self.checked(_call(self.service.get_requirement, self.tenant_id, pk))).data)

    def create(self, request):
        serializer = RequirementWriteSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        obj = _call(self.service.create_requirement, self.tenant_id, self.actor, serializer.validated_data, self.correlation_id)
        return Response(RequirementDetailSerializer(obj).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        serializer = RequirementWriteSerializer(data=request.data, partial=True); serializer.is_valid(raise_exception=True)
        obj = _call(self.service.update_requirement, self.tenant_id, self.actor, pk, serializer.validated_data, self.correlation_id)
        return Response(RequirementDetailSerializer(obj).data)

    def destroy(self, request, pk=None):
        key = _idempotency(request, required=False) or str(self.correlation_id)
        _call(self.service.archive_requirement, self.tenant_id, self.actor, pk, key, self.correlation_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def restore(self, request, pk=None):
        obj = _call(self.service.restore_requirement, self.tenant_id, self.actor, pk, _idempotency(request), self.correlation_id)
        return Response(RequirementDetailSerializer(obj).data)

    @action(detail=False, methods=("post",), url_path="import")
    def import_rows(self, request):
        serializer = RequirementBulkImportSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        rows = _call(self.service.bulk_import, self.tenant_id, self.actor, serializer.validated_data["framework_id"], serializer.validated_data["rows"], _idempotency(request), self.correlation_id)
        return Response(RequirementDetailSerializer(rows, many=True).data, status=status.HTTP_201_CREATED)


class PolicyViewSet(GovernedTenantViewSet):
    access_name = "policy"; service = PolicyService

    def get_queryset(self):
        filters = {key: self.request.query_params[key] for key in ("status", "category", "owner_id", "review_before", "expiry_before", "search") if key in self.request.query_params}
        return self.service.list_policies(self.tenant_id, filters, self.request.query_params.get("ordering", "code"))

    def list(self, request): return self.paginated(self.get_queryset(), PolicyListSerializer)
    def retrieve(self, request, pk=None): return Response(PolicyDetailSerializer(self.checked(_call(self.service.get_policy, self.tenant_id, pk))).data)

    def create(self, request):
        serializer = PolicyWriteSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        obj = _call(self.service.create_policy, self.tenant_id, self.actor, serializer.validated_data, self.correlation_id)
        return Response(PolicyDetailSerializer(obj).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        serializer = PolicyWriteSerializer(data=request.data, partial=True); serializer.is_valid(raise_exception=True)
        obj = _call(self.service.update_policy, self.tenant_id, self.actor, pk, serializer.validated_data, self.correlation_id)
        return Response(PolicyDetailSerializer(obj).data)

    def destroy(self, request, pk=None):
        key = _idempotency(request, required=False) or str(self.correlation_id)
        _call(self.service.archive, self.tenant_id, self.actor, pk, key, self.correlation_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("get", "post"))
    def versions(self, request, pk=None):
        policy = self.checked(_call(self.service.get_policy, self.tenant_id, pk))
        if request.method == "GET":
            return self.paginated(policy.versions.filter(tenant_id=self.tenant_id).order_by("-version"), PolicyVersionSerializer)
        serializer = PolicyVersionCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        obj = _call(self.service.create_version, self.tenant_id, self.actor, policy.id, serializer.validated_data["content"], serializer.validated_data["change_summary"], _idempotency(request), self.correlation_id)
        return Response(PolicyVersionSerializer(obj).data, status=status.HTTP_201_CREATED)

    def _transition(self, request, pk, command):
        serializer = PolicyTransitionSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        key = serializer.validated_data.get("transition_key") or _idempotency(request)
        if command == "request_changes": obj = _call(self.service.request_changes, self.tenant_id, self.actor, pk, serializer.validated_data.get("reason", ""), key, self.correlation_id)
        elif command == "revise":
            if not serializer.validated_data.get("content") or not serializer.validated_data.get("change_summary"):
                raise ValidationError({"content": ["Content and change summary are required."]})
            obj, _ = _call(self.service.revise, self.tenant_id, self.actor, pk, serializer.validated_data["content"], serializer.validated_data["change_summary"], key, self.correlation_id)
        else: obj = _call(getattr(self.service, command), self.tenant_id, self.actor, pk, key, self.correlation_id)
        return Response(PolicyDetailSerializer(obj).data)

    @action(detail=True, methods=("post",))
    def submit(self, request, pk=None): return self._transition(request, pk, "submit")
    @action(detail=True, methods=("post",), url_path="request-changes")
    def request_changes(self, request, pk=None): return self._transition(request, pk, "request_changes")
    @action(detail=True, methods=("post",))
    def approve(self, request, pk=None): return self._transition(request, pk, "approve")
    @action(detail=True, methods=("post",))
    def publish(self, request, pk=None): return self._transition(request, pk, "publish")
    @action(detail=True, methods=("post",))
    def revise(self, request, pk=None): return self._transition(request, pk, "revise")


class MappingViewSet(GovernedTenantViewSet):
    access_name = "mapping"; service = MappingService

    def get_queryset(self):
        filters = {key: self.request.query_params[key] for key in ("framework_id", "requirement_id", "policy_id", "coverage") if key in self.request.query_params}
        return self.service.list_mappings(self.tenant_id, filters, self.request.query_params.get("ordering", "mapped_at"))

    def list(self, request): return self.paginated(self.get_queryset(), MappingSerializer)
    def retrieve(self, request, pk=None): return Response(MappingSerializer(self.checked(_call(_get_mapping, self.tenant_id, pk))).data)

    def create(self, request):
        serializer = MappingWriteSerializer(data=request.data); serializer.is_valid(raise_exception=True); data = dict(serializer.validated_data)
        obj = _call(self.service.set_mapping, self.tenant_id, self.actor, data.pop("requirement_id"), data.pop("policy_id"), data, _idempotency(request), self.correlation_id)
        return Response(MappingSerializer(obj).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        existing = self.checked(_call(_get_mapping, self.tenant_id, pk)); serializer = MappingWriteSerializer(data=request.data, partial=True); serializer.is_valid(raise_exception=True); data = dict(serializer.validated_data)
        obj = _call(self.service.set_mapping, self.tenant_id, self.actor, data.pop("requirement_id", existing.requirement_id), data.pop("policy_id", existing.policy_id), data, _idempotency(request), self.correlation_id)
        return Response(MappingSerializer(obj).data)

    def destroy(self, request, pk=None):
        _call(self.service.remove_mapping, self.tenant_id, self.actor, pk, self.correlation_id); return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=("post",))
    def bulk(self, request):
        serializer = MappingBulkSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        rows = _call(self.service.bulk_set_mappings, self.tenant_id, self.actor, serializer.validated_data["rows"], _idempotency(request), self.correlation_id)
        return Response(MappingSerializer(rows, many=True).data)


def _get_mapping(tenant_id, mapping_id):
    try: return RequirementPolicyMapping.objects.for_tenant(tenant_id).filter(deleted_at__isnull=True).get(pk=mapping_id)
    except (RequirementPolicyMapping.DoesNotExist, ValueError) as exc: raise ComplianceNotFound("Mapping was not found.") from exc


class GapViewSet(GovernedTenantViewSet):
    access_name = "gap"
    def list(self, request):
        framework_id = request.query_params.get("framework_id")
        if not framework_id: raise ValidationError({"framework_id": ["This query parameter is required."]})
        return Response(GapSerializer(_call(MappingService.gap_analysis, self.tenant_id, framework_id, _as_of(request.query_params.get("as_of")))).data)


class AssessmentViewSet(GovernedTenantViewSet):
    access_name = "assessment"; service = AssessmentService
    def get_queryset(self):
        filters = {key: self.request.query_params[key] for key in ("framework_id", "requirement_id", "status", "due_after", "due_before") if key in self.request.query_params}
        return self.service.list_assessments(self.tenant_id, filters, self.request.query_params.get("ordering", "-assessed_at"))
    def list(self, request): return self.paginated(self.get_queryset(), AssessmentSerializer)
    def retrieve(self, request, pk=None): return Response(AssessmentSerializer(self.checked(_call(self.service.get_assessment, self.tenant_id, pk))).data)
    def create(self, request):
        serializer = AssessmentCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        obj = _call(self.service.record_assessment, self.tenant_id, self.actor, serializer.validated_data, _idempotency(request), self.correlation_id)
        return Response(AssessmentSerializer(obj).data, status=status.HTTP_201_CREATED)
    @action(detail=False, methods=("get",))
    def scorecard(self, request):
        framework_id = request.query_params.get("framework_id")
        if not framework_id: raise ValidationError({"framework_id": ["This query parameter is required."]})
        return Response(ScorecardSerializer(_call(self.service.scorecard, self.tenant_id, framework_id, _as_of(request.query_params.get("as_of")))).data)


class EvidenceViewSet(GovernedTenantViewSet):
    access_name = "evidence"; service = EvidenceService
    def get_queryset(self):
        filters = {key: self.request.query_params[key] for key in ("type", "classification", "requirement_id", "valid_before", "search") if key in self.request.query_params}
        return self.service.list_evidence(self.tenant_id, filters, self.request.query_params.get("ordering", "-collected_at"))
    def list(self, request): return self.paginated(self.get_queryset(), EvidenceListSerializer)
    def retrieve(self, request, pk=None): return Response(EvidenceDetailSerializer(self.checked(_call(self.service.get_evidence, self.tenant_id, pk))).data)
    def create(self, request):
        serializer = EvidenceWriteSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        obj = _call(self.service.register_evidence, self.tenant_id, self.actor, serializer.validated_data, self.correlation_id)
        return Response(EvidenceDetailSerializer(obj).data, status=status.HTTP_201_CREATED)
    def partial_update(self, request, pk=None):
        serializer = EvidenceWriteSerializer(data=request.data, partial=True); serializer.is_valid(raise_exception=True)
        obj = _call(self.service.update_evidence, self.tenant_id, self.actor, pk, serializer.validated_data, self.correlation_id)
        return Response(EvidenceDetailSerializer(obj).data)
    def destroy(self, request, pk=None):
        _call(self.service.archive_evidence, self.tenant_id, self.actor, pk, self.correlation_id); return Response(status=status.HTTP_204_NO_CONTENT)
    @action(detail=True, methods=("post",))
    def validate(self, request, pk=None):
        return Response(EvidenceValidationSerializer(_call(self.service.validate_evidence, self.tenant_id, pk, _as_of(request.data.get("as_of")))).data)
    @action(detail=True, methods=("post",), url_path="requirements")
    def requirements(self, request, pk=None):
        serializer = EvidenceLinkWriteSerializer(data=request.data); serializer.is_valid(raise_exception=True); data = dict(serializer.validated_data)
        obj = _call(self.service.link_requirement, self.tenant_id, self.actor, pk, data.pop("requirement_id"), data, self.correlation_id)
        return Response(EvidenceLinkSerializer(obj).data, status=status.HTTP_201_CREATED)


class EvidenceLinkViewSet(GovernedTenantViewSet):
    access_name = "evidence-link"
    def destroy(self, request, pk=None):
        _call(EvidenceService.unlink_requirement, self.tenant_id, self.actor, pk, self.correlation_id); return Response(status=status.HTTP_204_NO_CONTENT)


class ConfigurationViewSet(GovernedTenantViewSet):
    access_name = "configuration"; service = ConfigurationService
    def get_queryset(self):
        environment = self.request.query_params.get("environment", "development")
        qs = self.service.list_revisions(self.tenant_id, environment)
        if self.request.query_params.get("status"): qs = qs.filter(status=self.request.query_params["status"])
        return qs
    def list(self, request): return self.paginated(self.get_queryset(), ConfigurationRevisionSerializer)
    def retrieve(self, request, pk=None): return Response(ConfigurationRevisionSerializer(self.checked(_call(_get_configuration, self.tenant_id, pk))).data)
    def create(self, request):
        serializer = ConfigurationWriteSerializer(data=request.data); serializer.is_valid(raise_exception=True); data = dict(serializer.validated_data); environment = data.pop("environment", "development")
        obj = _call(self.service.create_revision, self.tenant_id, self.actor, environment, data, self.correlation_id)
        return Response(ConfigurationRevisionSerializer(obj).data, status=status.HTTP_201_CREATED)
    def partial_update(self, request, pk=None):
        serializer = ConfigurationWriteSerializer(data=request.data, partial=True); serializer.is_valid(raise_exception=True); data = dict(serializer.validated_data); data.pop("environment", None)
        obj = _call(self.service.update_draft, self.tenant_id, self.actor, pk, data, self.correlation_id); return Response(ConfigurationRevisionSerializer(obj).data)
    @action(detail=True, methods=("get",))
    def preview(self, request, pk=None): return Response(ConfigurationPreviewSerializer(_call(self.service.preview, self.tenant_id, pk)).data)
    @action(detail=True, methods=("post",))
    def activate(self, request, pk=None):
        obj = _call(self.service.activate, self.tenant_id, self.actor, pk, _idempotency(request), self.correlation_id); return Response(ConfigurationRevisionSerializer(obj).data)
    @action(detail=True, methods=("post",))
    def rollback(self, request, pk=None):
        obj = _call(self.service.rollback, self.tenant_id, self.actor, pk, _idempotency(request), self.correlation_id); return Response(ConfigurationRevisionSerializer(obj).data, status=status.HTTP_201_CREATED)
    @action(detail=True, methods=("get",))
    def export(self, request, pk=None): return Response(_call(self.service.export_revision, self.tenant_id, pk))
    @action(detail=False, methods=("post",), url_path="import")
    def import_document(self, request):
        serializer = ConfigurationImportSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        obj = _call(self.service.import_revision, self.tenant_id, self.actor, serializer.validated_data["document"], self.correlation_id)
        return Response(ConfigurationRevisionSerializer(obj).data, status=status.HTTP_201_CREATED)


def _get_configuration(tenant_id, revision_id):
    try: return ComplianceConfigurationRevision.objects.for_tenant(tenant_id).get(pk=revision_id)
    except (ComplianceConfigurationRevision.DoesNotExist, ValueError) as exc: raise ComplianceNotFound("Configuration revision was not found.") from exc


class ActivityViewSet(GovernedTenantViewSet):
    access_name = "activity"
    def list(self, request):
        filters = {key: request.query_params[key] for key in ("entity_type", "entity_id", "actor_id", "action", "correlation_id", "occurred_after", "occurred_before") if key in request.query_params}
        return self.paginated(ActivityService.list_activity(self.tenant_id, filters, request.query_params.get("ordering", "-occurred_at")), ActivitySerializer)


class DashboardViewSet(GovernedTenantViewSet):
    access_name = "dashboard"
    def list(self, request):
        result = _call(ComplianceDashboardService.summary, self.tenant_id, request.query_params.get("framework_id"), _as_of(request.query_params.get("as_of")))
        return Response(DashboardSerializer(result).data)


class JobViewSet(GovernedTenantViewSet):
    access_name = "job"
    def retrieve(self, request, pk=None):
        try:
            from src.core.async_jobs.models import AsyncJob
            job = AsyncJob.objects.filter(tenant_id=self.tenant_id, pk=pk, command__startswith="compliance_management.").get()
        except Exception as exc:
            if exc.__class__.__name__ == "DoesNotExist": raise NotFound() from exc
            if isinstance(exc, (ValueError, TypeError)): raise NotFound() from exc
            raise
        return Response({"id": job.id, "command": job.command, "status": job.status, "correlation_id": job.correlation_id, "created_at": job.created_at, "updated_at": job.updated_at, "result": getattr(job, "result", None), "error_code": getattr(job, "error_code", "")})


# Legacy class names retained for import compatibility only.
CompliancePolicyViewSet = PolicyViewSet
ComplianceRequirementViewSet = RequirementViewSet


__all__ = [name for name in globals() if name.endswith("ViewSet")]
