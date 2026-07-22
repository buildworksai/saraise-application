"""Governed API v2 adapters for metadata-modeling services."""

from __future__ import annotations

import uuid

from django.core.cache import cache
from django.db import connection
from django.utils.dateparse import parse_datetime
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView, exception_handler as drf_exception_handler

from src.core.access.permissions import RequiresAccess
from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination
from src.core.api.envelope import correlation_id_for_request
from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication
from src.core.async_jobs.services import enqueue

from .models import DynamicResourceVersion, NamingSequence
from .permissions import (
    CONFIG_ACTION_ACCESS,
    ENTITY_ACTION_ACCESS,
    HEALTH_ACTION_ACCESS,
    RESOURCE_ACTION_ACCESS,
    SEQUENCE_ACTION_ACCESS,
    access_for_action,
)
from .serializers import (
    DynamicResourceCreateSerializer,
    DynamicResourceDetailSerializer,
    DynamicResourceListSerializer,
    DynamicResourcePatchSerializer,
    DynamicResourceReplaceSerializer,
    DynamicResourceVersionSerializer,
    EntityDefinitionCreateSerializer,
    EntityDefinitionDetailSerializer,
    EntityDefinitionImportSerializer,
    EntityDefinitionListSerializer,
    EntityDefinitionPreviewSerializer,
    EntityDefinitionUpdateSerializer,
    EntitySchemaVersionDetailSerializer,
    EntitySchemaVersionListSerializer,
    NamingSequenceSerializer,
    MetadataConfigurationAuditSerializer,
    MetadataConfigurationSerializer,
    MetadataConfigurationWriteSerializer,
    ResourceTransitionSerializer,
    SchemaCandidateCreateSerializer,
    SchemaPublishSerializer,
    SequenceResetSerializer,
)
from .services import (
    DynamicResourceService, EntityDefinitionService, MetadataConfigurationService, NamingService, SchemaVersionService,
)


def _tenant_id(request) -> uuid.UUID:
    raw = get_user_tenant_id(request.user)
    if not raw:
        raise PermissionDenied("A tenant context is required.")
    try:
        tenant_id = uuid.UUID(str(raw))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PermissionDenied("The tenant context is invalid.") from exc
    request.tenant_id = tenant_id
    return tenant_id


def _actor_id(request) -> uuid.UUID:
    value = getattr(request.user, "id", None)
    if isinstance(value, uuid.UUID):
        return value
    return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{value}")


def _correlation_id(request) -> str:
    return correlation_id_for_request(request)


def _idempotency_key(request) -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise ValidationError({"idempotency_key": [{"code": "REQUIRED", "message": "Idempotency-Key is required."}]})
    if len(key) > 255:
        raise ValidationError({"idempotency_key": [{"code": "MAX_LENGTH", "message": "Key is too long."}]})
    return key


def _lock_version(request) -> int:
    raw = request.headers.get("If-Match")
    if raw is None:
        raw = request.data.get("lock_version") if isinstance(request.data, dict) else None
    if isinstance(raw, str):
        raw = raw.strip(' W/"')
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"lock_version": [{"code": "REQUIRED", "message": "If-Match is required."}]}) from exc
    if value < 1:
        raise ValidationError({"lock_version": [{"code": "OUT_OF_RANGE", "message": "Must be positive."}]})
    return value


def _date_param(request, name: str):
    raw = request.query_params.get(name)
    if not raw:
        return None
    parsed = parse_datetime(raw)
    if parsed is None:
        raise ValidationError({name: [{"code": "INVALID_DATETIME", "message": "Use an ISO 8601 datetime."}]})
    return parsed


