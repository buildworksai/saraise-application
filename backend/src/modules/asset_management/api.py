"""Tenant-isolated API controllers for Asset Management."""

from __future__ import annotations

import logging
from datetime import date
from uuid import NAMESPACE_URL, UUID, uuid5

from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db.models import QuerySet
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from src.core.views.tenant_scoped import TenantScopedModelViewSet, TenantScopedReadOnlyModelViewSet

from .api_auth import StrictSessionAuthentication
from .health import AssetHealthUnavailable, get_module_health
from .models import Asset, AssetCategory, AssetManagementConfiguration, DepreciationEntry
from .permissions import (
    ASSET_CREATE,
    ASSET_DELETE,
    ASSET_ACTIVATE,
    ASSET_DEACTIVATE,
    ASSET_READ,
    ASSET_UPDATE,
    CONFIGURATION_EXPORT,
    CONFIGURATION_IMPORT,
    CONFIGURATION_READ,
    CONFIGURATION_ROLLBACK,
    CONFIGURATION_UPDATE,
    DEPRECIATION_READ,
    HEALTH_ACTION_PERMISSIONS,
    ActionAccessMixin,
    AssetAccessMixin,
)
from .serializers import (
    AssetConfigurationSerializer,
    AssetConfigurationVersionSerializer,
    AssetDetailSerializer,
    AssetListSerializer,
    AssetUpdateSerializer,
    AssetWriteSerializer,
    ConfigurationDocumentSerializer,
    ConfigurationImportSerializer,
    ConfigurationRollbackSerializer,
    DepreciationCalculationSerializer,
    DepreciationEntrySerializer,
)
from .services import AssetConfigurationService, AssetService, DEFAULT_CONFIGURATION, DepreciationService

logger = logging.getLogger("saraise.asset_management")


