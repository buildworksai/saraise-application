"""Governed, tenant-isolated Integration Platform API v2 endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Count, Q, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import mixins, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from src.core.access import RequiresAccess
from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination, OperationFailed, OperationResult
from src.core.views.tenant_scoped import TenantScopedModelViewSet, TenantScopedReadOnlyModelViewSet

from .models import DataMapping, Integration, IntegrationCredential, Webhook, WebhookDelivery
from .permissions import (
    CONFIGURATION_ACTIONS,
    CONNECTOR_ACTIONS,
    CREDENTIAL_ACTIONS,
    DELIVERY_ACTIONS,
    INTEGRATION_ACTIONS,
    INTEGRATION_CREDENTIAL_ACTIONS,
    MAPPING_ACTIONS,
    WEBHOOK_ACTIONS,
    AccessRequirement,
    InboundWebhookSignaturePermission,
)
from .serializers import (
    AsyncJobReceiptSerializer,
    AsyncJobStateSerializer,
    ConnectorDetailSerializer,
    ConnectorListSerializer,
    ConnectorSchemaSerializer,
    ConfigurationAuditSerializer,
    ConfigurationDocumentSerializer,
    ConfigurationPreviewSerializer,
    ConfigurationRollbackSerializer,
    ConfigurationSerializer,
    ConfigurationVersionSerializer,
    CredentialCreateSerializer,
    CredentialMetadataSerializer,
    CredentialRotateSerializer,
    DataMappingCreateSerializer,
    DataMappingDetailSerializer,
    DataMappingListSerializer,
    DataMappingUpdateSerializer,
    DeliveryRedriveSerializer,
    InboundWebhookSerializer,
    IntegrationCreateSerializer,
    IntegrationDetailSerializer,
    IntegrationListSerializer,
    IntegrationSyncRequestSerializer,
    IntegrationTestRequestSerializer,
    IntegrationUpdateSerializer,
    MappingPreviewSerializer,
    MappingValidateSerializer,
    TransitionRequestSerializer,
    WebhookCreateSerializer,
    WebhookDeliveryDetailSerializer,
    WebhookDeliveryListSerializer,
    WebhookDetailSerializer,
    WebhookListSerializer,
    WebhookSecretOnceSerializer,
    WebhookUpdateSerializer,
)
from .services import (
    INBOUND_NONCE_HEADER,
    INBOUND_SIGNATURE_HEADER,
    INBOUND_TIMESTAMP_HEADER,
    ConfigurationService,
    ConnectorService,
    CredentialService,
    DataMappingService,
    IntegrationService,
    WebhookService,
    durable_job_receipt,
    durable_job_state,
    runtime_configuration,
)
from .configuration import setting


class CanonicalSessionAuthentication(SessionAuthentication):
    """Standard CSRF-enforcing session auth with an explicit v2 challenge."""

    def authenticate_header(self, request: Request) -> str:
        del request
        return "Session"


class InboundWebhookThrottle(SimpleRateThrottle):
    """Bound public webhook transport requests by source and public endpoint."""

    rate = None
    view: object | None = None

    def allow_request(self, request: Request, view: object) -> bool:
        self.view = view
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)

    def get_rate(self) -> str | None:
        public_id = getattr(getattr(self, "view", None), "kwargs", {}).get("public_id")
        webhook = Webhook.objects.filter(public_id=public_id, is_deleted=False).only("tenant_id").first()
        if webhook is None:
            return None
        return str(setting(runtime_configuration(webhook.tenant_id), "webhooks.inbound_rate"))

    def get_cache_key(self, request: Request, view: object) -> str:
        ident = self.get_ident(request)
        public_id = getattr(view, "kwargs", {}).get("public_id", "unknown")
        return self.cache_format % {"scope": f"integration-webhook:{public_id}", "ident": ident}


def _tenant_from_request(request: Request) -> UUID:
    raw = getattr(request, "tenant_id", None)
    if raw is None:
        try:
            raw = getattr(request.user.profile, "tenant_id", None)
        except (AttributeError, ObjectDoesNotExist):
            raw = None
    try:
        if raw is None:
            raise ValueError
        return raw if isinstance(raw, UUID) else UUID(str(raw))
    except (AttributeError, TypeError, ValueError) as exc:
        raise PermissionDenied("Authenticated tenant context is required.") from exc


def _actor_id(request: Request) -> UUID:
    raw = getattr(request.user, "id", None)
    if isinstance(raw, UUID):
        return raw
    return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{raw}")


def _uuid(value: object, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValidationError({field: "Must be a valid UUID."}) from exc


def _service_value(value: Any) -> Any:
    """Unwrap governed service outcomes without manufacturing success."""

    if isinstance(value, OperationResult):
        return value.unwrap()
    return value


def _service_call(operation: Any) -> Any:
    """Translate domain persistence failures into stable public boundaries."""

    try:
        return _service_value(operation())
    except ObjectDoesNotExist as exc:
        raise NotFound() from exc
    except DjangoValidationError as exc:
        detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or {}
        raise ValidationError(detail) from exc
    except IntegrityError as exc:
        raise OperationFailed(
            error_code="IDEMPOTENCY_OR_UNIQUENESS_CONFLICT",
            message="The request conflicts with an existing resource or idempotency key.",
            http_status=status.HTTP_409_CONFLICT,
        ) from exc


def _job_payload(job: object) -> dict[str, object]:
    return durable_job_receipt(job)


def _job_state_payload(job: object) -> dict[str, object]:
    return durable_job_state(job)


def _parse_datetime_filter(value: str | None, field: str) -> datetime | None:
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValidationError({field: "Must be an ISO-8601 date-time."})
    return parsed


def _parse_boolean_filter(value: str | None, field: str) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise ValidationError({field: "Must be true or false."})


def _mapping_preview_payload(result: object) -> dict[str, object]:
    """Expose deterministic records and bounded per-record failures."""

    records = getattr(result, "records", None)
    failures = getattr(result, "failures", None)
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise OperationFailed(
            error_code="MAPPING_PREVIEW_UNAVAILABLE",
            message="The mapping preview result is invalid.",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if not isinstance(failures, Sequence) or isinstance(failures, (str, bytes)):
        raise OperationFailed(
            error_code="MAPPING_PREVIEW_UNAVAILABLE",
            message="The mapping preview result is invalid.",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return {
        "records": [dict(record) for record in records],
        "failures": [
            {
                "record_index": failure.record_index,
                "mapping_id": failure.mapping_id,
                "source_field": failure.source_field,
                "target_field": failure.target_field,
                "code": failure.code,
                "message": failure.message,
            }
            for failure in failures
        ],
    }


def _connector_health_payload(connector_id: UUID, result: OperationResult[Any]) -> dict[str, object]:
    """Normalize only health evidence that the registered adapter proved."""

    value = result.unwrap()
    if not isinstance(value, Mapping):
        raise OperationFailed(
            error_code="CONNECTOR_HEALTH_UNAVAILABLE",
            message="The adapter returned an invalid health result.",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    raw_status = value.get("status")
    if raw_status not in {"healthy", "degraded", "unavailable"}:
        if value.get("healthy") is True:
            raw_status = "healthy"
        elif value.get("healthy") is False:
            raw_status = "unavailable"
        else:
            raise OperationFailed(
                error_code="CONNECTOR_HEALTH_UNAVAILABLE",
                message="The adapter did not prove its health state.",
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
    raw_circuit = value.get("circuit_state", result.evidence.get("circuit_state"))
    circuit_state = (
        raw_circuit if raw_circuit in {"closed", "open", "half_open", "unavailable"} else "unavailable"
    )
    if raw_status == "healthy" and circuit_state != "closed":
        raw_status = "degraded"
    payload: dict[str, object] = {
        "connector_id": connector_id,
        "status": raw_status,
        "adapter_registered": True,
        "circuit_state": circuit_state,
        "checked_at": value.get("checked_at", timezone.now()),
    }
    reason = value.get("reason")
    if isinstance(reason, str) and reason:
        payload["reason"] = reason[:255]
    return payload


class GovernedAccessMixin:
    """Bind authenticated tenancy and deny-default action metadata."""

    authentication_classes = (CanonicalSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    pagination_class = GovernedPageNumberPagination
    access_by_action: Mapping[str, AccessRequirement] = {}

    def check_permissions(self, request: Request) -> None:
        if request.method.lower() not in self.http_method_names:
            raise MethodNotAllowed(request.method)
        try:
            request.tenant_id = _tenant_from_request(request)  # type: ignore[attr-defined]
        except PermissionDenied:
            pass
        requirement = self.access_by_action.get(getattr(self, "action", ""))
        if requirement is None:
            self.required_permission = None
            self.required_entitlement = None
            self.quota_resource = None
            self.quota_cost = 1
        else:
            self.required_permission = requirement.permission
            self.required_entitlement = requirement.entitlement
            self.quota_resource = requirement.quota_resource
            self.quota_cost = requirement.quota_cost
        super().check_permissions(request)  # type: ignore[misc]

    def permission_denied(self, request: Request, message: str | None = None, code: str | None = None) -> None:
        if request.authenticators and not request.successful_authenticator:
            super().permission_denied(request, message=message, code=code)  # type: ignore[misc]
        raise OperationFailed(
            error_code="PERMISSION_DENIED",
            message="You do not have permission to perform this action.",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    @property
    def tenant_id(self) -> UUID:
        return _tenant_from_request(self.request)

    @property
    def actor_id(self) -> UUID:
        return _actor_id(self.request)

    def _validate_query(self, allowed: set[str]) -> None:
        common = {"page", "page_size", "search", "ordering", "format"}
        unknown = set(self.request.query_params).difference(allowed, common)
        if unknown:
            raise ValidationError({key: "Unknown query parameter." for key in sorted(unknown)})

    def _paginate(self, values: Any, serializer_class: type[Any]) -> Response:
        page = self.paginate_queryset(values)
        serializer = serializer_class(
            page if page is not None else values, many=True, context={"request": self.request}
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class GovernedTenantModelViewSet(GovernedAccessMixin, GovernedAPIViewMixin, TenantScopedModelViewSet):
    """Mutable governed tenant base; subclasses override every mutation."""

    http_method_names = ("get", "post", "patch", "delete", "head", "options")


class GovernedTenantReadOnlyViewSet(GovernedAccessMixin, GovernedAPIViewMixin, TenantScopedReadOnlyModelViewSet):
    """Read-only governed tenant base."""

    http_method_names = ("get", "post", "head", "options")


class IntegrationPlatformConfigurationViewSet(
    GovernedAccessMixin,
    GovernedAPIViewMixin,
    viewsets.ViewSet,
):
    """Singleton-style tenant configuration API with immutable evidence."""

    http_method_names = ("get", "post", "head", "options")
    access_by_action = CONFIGURATION_ACTIONS
    service = ConfigurationService()

    def _environment(self, request: Request) -> str:
        return request.query_params.get("environment", "default")

    def list(self, request: Request) -> Response:
        payload = _service_call(lambda: self.service.get(self.tenant_id, self._environment(request)))
        return Response(ConfigurationSerializer(payload).data)

    @action(detail=False, methods=("get",), url_path="manage-capability")
    def manage_capability(self, request: Request) -> Response:
        """Return the RBAC decision proven by this action's access gate."""

        decision = getattr(request, "access_decision", None)
        return Response(
            {
                "allowed": bool(getattr(decision, "allowed", False)),
                "permission": CONFIGURATION_ACTIONS["manage_capability"].permission,
                "reason_code": str(getattr(decision, "reason_code", "DENY_DEFAULT")),
            }
        )

    def create(self, request: Request) -> Response:
        serializer = ConfigurationDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = _service_call(
            lambda: self.service.save(
                self.tenant_id,
                self.actor_id,
                serializer.validated_data["document"],
                environment=serializer.validated_data["environment"],
                correlation_id=getattr(request, "correlation_id", None),
            )
        )
        return Response(ConfigurationSerializer(payload).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=("post",))
    def preview(self, request: Request) -> Response:
        serializer = ConfigurationDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = _service_call(
            lambda: self.service.preview(
                self.tenant_id,
                serializer.validated_data["document"],
                serializer.validated_data["environment"],
            )
        )
        return Response(ConfigurationPreviewSerializer(payload).data)

    @action(detail=False, methods=("post",))
    def rollback(self, request: Request) -> Response:
        serializer = ConfigurationRollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = _service_call(
            lambda: self.service.rollback(
                self.tenant_id,
                self.actor_id,
                serializer.validated_data["version"],
                environment=serializer.validated_data["environment"],
                correlation_id=getattr(request, "correlation_id", None),
            )
        )
        return Response(ConfigurationSerializer(payload).data)

    @action(detail=False, methods=("post",), url_path="import")
    def import_document(self, request: Request) -> Response:
        serializer = ConfigurationDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = _service_call(
            lambda: self.service.save(
                self.tenant_id,
                self.actor_id,
                serializer.validated_data["document"],
                environment=serializer.validated_data["environment"],
                correlation_id=getattr(request, "correlation_id", None),
                action="import",
            )
        )
        return Response(ConfigurationSerializer(payload).data)

    @action(detail=False, methods=("get",))
    def export(self, request: Request) -> Response:
        payload = _service_call(lambda: self.service.get(self.tenant_id, self._environment(request)))
        return Response(
            {
                "schema_version": payload["document"]["schema_version"],
                "environment": payload["environment"],
                "version": payload["version"],
                "document": payload["document"],
            }
        )

    @action(detail=False, methods=("get",))
    def versions(self, request: Request) -> Response:
        values = _service_call(
            lambda: self.service.versions(self.tenant_id, self._environment(request))
        )
        return self._paginate(values, ConfigurationVersionSerializer)

    @action(detail=False, methods=("get",))
    def audits(self, request: Request) -> Response:
        values = _service_call(
            lambda: self.service.audits(self.tenant_id, self._environment(request))
        )
        return self._paginate(values, ConfigurationAuditSerializer)