class GovernedMetadataViewSet(GovernedAPIViewMixin, viewsets.GenericViewSet):
    """Common tenant/correlation/access behavior with explicit action maps."""

    authentication_classes = (RelaxedCsrfSessionAuthentication,)
    pagination_class = GovernedPageNumberPagination
    access_map = {}

    def get_exception_handler(self):
        if self.request.path.startswith("/api/v1/"):
            return drf_exception_handler
        return super().get_exception_handler()

    def initial(self, request, *args, **kwargs):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            raise NotAuthenticated()
        _tenant_id(request)
        super().initial(request, *args, **kwargs)

    def get_permissions(self):
        # Keep the applied legacy v1 route operational during migration.  The
        # authoritative v2 route always executes the fail-closed access pipeline.
        if self.request.path.startswith("/api/v1/"):
            return [IsAuthenticated()]
        requirement = access_for_action(getattr(self, "action", None), self.access_map)
        if requirement is None:
            return [IsAuthenticated(), RequiresAccess()]
        self.required_permission = requirement.permission
        self.required_entitlement = requirement.entitlement
        self.quota_resource = requirement.quota_resource
        self.quota_cost = requirement.quota_cost
        return [IsAuthenticated(), RequiresAccess()]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["X-Correlation-ID"] = _correlation_id(request)
        return response

    def _page(self, queryset, serializer_class):
        page = self.paginate_queryset(queryset)
        if page is None:
            return Response(serializer_class(queryset, many=True).data)
        return self.get_paginated_response(serializer_class(page, many=True).data)