class AssetPagination(PageNumberPagination):
    """Bounded pagination shared by asset and history collections."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset: QuerySet[object], request: object, view: object | None = None) -> list[object] | None:
        tenant = TenantAssetRateThrottle._tenant_id(request)
        if tenant:
            configuration = AssetConfigurationService().resolve(tenant)
            self.page_size = int(configuration["asset_list_page_size"])
            self.max_page_size = int(configuration["asset_list_max_page_size"])
        return super().paginate_queryset(queryset, request, view)


class TenantAssetRateThrottle(SimpleRateThrottle):
    """Bound traffic independently for each authenticated tenant."""

    scope = "asset_management"
    rate = None

    def get_rate(self) -> str:
        return str(DEFAULT_CONFIGURATION["tenant_throttle_rate"])

    def allow_request(self, request: object, view: object) -> bool:
        tenant = self._tenant_id(request)
        if not tenant:
            raise APIException("Tenant policy context is required for throttling.")
        try:
            self.rate = str(AssetConfigurationService().resolve(tenant)["tenant_throttle_rate"])
            self.num_requests, self.duration = self.parse_rate(self.rate)
        except Exception as exc:
            logger.exception("asset.throttle_configuration_unavailable", extra={"event": "asset.throttle_configuration_unavailable"})
            raise APIException("Asset Management throttle configuration is unavailable.") from exc
        return super().allow_request(request, view)

    @staticmethod
    def _tenant_id(request: object | None) -> UUID | None:
        user = getattr(request, "user", None)
        try:
            value = user.profile.tenant_id
            return UUID(str(value)) if value else None
        except (AttributeError, ObjectDoesNotExist, TypeError, ValueError):
            return None

    def get_cache_key(self, request: object, view: object) -> str | None:
        del view
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
        try:
            profile = user.profile
        except (AttributeError, ObjectDoesNotExist):
            profile = None
        tenant_id = getattr(profile, "tenant_id", None)
        if not tenant_id:
            return self.cache_format % {"scope": self.scope, "ident": f"user:{user.pk}"}
        return self.cache_format % {"scope": self.scope, "ident": f"tenant:{tenant_id}"}


def _date_filter(value: object, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: "Use an ISO-8601 date (YYYY-MM-DD)."}) from exc


def _boolean_filter(value: object, field: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise ValidationError({field: "Use true or false."})


def _correlation_id(request: object) -> str | None:
    value = getattr(request, "correlation_id", None) or getattr(request, "headers", {}).get("X-Correlation-ID")
    return str(value) if value else None


def _idempotency_key(request: object) -> str | None:
    return getattr(request, "headers", {}).get("Idempotency-Key")


def _require_idempotency_key(request: object) -> str:
    value = _idempotency_key(request)
    if not value or not str(value).strip():
        raise ValidationError({"Idempotency-Key": "This header is required for asset mutations."})
    return str(value).strip()


def _actor_id(request: object) -> UUID:
    value = getattr(getattr(request, "user", None), "id", None)
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return uuid5(NAMESPACE_URL, f"saraise:user:{value}")


class DomainErrorMixin:
    """Translate Django domain errors into stable client-visible failures."""

    def handle_exception(self, exc: Exception) -> Response:
        error_code = getattr(exc, "domain_code", None)
        if isinstance(exc, ObjectDoesNotExist):
            exc = NotFound()
            error_code = "NOT_FOUND"
        elif isinstance(exc, DjangoValidationError):
            detail = (
                getattr(exc, "message_dict", None)
                or getattr(exc, "messages", None)
                or {"non_field_errors": ["The operation could not be completed."]}
            )
            exc = ValidationError(detail)
            error_code = error_code or "VALIDATION_ERROR"
        response = super().handle_exception(exc)  # type: ignore[misc]
        if response.status_code >= 400 and isinstance(response.data, dict):
            response.data.setdefault("error_code", error_code or getattr(exc, "default_code", "REQUEST_FAILED"))
            correlation_id = _correlation_id(self.request)
            if correlation_id:
                response.data.setdefault("correlation_id", correlation_id)
            logger.warning(
                "asset.request_failed",
                extra={
                    "event": "asset.request_failed",
                    "correlation_id": correlation_id or "missing-context",
                    "error_code": str(response.data["error_code"]),
                    "status_code": response.status_code,
                    "view": type(self).__name__,
                    "action": getattr(self, "action", "unknown"),
                },
            )
        return response


class AssetViewSet(DomainErrorMixin, AssetAccessMixin, TenantScopedModelViewSet):
    """Asset CRUD with service-owned writes and soft deletion."""

    queryset = Asset.objects.all()
    throttle_classes = (TenantAssetRateThrottle,)
    pagination_class = AssetPagination
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("asset_code", "asset_name", "location")
    ordering_fields = ("asset_code", "asset_name", "purchase_date", "purchase_cost", "current_value", "created_at")
    ordering = ("asset_code",)
    action_permissions = {
        "list": ASSET_READ,
        "retrieve": ASSET_READ,
        "create": ASSET_CREATE,
        "update": ASSET_UPDATE,
        "partial_update": ASSET_UPDATE,
        "destroy": ASSET_DELETE,
        "calculate_depreciation": ASSET_UPDATE,
        "activate": ASSET_ACTIVATE,
        "deactivate": ASSET_DEACTIVATE,
    }

    def get_queryset(self) -> QuerySet[Asset]:
        queryset = super().get_queryset().filter(is_deleted=False)
        params = self.request.query_params
        category = params.get("category")
        if category:
            valid = {choice for choice, _label in AssetCategory.choices}
            if category not in valid:
                raise ValidationError({"category": "Unsupported asset category."})
            queryset = queryset.filter(category=category)
        if params.get("is_active") not in (None, ""):
            queryset = queryset.filter(is_active=_boolean_filter(params["is_active"], "is_active"))
        if params.get("purchase_date_after"):
            queryset = queryset.filter(
                purchase_date__gte=_date_filter(params["purchase_date_after"], "purchase_date_after")
            )
        if params.get("purchase_date_before"):
            queryset = queryset.filter(
                purchase_date__lte=_date_filter(params["purchase_date_before"], "purchase_date_before")
            )
        return queryset

    def get_serializer_class(self) -> type:
        if self.action == "list":
            return AssetListSerializer
        if self.action == "create":
            return AssetWriteSerializer
        if self.action in {"update", "partial_update"}:
            return AssetUpdateSerializer
        if self.action == "calculate_depreciation":
            return DepreciationCalculationSerializer
        return AssetDetailSerializer

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = AssetWriteSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        asset = AssetService.create_asset(
            self._require_tenant_id(),
            correlation_id=_correlation_id(self.request),
            idempotency_key=_require_idempotency_key(self.request),
            **serializer.validated_data,
        )
        response = Response(AssetDetailSerializer(asset).data, status=status.HTTP_201_CREATED)
        response["Location"] = f"{self.request.path}{asset.pk}/"
        return response

    def update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        asset = self.get_object()
        serializer = AssetUpdateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        updated = AssetService.update_asset(
            self._require_tenant_id(),
            asset.pk,
            serializer.validated_data,
            correlation_id=_correlation_id(self.request),
            idempotency_key=_require_idempotency_key(self.request),
        )
        return Response(AssetDetailSerializer(updated).data)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        return self.update(request, *args, **kwargs)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        asset = self.get_object()
        AssetService.delete_asset(
            self._require_tenant_id(),
            asset.pk,
            correlation_id=_correlation_id(self.request),
            idempotency_key=_require_idempotency_key(self.request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def activate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        asset = self.get_object()
        updated = AssetService.set_active_state(
            self._require_tenant_id(), asset.pk, is_active=True, correlation_id=_correlation_id(self.request), idempotency_key=_require_idempotency_key(self.request)
        )
        return Response(AssetDetailSerializer(updated).data)

    @action(detail=True, methods=("post",))
    def deactivate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        asset = self.get_object()
        updated = AssetService.set_active_state(
            self._require_tenant_id(), asset.pk, is_active=False, correlation_id=_correlation_id(self.request), idempotency_key=_require_idempotency_key(self.request)
        )
        return Response(AssetDetailSerializer(updated).data)

    @action(detail=True, methods=("post",), url_path="calculate-depreciation")
    def calculate_depreciation(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        asset = self.get_object()
        serializer = DepreciationCalculationSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        entry = DepreciationService.calculate_depreciation(
            self._require_tenant_id(),
            asset.pk,
            serializer.validated_data["entry_date"],
            correlation_id=_correlation_id(self.request),
        )
        return Response(DepreciationEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class DepreciationEntryViewSet(DomainErrorMixin, AssetAccessMixin, TenantScopedReadOnlyModelViewSet):
    """Read-only access to the immutable depreciation ledger."""

    queryset = DepreciationEntry.objects.select_related("asset").all()
    serializer_class = DepreciationEntrySerializer
    throttle_classes = (TenantAssetRateThrottle,)
    pagination_class = AssetPagination
    filter_backends = (filters.OrderingFilter,)
    ordering_fields = ("entry_date", "depreciation_amount", "book_value", "created_at")
    ordering = ("-entry_date", "-created_at")
    action_permissions = {None: DEPRECIATION_READ, "list": DEPRECIATION_READ, "retrieve": DEPRECIATION_READ}

    def get_queryset(self) -> QuerySet[DepreciationEntry]:
        queryset = super().get_queryset()
        params = self.request.query_params
        asset_id = params.get("asset_id")
        if asset_id:
            try:
                asset_uuid = UUID(str(asset_id))
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValidationError({"asset_id": "Use a valid UUID."}) from exc
            queryset = queryset.filter(asset_id=asset_uuid)
        if params.get("entry_date_after"):
            queryset = queryset.filter(entry_date__gte=_date_filter(params["entry_date_after"], "entry_date_after"))
        if params.get("entry_date_before"):
            queryset = queryset.filter(entry_date__lte=_date_filter(params["entry_date_before"], "entry_date_before"))
        return queryset


class AssetConfigurationViewSet(DomainErrorMixin, AssetAccessMixin, TenantScopedReadOnlyModelViewSet):
    """Tenant configuration API used by the UI and configuration-as-code."""

    queryset = AssetManagementConfiguration.objects.all()
    serializer_class = AssetConfigurationSerializer
    throttle_classes = (TenantAssetRateThrottle,)
    pagination_class = AssetPagination
    action_permissions = {
        "list": CONFIGURATION_READ,
        "current": CONFIGURATION_READ,
        "update_configuration": CONFIGURATION_UPDATE,
        "preview": CONFIGURATION_UPDATE,
        "history": CONFIGURATION_READ,
        "rollback": CONFIGURATION_ROLLBACK,
        "import_document": CONFIGURATION_IMPORT,
        "export_document": CONFIGURATION_EXPORT,
    }

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = AssetConfigurationService().get_configuration(
            self._require_tenant_id(), _actor_id(self.request), _correlation_id(self.request)
        )
        return Response(AssetConfigurationSerializer(value).data)

    @action(detail=False, methods=("get",))
    def current(self, request: object) -> Response:
        value = AssetConfigurationService().get_configuration(
            self._require_tenant_id(), _actor_id(request), _correlation_id(request)
        )
        return Response(AssetConfigurationSerializer(value).data)

    @action(detail=False, methods=("put", "patch"), url_path="update")
    def update_configuration(self, request: object) -> Response:
        serializer = ConfigurationDocumentSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = AssetConfigurationService().update(
            self._require_tenant_id(),
            _actor_id(request),
            _correlation_id(request) or "",
            serializer.validated_data["document"],
        )
        return Response(AssetConfigurationSerializer(value).data)

    @action(detail=False, methods=("post",))
    def preview(self, request: object) -> Response:
        del request
        serializer = ConfigurationDocumentSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(AssetConfigurationService().preview(self._require_tenant_id(), serializer.validated_data["document"]))

    @action(detail=False, methods=("get",))
    def history(self, request: object) -> Response:
        del request
        page = self.paginate_queryset(AssetConfigurationService().history(self._require_tenant_id()))
        if page is None:
            return Response(AssetConfigurationVersionSerializer(AssetConfigurationService().history(self._require_tenant_id()), many=True).data)
        return self.get_paginated_response(AssetConfigurationVersionSerializer(page, many=True).data)

    @action(detail=False, methods=("post",))
    def rollback(self, request: object) -> Response:
        serializer = ConfigurationRollbackSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = AssetConfigurationService().rollback(
            self._require_tenant_id(),
            _actor_id(request),
            _correlation_id(request) or "",
            serializer.validated_data["version"],
        )
        return Response(AssetConfigurationSerializer(value).data)

    @action(detail=False, methods=("post",), url_path="import")
    def import_document(self, request: object) -> Response:
        serializer = ConfigurationImportSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        value = AssetConfigurationService().import_document(
            self._require_tenant_id(),
            _actor_id(request),
            _correlation_id(request) or "",
            serializer.validated_data["configuration"],
        )
        return Response(AssetConfigurationSerializer(value).data)

    @action(detail=False, methods=("get",), url_path="export")
    def export_document(self, request: object) -> Response:
        del request
        return Response(AssetConfigurationService().export_document(self._require_tenant_id()))


class ModuleHealthAPIView(DomainErrorMixin, ActionAccessMixin, APIView):
    """Authenticated and explicitly authorized module health endpoint."""

    action_permissions = HEALTH_ACTION_PERMISSIONS
    action = "health"

    def get(self, request: object) -> Response:
        try:
            return Response(get_module_health(_correlation_id(request)), status=status.HTTP_200_OK)
        except AssetHealthUnavailable:
            return Response(
                {
                    "status": "unhealthy",
                    "module": "asset_management",
                    "error_code": "DATABASE_UNAVAILABLE",
                    "message": "Asset Management database connectivity is unavailable.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


__all__ = ["AssetConfigurationViewSet", "AssetViewSet", "DepreciationEntryViewSet", "ModuleHealthAPIView"]