class IntegrationViewSet(GovernedTenantModelViewSet):
    queryset = Integration.objects.filter(is_deleted=False)
    serializer_class = IntegrationDetailSerializer
    access_by_action = INTEGRATION_ACTIONS
    service = IntegrationService()

    def get_queryset(self) -> QuerySet[Integration]:
        self._validate_query({"status", "integration_type", "connector_id"})
        queryset = super().get_queryset().select_related("connector")
        if self.action == "list":
            queryset = queryset.annotate(
                credentials_count=Count("credentials", distinct=True),
                mappings_count=Count("mappings", filter=Q(mappings__is_deleted=False), distinct=True),
            )
        if value := self.request.query_params.get("status"):
            queryset = queryset.filter(status=value)
        if value := self.request.query_params.get("integration_type"):
            queryset = queryset.filter(integration_type=value)
        if value := self.request.query_params.get("connector_id"):
            queryset = queryset.filter(connector_id=_uuid(value, "connector_id"))
        if value := self.request.query_params.get("search", "").strip():
            queryset = queryset.filter(Q(name__icontains=value) | Q(description__icontains=value))
        policy = runtime_configuration(self.tenant_id)
        ordering = self.request.query_params.get("ordering", str(setting(policy, "list.integration_ordering")))
        fields = ordering.split(",")
        allowed = set(setting(policy, "list.integration_ordering_fields"))
        if any(field.lstrip("-") not in allowed for field in fields):
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return queryset.order_by(*fields, "id")

    def get_serializer_class(self) -> type[Any]:
        return {
            "list": IntegrationListSerializer,
            "create": IntegrationCreateSerializer,
            "partial_update": IntegrationUpdateSerializer,
        }.get(self.action, IntegrationDetailSerializer)

    def create(self, request: Request) -> Response:
        serializer = IntegrationCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        connector = values.pop("connector")
        values["connector_id"] = connector.id
        integration = _service_call(
            lambda: self.service.create(self.tenant_id, self.actor_id, values)
        )
        return Response(IntegrationDetailSerializer(integration).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        current = self.get_object()
        serializer = IntegrationUpdateSerializer(current, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        integration = _service_call(
            lambda: self.service.update(self.tenant_id, self.actor_id, _uuid(pk, "id"), dict(serializer.validated_data))
        )
        return Response(IntegrationDetailSerializer(integration).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        _service_call(lambda: self.service.soft_delete(self.tenant_id, self.actor_id, _uuid(pk, "id")))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def activate(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = TransitionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        integration = _service_call(
            lambda: self.service.activate(
                self.tenant_id, self.actor_id, _uuid(pk, "id"), serializer.validated_data["transition_key"]
            )
        )
        return Response(IntegrationDetailSerializer(integration).data)

    @action(detail=True, methods=("post",))
    def deactivate(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = TransitionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        integration = _service_call(
            lambda: self.service.deactivate(
                self.tenant_id, self.actor_id, _uuid(pk, "id"), serializer.validated_data["transition_key"]
            )
        )
        return Response(IntegrationDetailSerializer(integration).data)

    @action(detail=True, methods=("post",), url_path="test")
    def test_connection(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = IntegrationTestRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = _service_call(
            lambda: self.service.request_test(
                self.tenant_id, self.actor_id, _uuid(pk, "id"), serializer.validated_data["idempotency_key"]
            )
        )
        return Response(AsyncJobReceiptSerializer(_job_payload(job)).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=("post",))
    def sync(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = IntegrationSyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = _service_call(
            lambda: self.service.request_sync_governed(
                self.tenant_id,
                self.actor_id,
                _uuid(pk, "id"),
                serializer.validated_data["direction"],
                serializer.validated_data["mapping_ids"],
                serializer.validated_data["idempotency_key"],
            )
        )
        return Response(AsyncJobReceiptSerializer(_job_payload(job)).data, status=status.HTTP_202_ACCEPTED)

    @action(
        detail=True,
        methods=("get",),
        url_path=r"jobs/(?P<job_id>[0-9a-fA-F-]{36})",
    )
    def job(self, request: Request, pk: str | None = None, job_id: str | None = None) -> Response:
        del request
        self.get_object()
        job = _service_call(lambda: self.service.get_job(self.tenant_id, _uuid(pk, "id"), _uuid(job_id, "job_id")))
        return Response(AsyncJobStateSerializer(_job_state_payload(job)).data)


class NestedCredentialViewSet(
    GovernedAccessMixin,
    GovernedAPIViewMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet[Any],
):
    """Credential metadata/create surface nested under a tenant integration."""

    authentication_classes = (CanonicalSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    pagination_class = GovernedPageNumberPagination
    access_by_action = INTEGRATION_CREDENTIAL_ACTIONS
    serializer_class = CredentialMetadataSerializer
    service = CredentialService()
    http_method_names = ("get", "post", "head", "options")

    def integration_id(self) -> UUID:
        return _uuid(self.kwargs.get("integration_id"), "integration_id")

    def get_queryset(self) -> QuerySet[IntegrationCredential]:
        return (
            IntegrationCredential.objects.filter(tenant_id=self.tenant_id, integration_id=self.integration_id())
            .select_related("integration")
            .order_by("-created_at", "-version")
        )

    def list(self, request: Request, *args: object, **kwargs: object) -> Response:
        del args, kwargs
        values = _service_call(lambda: self.service.list_metadata(self.tenant_id, self.integration_id()))
        return self._paginate(values, CredentialMetadataSerializer)

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        del args, kwargs
        serializer = CredentialCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        credential = _service_call(
            lambda: self.service.create(
                self.tenant_id,
                self.actor_id,
                self.integration_id(),
                serializer.validated_data["credential_type"],
                serializer.validated_data["plaintext"],
                serializer.validated_data.get("expires_at"),
            )
        )
        return Response(CredentialMetadataSerializer(credential).data, status=status.HTTP_201_CREATED)


class IntegrationCredentialViewSet(GovernedTenantReadOnlyViewSet):
    queryset = IntegrationCredential.objects.all()
    serializer_class = CredentialMetadataSerializer
    access_by_action = CREDENTIAL_ACTIONS
    service = CredentialService()

    @action(detail=True, methods=("post",))
    def rotate(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = CredentialRotateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        credential = _service_call(
            lambda: self.service.rotate(
                self.tenant_id,
                self.actor_id,
                _uuid(pk, "id"),
                serializer.validated_data["plaintext"],
                serializer.validated_data["idempotency_key"],
                expires_at=serializer.validated_data.get("expires_at"),
            )
        )
        return Response(CredentialMetadataSerializer(credential).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("post",))
    def revoke(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = TransitionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        credential = _service_call(
            lambda: self.service.revoke(
                self.tenant_id, self.actor_id, _uuid(pk, "id"), serializer.validated_data["transition_key"]
            )
        )
        return Response(CredentialMetadataSerializer(credential).data)


class ConnectorViewSet(GovernedAccessMixin, GovernedAPIViewMixin, viewsets.GenericViewSet[Any]):
    """Tenant-evaluated descriptors for the platform-global connector catalog."""

    authentication_classes = (CanonicalSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    pagination_class = GovernedPageNumberPagination
    access_by_action = CONNECTOR_ACTIONS
    serializer_class = ConnectorDetailSerializer
    service = ConnectorService()
    http_method_names = ("get", "head", "options")

    def list(self, request: Request) -> Response:
        self._validate_query({"connector_type", "module_id", "is_active"})
        filters = {
            "connector_type": request.query_params.get("connector_type"),
            "module_id": request.query_params.get("module_id"),
            "is_active": _parse_boolean_filter(request.query_params.get("is_active"), "is_active"),
            "search": request.query_params.get("search", "").strip(),
        }
        values = _service_call(lambda: self.service.list_connectors(self.tenant_id, filters))
        return self._paginate(values, ConnectorListSerializer)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        del request
        connector = _service_call(lambda: self.service.get_connector(self.tenant_id, _uuid(pk, "id")))
        return Response(ConnectorDetailSerializer(connector).data)

    @action(detail=True, methods=("get",))
    def schema(self, request: Request, pk: str | None = None) -> Response:
        del request
        connector_id = _uuid(pk, "id")
        connector = _service_call(lambda: self.service.get_schema(self.tenant_id, connector_id))
        return Response(ConnectorSchemaSerializer({"connector_id": connector_id, **connector}).data)

    @action(detail=True, methods=("get",))
    def health(self, request: Request, pk: str | None = None) -> Response:
        del request
        connector_id = _uuid(pk, "id")
        result = self.service.adapter_health(self.tenant_id, connector_id)
        if not isinstance(result, OperationResult):
            raise OperationFailed(
                error_code="CONNECTOR_HEALTH_UNAVAILABLE",
                message="The connector health capability returned an invalid result.",
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(_connector_health_payload(connector_id, result))


class WebhookViewSet(GovernedTenantModelViewSet):
    queryset = Webhook.objects.filter(is_deleted=False)
    serializer_class = WebhookDetailSerializer
    access_by_action = WEBHOOK_ACTIONS
    service = WebhookService()

    def get_queryset(self) -> QuerySet[Webhook]:
        self._validate_query({"direction", "status", "event"})
        queryset = super().get_queryset()
        if self.action == "list":
            queryset = queryset.annotate(delivery_count=Count("deliveries"))
        if value := self.request.query_params.get("direction"):
            queryset = queryset.filter(direction=value)
        if value := self.request.query_params.get("status"):
            queryset = queryset.filter(status=value)
        if value := self.request.query_params.get("event"):
            queryset = queryset.filter(events__contains=[value])
        if value := self.request.query_params.get("search", "").strip():
            queryset = queryset.filter(Q(name__icontains=value) | Q(url__icontains=value))
        policy = runtime_configuration(self.tenant_id)
        ordering = self.request.query_params.get("ordering", str(setting(policy, "list.webhook_ordering")))
        fields = ordering.split(",")
        if any(field.lstrip("-") not in set(setting(policy, "list.webhook_ordering_fields")) for field in fields):
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return queryset.order_by(*fields, "id")

    def get_serializer_class(self) -> type[Any]:
        return {
            "list": WebhookListSerializer,
            "create": WebhookCreateSerializer,
            "partial_update": WebhookUpdateSerializer,
        }.get(self.action, WebhookDetailSerializer)

    @staticmethod
    def _secret_payload(result: object) -> dict[str, object]:
        if isinstance(result, tuple) and len(result) == 2:
            webhook, secret = result
        elif isinstance(result, Mapping):
            webhook = result.get("webhook", result)
            secret = result.get("signing_secret", result.get("secret"))
        else:
            webhook = getattr(result, "webhook", getattr(result, "record", result))
            secret = getattr(result, "signing_secret", getattr(result, "secret", None))
        if webhook is None or not isinstance(secret, str) or not secret:
            raise OperationFailed(
                error_code="SECRET_ISSUANCE_FAILED",
                message="The signing secret could not be issued safely.",
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return {
            "webhook": webhook,
            "signing_secret": secret,
            "shown_once": True,
        }

    def create(self, request: Request) -> Response:
        serializer = WebhookCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        result = _service_call(
            lambda: self.service.create(self.tenant_id, self.actor_id, dict(serializer.validated_data))
        )
        return Response(WebhookSecretOnceSerializer(self._secret_payload(result)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        current = self.get_object()
        serializer = WebhookUpdateSerializer(current, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        webhook = _service_call(
            lambda: self.service.update(self.tenant_id, self.actor_id, _uuid(pk, "id"), dict(serializer.validated_data))
        )
        return Response(WebhookDetailSerializer(webhook).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        _service_call(lambda: self.service.soft_delete(self.tenant_id, self.actor_id, _uuid(pk, "id")))
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _transition(self, request: Request, pk: str | None, operation: Any) -> Response:
        self.get_object()
        serializer = TransitionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        webhook = _service_call(
            lambda: operation(
                self.tenant_id, self.actor_id, _uuid(pk, "id"), serializer.validated_data["transition_key"]
            )
        )
        return Response(WebhookDetailSerializer(webhook).data)

    @action(detail=True, methods=("post",))
    def activate(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, pk, self.service.activate)

    @action(detail=True, methods=("post",))
    def deactivate(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, pk, self.service.deactivate)

    @action(detail=True, methods=("post",), url_path="rotate-secret")
    def rotate_secret(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = TransitionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = _service_call(
            lambda: self.service.rotate_secret(
                self.tenant_id, self.actor_id, _uuid(pk, "id"), serializer.validated_data["transition_key"]
            )
        )
        return Response(WebhookSecretOnceSerializer(self._secret_payload(result)).data)


class WebhookDeliveryViewSet(GovernedTenantReadOnlyViewSet):
    queryset = WebhookDelivery.objects.all()
    serializer_class = WebhookDeliveryDetailSerializer
    access_by_action = DELIVERY_ACTIONS
    service = WebhookService()

    def get_queryset(self) -> QuerySet[WebhookDelivery]:
        self._validate_query({"webhook_id", "status", "event", "created_after", "created_before"})
        queryset = super().get_queryset().select_related("webhook")
        if value := self.request.query_params.get("webhook_id"):
            queryset = queryset.filter(webhook_id=_uuid(value, "webhook_id"))
        if value := self.request.query_params.get("status"):
            queryset = queryset.filter(status=value)
        if value := self.request.query_params.get("event"):
            queryset = queryset.filter(event=value)
        if value := _parse_datetime_filter(self.request.query_params.get("created_after"), "created_after"):
            queryset = queryset.filter(created_at__gte=value)
        if value := _parse_datetime_filter(self.request.query_params.get("created_before"), "created_before"):
            queryset = queryset.filter(created_at__lte=value)
        ordering = str(setting(runtime_configuration(self.tenant_id), "list.delivery_ordering")).split(",")
        return queryset.order_by(*ordering)

    def get_serializer_class(self) -> type[Any]:
        return WebhookDeliveryListSerializer if self.action == "list" else WebhookDeliveryDetailSerializer

    @action(detail=True, methods=("post",))
    def redrive(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        serializer = DeliveryRedriveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delivery = _service_call(
            lambda: self.service.redrive_delivery(
                self.tenant_id, self.actor_id, _uuid(pk, "id"), serializer.validated_data["transition_key"]
            )
        )
        return Response(WebhookDeliveryDetailSerializer(delivery).data)


class DataMappingViewSet(GovernedTenantModelViewSet):
    queryset = DataMapping.objects.filter(is_deleted=False)
    serializer_class = DataMappingDetailSerializer
    access_by_action = MAPPING_ACTIONS
    service = DataMappingService()

    def get_queryset(self) -> QuerySet[DataMapping]:
        self._validate_query({"integration_id", "source_field", "target_field"})
        queryset = super().get_queryset().select_related("integration")
        if value := self.request.query_params.get("integration_id"):
            queryset = queryset.filter(integration_id=_uuid(value, "integration_id"))
        if value := self.request.query_params.get("source_field"):
            queryset = queryset.filter(source_field=value)
        if value := self.request.query_params.get("target_field"):
            queryset = queryset.filter(target_field=value)
        if value := self.request.query_params.get("search", "").strip():
            queryset = queryset.filter(
                Q(name__icontains=value) | Q(source_field__icontains=value) | Q(target_field__icontains=value)
            )
        policy = runtime_configuration(self.tenant_id)
        ordering = self.request.query_params.get("ordering", str(setting(policy, "list.mapping_ordering")))
        fields = ordering.split(",")
        if any(field.lstrip("-") not in set(setting(policy, "list.mapping_ordering_fields")) for field in fields):
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return queryset.order_by(*fields, "id")

    def get_serializer_class(self) -> type[Any]:
        return {
            "list": DataMappingListSerializer,
            "create": DataMappingCreateSerializer,
            "partial_update": DataMappingUpdateSerializer,
        }.get(self.action, DataMappingDetailSerializer)

    def create(self, request: Request) -> Response:
        serializer = DataMappingCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        integration_id = values.pop("integration_id")
        mapping = _service_call(lambda: self.service.create(self.tenant_id, self.actor_id, integration_id, values))
        return Response(DataMappingDetailSerializer(mapping).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        current = self.get_object()
        serializer = DataMappingUpdateSerializer(current, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        mapping = _service_call(
            lambda: self.service.update(self.tenant_id, self.actor_id, _uuid(pk, "id"), dict(serializer.validated_data))
        )
        return Response(DataMappingDetailSerializer(mapping).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        self.get_object()
        _service_call(lambda: self.service.soft_delete(self.tenant_id, self.actor_id, _uuid(pk, "id")))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=("post",), url_path="validate")
    def validate_mappings(self, request: Request) -> Response:
        serializer = MappingValidateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        result = _service_call(
            lambda: self.service.validate(
                self.tenant_id,
                values["integration_id"],
                values["mappings"],
                values["source_schema"],
                values["target_schema"],
            )
        )
        return Response(result)

    @action(detail=False, methods=("post",))
    def preview(self, request: Request) -> Response:
        serializer = MappingPreviewSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        result = _service_call(
            lambda: self.service.preview(
                self.tenant_id, values["integration_id"], values["mapping_ids"], values["sample"]
            )
        )
        return Response(_mapping_preview_payload(result))


class InboundWebhookView(GovernedAPIViewMixin, viewsets.ViewSet):
    """Public signed transport endpoint; authorization is verified in-service."""

    authentication_classes: tuple[type[Any], ...] = ()
    permission_classes = (InboundWebhookSignaturePermission,)
    throttle_classes = (InboundWebhookThrottle,)
    parser_classes: tuple[type[Any], ...] = ()
    service = WebhookService()
    http_method_names = ("post", "options")

    def create(self, request: Request, public_id: str | None = None) -> Response:
        validated_headers = {
            "timestamp": request.headers.get(INBOUND_TIMESTAMP_HEADER, ""),
            "nonce": request.headers.get(INBOUND_NONCE_HEADER, ""),
            "signature": request.headers.get(INBOUND_SIGNATURE_HEADER, ""),
        }
        serializer = InboundWebhookSerializer(data=validated_headers)
        serializer.is_valid(raise_exception=True)
        headers = {
            INBOUND_TIMESTAMP_HEADER: str(serializer.validated_data["timestamp"]),
            INBOUND_NONCE_HEADER: serializer.validated_data["nonce"],
            INBOUND_SIGNATURE_HEADER: serializer.validated_data["signature"],
        }
        result = _service_call(lambda: self.service.receive(_uuid(public_id, "public_id"), headers, request.body))
        receipt = _job_payload(result)
        return Response(
            {
                "job_id": receipt["job_id"],
                "correlation_id": receipt["correlation_id"],
                "accepted_at": receipt["accepted_at"],
            },
            status=status.HTTP_202_ACCEPTED,
        )


__all__ = [
    "CanonicalSessionAuthentication",
    "ConnectorViewSet",
    "DataMappingViewSet",
    "InboundWebhookThrottle",
    "InboundWebhookView",
    "IntegrationCredentialViewSet",
    "IntegrationPlatformConfigurationViewSet",
    "IntegrationViewSet",
    "NestedCredentialViewSet",
    "WebhookDeliveryViewSet",
    "WebhookViewSet",
]