class EntityDefinitionViewSet(GovernedMetadataViewSet):
    access_map = ENTITY_ACTION_ACCESS

    def get_queryset(self):
        return EntityDefinitionService.list_definitions(
            _tenant_id(self.request),
            status=self.request.query_params.get("status"),
            owner_module=self.request.query_params.get("owner_module"),
            origin=self.request.query_params.get("origin"),
            search=self.request.query_params.get("search"),
            ordering=self.request.query_params.get("ordering"),
        )

    def list(self, request):
        return self._page(self.get_queryset(), EntityDefinitionListSerializer)

    def retrieve(self, request, pk=None):
        entity = EntityDefinitionService.get_definition(_tenant_id(request), pk)
        return Response(EntityDefinitionDetailSerializer(entity).data)

    def create(self, request):
        serializer = EntityDefinitionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = request.headers.get("Idempotency-Key") or (f"legacy:{uuid.uuid4()}" if request.path.startswith("/api/v1/") else _idempotency_key(request))
        entity = EntityDefinitionService.create_definition(
            _tenant_id(request), _actor_id(request), serializer.validated_data,
            idempotency_key=key, correlation_id=_correlation_id(request),
        )
        return Response(EntityDefinitionDetailSerializer(entity).data, status=status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        serializer = EntityDefinitionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current = EntityDefinitionService.get_definition(_tenant_id(request), pk)
        expected = current.lock_version if request.path.startswith("/api/v1/") else _lock_version(request)
        entity = EntityDefinitionService.update_definition(
            _tenant_id(request), _actor_id(request), current.id, serializer.validated_data,
            expected_lock_version=expected, correlation_id=_correlation_id(request),
        )
        return Response(EntityDefinitionDetailSerializer(entity).data)

    def partial_update(self, request, pk=None):
        serializer = EntityDefinitionUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        entity = EntityDefinitionService.update_definition(
            _tenant_id(request), _actor_id(request), pk, serializer.validated_data,
            expected_lock_version=_lock_version(request), correlation_id=_correlation_id(request),
        )
        return Response(EntityDefinitionDetailSerializer(entity).data)

    def destroy(self, request, pk=None):
        entity = EntityDefinitionService.get_definition(_tenant_id(request), pk)
        if entity.status == "draft":
            EntityDefinitionService.delete_draft_definition(
                _tenant_id(request), _actor_id(request), entity.id, correlation_id=_correlation_id(request)
            )
            return Response({"operation": "delete", "status": "completed", "id": str(entity.id)})
        EntityDefinitionService.archive_definition(
            _tenant_id(request), _actor_id(request), entity.id,
            idempotency_key=request.headers.get("Idempotency-Key", f"archive:{entity.id}"),
            correlation_id=_correlation_id(request),
        )
        return Response({"operation": "archive", "status": "completed", "id": str(entity.id)})

    @action(detail=True, methods=("post",))
    def archive(self, request, pk=None):
        entity = EntityDefinitionService.archive_definition(
            _tenant_id(request), _actor_id(request), pk,
            idempotency_key=_idempotency_key(request), correlation_id=_correlation_id(request),
        )
        return Response(EntityDefinitionDetailSerializer(entity).data)

    @action(detail=True, methods=("post",))
    def restore(self, request, pk=None):
        entity = EntityDefinitionService.restore_definition(
            _tenant_id(request), _actor_id(request), pk,
            idempotency_key=_idempotency_key(request), correlation_id=_correlation_id(request),
        )
        return Response(EntityDefinitionDetailSerializer(entity).data)

    @action(detail=True, methods=("post",))
    def clone(self, request, pk=None):
        entity = EntityDefinitionService.clone_definition(
            _tenant_id(request), _actor_id(request), pk,
            str(request.data.get("code", "")), str(request.data.get("name", "")),
            correlation_id=_correlation_id(request),
        )
        return Response(EntityDefinitionDetailSerializer(entity).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("post",))
    def preview(self, request, pk=None):
        serializer = EntityDefinitionPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = EntityDefinitionService.preview_definition(
            _tenant_id(request), pk, serializer.validated_data["schema"], serializer.validated_data.get("sample_data")
        )
        return Response(result)

    @action(detail=False, methods=("post",), url_path="preview")
    def preview_new(self, request):
        serializer = EntityDefinitionPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            EntityDefinitionService.preview_unpersisted(
                _tenant_id(request),
                serializer.validated_data["schema"],
                serializer.validated_data.get("sample_data"),
            )
        )

    @action(detail=True, methods=("get",), url_path="export")
    def export(self, request, pk=None):
        return Response(EntityDefinitionService.export_definition(_tenant_id(request), pk))

    @action(detail=False, methods=("post",), url_path="import")
    def import_schema(self, request):
        serializer = EntityDefinitionImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = EntityDefinitionService.import_definition(
            _tenant_id(request), _actor_id(request), serializer.validated_data["document"],
            mode=serializer.validated_data["mode"], idempotency_key=_idempotency_key(request),
            correlation_id=_correlation_id(request),
        )
        if isinstance(result, dict):
            return Response(result)
        return Response(EntitySchemaVersionDetailSerializer(result).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("get", "post"), url_path="versions")
    def versions(self, request, pk=None):
        if request.method == "GET":
            return self._page(SchemaVersionService.list_versions(_tenant_id(request), pk), EntitySchemaVersionListSerializer)
        serializer = SchemaCandidateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        version = SchemaVersionService.create_candidate(
            _tenant_id(request), _actor_id(request), pk, serializer.validated_data["fields"],
            based_on_version_id=serializer.validated_data.get("based_on_version_id"),
            change_summary=serializer.validated_data.get("change_summary", ""), correlation_id=_correlation_id(request),
        )
        return Response(EntitySchemaVersionDetailSerializer(version).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("get",), url_path=r"versions/(?P<version_id>[^/.]+)")
    def version_detail(self, request, pk=None, version_id=None):
        version = SchemaVersionService.get_version(_tenant_id(request), pk, version_id)
        return Response(EntitySchemaVersionDetailSerializer(version).data)

    @action(detail=True, methods=("post",), url_path=r"versions/(?P<version_id>[^/.]+)/validate")
    def validate_version(self, request, pk=None, version_id=None):
        tenant_id = _tenant_id(request)
        config = MetadataConfigurationService.get_configuration(tenant_id, "production")
        record_count = DynamicResourceService.list_resources(tenant_id, entity_id=pk).count()
        if record_count > config.synchronous_validation_limit:
            job = enqueue(
                tenant_id,
                _actor_id(request),
                "metadata_modeling.validate_schema",
                {
                    "definition_id": str(pk),
                    "version_id": str(version_id),
                    "sample_limit": min(record_count, 1000),
                },
                _idempotency_key(request),
            )
            return Response(
                {"job_id": str(job.id), "status": job.status, "command": job.command},
                status=status.HTTP_202_ACCEPTED,
            )
        return Response(
            SchemaVersionService.validate_candidate(
                tenant_id, pk, version_id, sample_limit=config.synchronous_validation_limit
            )
        )

    @action(detail=True, methods=("post",), url_path=r"versions/(?P<version_id>[^/.]+)/publish")
    def publish_version(self, request, pk=None, version_id=None):
        serializer = SchemaPublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        version = SchemaVersionService.publish_candidate(
            _tenant_id(request), _actor_id(request), pk, version_id,
            idempotency_key=_idempotency_key(request), correlation_id=_correlation_id(request),
        )
        return Response(EntitySchemaVersionDetailSerializer(version).data)

    @action(detail=True, methods=("post",), url_path=r"versions/(?P<version_id>[^/.]+)/reject")
    def reject_version(self, request, pk=None, version_id=None):
        version = SchemaVersionService.reject_candidate(
            _tenant_id(request), _actor_id(request), pk, version_id, str(request.data.get("reason", "")),
            correlation_id=_correlation_id(request),
        )
        return Response(EntitySchemaVersionDetailSerializer(version).data)

    @action(detail=True, methods=("post",), url_path=r"versions/(?P<version_id>[^/.]+)/rollback")
    def rollback_version(self, request, pk=None, version_id=None):
        version = SchemaVersionService.rollback_to_version(
            _tenant_id(request), _actor_id(request), pk, version_id,
            idempotency_key=_idempotency_key(request), correlation_id=_correlation_id(request),
        )
        return Response(EntitySchemaVersionDetailSerializer(version).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("get",), url_path="versions/diff")
    def diff_versions(self, request, pk=None):
        return Response(
            SchemaVersionService.diff_versions(
                _tenant_id(request), pk, request.query_params.get("from"), request.query_params.get("to")
            )
        )


class DynamicResourceViewSet(GovernedMetadataViewSet):
    access_map = RESOURCE_ACTION_ACCESS

    def get_queryset(self):
        return DynamicResourceService.list_resources(
            _tenant_id(self.request), entity_id=self.request.query_params.get("entity_id"),
            entity_code=self.request.query_params.get("entity_code"), state=self.request.query_params.get("state"),
            search=self.request.query_params.get("search"),
            created_after=_date_param(self.request, "created_after"),
            created_before=_date_param(self.request, "created_before"),
            ordering=self.request.query_params.get("ordering"),
        )

    def list(self, request):
        return self._page(self.get_queryset(), DynamicResourceListSerializer)

    def retrieve(self, request, pk=None):
        return Response(DynamicResourceDetailSerializer(DynamicResourceService.get_resource(_tenant_id(request), pk)).data)

    def create(self, request):
        serializer = DynamicResourceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if request.path.startswith("/api/v1/"):
            resource = DynamicResourceService.create_legacy_resource(
                _tenant_id(request), _actor_id(request), serializer.validated_data["entity_id"],
                serializer.validated_data["data"], correlation_id=_correlation_id(request),
            )
        else:
            resource = DynamicResourceService.create_resource(
                _tenant_id(request), _actor_id(request), serializer.validated_data["entity_id"],
                serializer.validated_data["data"], display_name=serializer.validated_data.get("display_name"),
                idempotency_key=_idempotency_key(request), correlation_id=_correlation_id(request),
            )
        return Response(DynamicResourceDetailSerializer(resource).data, status=status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        serializer = DynamicResourceReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current = DynamicResourceService.get_resource(_tenant_id(request), pk)
        expected = current.lock_version if request.path.startswith("/api/v1/") else _lock_version(request)
        resource = DynamicResourceService.replace_resource(
            _tenant_id(request), _actor_id(request), pk, serializer.validated_data["data"],
            expected_lock_version=expected, correlation_id=_correlation_id(request),
        )
        return Response(DynamicResourceDetailSerializer(resource).data)

    def partial_update(self, request, pk=None):
        serializer = DynamicResourcePatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resource = DynamicResourceService.patch_resource(
            _tenant_id(request), _actor_id(request), pk, serializer.validated_data.get("data", {}),
            expected_lock_version=_lock_version(request), correlation_id=_correlation_id(request),
        )
        return Response(DynamicResourceDetailSerializer(resource).data)

    def destroy(self, request, pk=None):
        current = DynamicResourceService.get_resource(_tenant_id(request), pk)
        expected = current.lock_version if request.path.startswith("/api/v1/") else _lock_version(request)
        resource = DynamicResourceService.soft_delete_resource(
            _tenant_id(request), _actor_id(request), pk, expected_lock_version=expected,
            correlation_id=_correlation_id(request),
        )
        return Response({"operation": "delete", "status": "completed", "id": str(resource.id)})

    @action(detail=True, methods=("post",))
    def restore(self, request, pk=None):
        resource = DynamicResourceService.restore_resource(
            _tenant_id(request), _actor_id(request), pk, correlation_id=_correlation_id(request)
        )
        return Response(DynamicResourceDetailSerializer(resource).data)

    @action(detail=True, methods=("post",))
    def duplicate(self, request, pk=None):
        resource = DynamicResourceService.duplicate_resource(
            _tenant_id(request), _actor_id(request), pk, correlation_id=_correlation_id(request)
        )
        return Response(DynamicResourceDetailSerializer(resource).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("post",))
    def submit(self, request, pk=None):
        serializer = ResourceTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resource = DynamicResourceService.submit_resource(
            _tenant_id(request), _actor_id(request), pk, expected_lock_version=_lock_version(request),
            idempotency_key=_idempotency_key(request), correlation_id=_correlation_id(request),
        )
        return Response(DynamicResourceDetailSerializer(resource).data)

    @action(detail=True, methods=("post",))
    def cancel(self, request, pk=None):
        serializer = ResourceTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resource = DynamicResourceService.cancel_resource(
            _tenant_id(request), _actor_id(request), pk, serializer.validated_data.get("reason", ""),
            expected_lock_version=_lock_version(request), idempotency_key=_idempotency_key(request),
            correlation_id=_correlation_id(request),
        )
        return Response(DynamicResourceDetailSerializer(resource).data)

    @action(detail=True, methods=("get",), url_path="versions")
    def versions(self, request, pk=None):
        return self._page(DynamicResourceService.list_resource_versions(_tenant_id(request), pk), DynamicResourceVersionSerializer)

    @action(detail=True, methods=("get",), url_path=r"versions/(?P<version>[^/.]+)")
    def version_detail(self, request, pk=None, version=None):
        try:
            item = DynamicResourceVersion.objects.for_tenant(_tenant_id(request)).get(resource_id=pk, version=version)
        except DynamicResourceVersion.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("Resource version not found.")
        return Response(DynamicResourceVersionSerializer(item).data)


class NamingSequenceViewSet(
    GovernedMetadataViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin
):
    access_map = SEQUENCE_ACTION_ACCESS

    def get_queryset(self):
        queryset = NamingSequence.objects.for_tenant(_tenant_id(self.request)).select_related("entity_definition")
        if self.request.query_params.get("entity_id"):
            queryset = queryset.filter(entity_definition_id=self.request.query_params["entity_id"])
        if self.request.query_params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=self.request.query_params["is_active"] == "true")
        return queryset

    def list(self, request):
        return self._page(self.get_queryset(), NamingSequenceSerializer)

    def retrieve(self, request, pk=None):
        try:
            sequence = self.get_queryset().get(pk=pk)
        except NamingSequence.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("Naming sequence not found.")
        return Response(NamingSequenceSerializer(sequence).data)

    @action(detail=True, methods=("post",))
    def reset(self, request, pk=None):
        serializer = SequenceResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sequence = NamingService.reset_sequence(
            _tenant_id(request), _actor_id(request), pk, serializer.validated_data["next_value"],
            correlation_id=_correlation_id(request),
        )
        return Response(NamingSequenceSerializer(sequence).data)

    @action(detail=False, methods=("post",))
    def preview(self, request):
        entity = EntityDefinitionService.get_definition(_tenant_id(request), request.data.get("entity_id"))
        data = request.data.get("data", {})
        if not isinstance(data, dict):
            raise ValidationError({"data": [{"code": "INVALID_OBJECT", "message": "Data must be an object."}]})
        return Response(NamingService.preview_record_key(_tenant_id(request), entity, data))


class MetadataConfigurationViewSet(GovernedMetadataViewSet):
    """Runtime configuration UI/API surface with preview and reversible history."""

    access_map = CONFIG_ACTION_ACCESS

    def _environment(self, request) -> str:
        return str(request.query_params.get("environment", "production"))

    def list(self, request):
        config = MetadataConfigurationService.ensure_configuration(
            _tenant_id(request),
            _actor_id(request),
            self._environment(request),
            correlation_id=_correlation_id(request),
        )
        return Response(MetadataConfigurationSerializer(config).data)

    def update(self, request):
        serializer = MetadataConfigurationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        config = MetadataConfigurationService.update_configuration(
            _tenant_id(request), _actor_id(request), self._environment(request), serializer.validated_data,
            expected_version=_lock_version(request), correlation_id=_correlation_id(request),
        )
        return Response(MetadataConfigurationSerializer(config).data)

    def preview(self, request):
        payload = request.data.get("values", request.data) if isinstance(request.data, dict) else request.data
        serializer = MetadataConfigurationWriteSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return Response(
            MetadataConfigurationService.preview_configuration(
                _tenant_id(request), self._environment(request), serializer.validated_data
            )
        )

    def versions(self, request):
        return self._page(
            MetadataConfigurationService.list_history(_tenant_id(request), self._environment(request)),
            MetadataConfigurationAuditSerializer,
        )

    def rollback(self, request, version=None):
        config = MetadataConfigurationService.rollback_configuration(
            _tenant_id(request), _actor_id(request), self._environment(request), int(version),
            correlation_id=_correlation_id(request),
        )
        return Response(MetadataConfigurationSerializer(config).data)

    def import_config(self, request):
        if not isinstance(request.data, dict):
            raise ValidationError({"document": [{"code": "INVALID_OBJECT", "message": "Document must be an object."}]})
        document = request.data.get("document", request.data)
        if not isinstance(document, dict):
            raise ValidationError({"document": [{"code": "INVALID_OBJECT", "message": "Document must be an object."}]})
        if request.data.get("validate_only"):
            checksum = document.get("checksum")
            body = {key: value for key, value in document.items() if key != "checksum"}
            from .services import _schema_hash
            if checksum != _schema_hash(body):
                raise ValidationError({"checksum": [{"code": "CHECKSUM_MISMATCH", "message": "Checksum is invalid."}]})
            values = document.get("values")
            if not isinstance(values, dict):
                raise ValidationError({"document": [{"code": "MALFORMED_DOCUMENT", "message": "Values are required."}]})
            return Response(
                MetadataConfigurationService.preview_configuration(
                    _tenant_id(request), self._environment(request), values
                )
            )
        config = MetadataConfigurationService.import_configuration(
            _tenant_id(request), _actor_id(request), document, correlation_id=_correlation_id(request)
        )
        return Response(MetadataConfigurationSerializer(config).data)

    def export_config(self, request):
        return Response(MetadataConfigurationService.export_configuration(_tenant_id(request), self._environment(request)))

class MetadataHealthView(GovernedAPIViewMixin, APIView):
    authentication_classes = (RelaxedCsrfSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    required_permission = HEALTH_ACTION_ACCESS["health"].permission
    required_entitlement = HEALTH_ACTION_ACCESS["health"].entitlement
    quota_resource = HEALTH_ACTION_ACCESS["health"].quota_resource

    def get(self, request):
        tenant_id = _tenant_id(request)
        checks = {"database": "ok", "cache": "ok", "outbox": "ok"}
        overall = "healthy"
        try:
            # A tenant-bounded ORM query proves the active context without leaking counts.
            EntityDefinitionService.list_definitions(tenant_id).values_list("id", flat=True).first()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            checks["database"] = "unavailable"
            overall = "unhealthy"
        nonce_key = f"metadata-health:{tenant_id}:{uuid.uuid4()}"
        try:
            cache.set(nonce_key, "ok", timeout=5)
            if cache.get(nonce_key) != "ok":
                raise RuntimeError("cache nonce mismatch")
            cache.delete(nonce_key)
        except Exception:
            checks["cache"] = "unavailable"
            overall = "degraded" if overall == "healthy" else overall
        try:
            OutboxEvent = __import__("src.core.async_jobs.models", fromlist=["OutboxEvent"]).OutboxEvent
            OutboxEvent.objects.for_tenant(tenant_id).values_list("id", flat=True).first()
        except Exception:
            checks["outbox"] = "unavailable"
            overall = "unhealthy"
        response_status = status.HTTP_200_OK if overall == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
        response = Response({"status": overall, "module": "metadata-modeling", "checks": checks}, status=response_status)
        response["X-Correlation-ID"] = _correlation_id(request)
        return response
