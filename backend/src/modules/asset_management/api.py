"""Tenant-isolated API controllers for Asset Management."""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db.models import QuerySet
from rest_framework import filters, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from src.core.views.tenant_scoped import TenantScopedModelViewSet, TenantScopedReadOnlyModelViewSet

from .models import Asset, AssetCategory, DepreciationEntry
from .permissions import IsAssetUser, IsDepreciationReader
from .serializers import (
    AssetDetailSerializer,
    AssetListSerializer,
    AssetUpdateSerializer,
    AssetWriteSerializer,
    DepreciationCalculationSerializer,
    DepreciationEntrySerializer,
)
from .services import AssetService, DepreciationService

logger = logging.getLogger("saraise.asset_management")


class AssetPagination(PageNumberPagination):
    """Bounded pagination shared by asset and history collections."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class StrictSessionAuthentication(SessionAuthentication):
    """Enforce Django's CSRF validation and advertise a 401 challenge."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class TenantAssetRateThrottle(SimpleRateThrottle):
    """Bound traffic independently for each authenticated tenant."""

    scope = "asset_management"
    rate = "240/minute"

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
                    "correlation_id": correlation_id or "unavailable",
                    "error_code": str(response.data["error_code"]),
                    "status_code": response.status_code,
                    "view": type(self).__name__,
                    "action": getattr(self, "action", "unknown"),
                },
            )
        return response


class AssetViewSet(DomainErrorMixin, TenantScopedModelViewSet):
    """Asset CRUD with service-owned writes and soft deletion."""

    queryset = Asset.objects.all()
    authentication_classes = (StrictSessionAuthentication,)
    permission_classes = (IsAuthenticated, IsAssetUser)
    throttle_classes = (TenantAssetRateThrottle,)
    pagination_class = AssetPagination
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("asset_code", "asset_name", "location")
    ordering_fields = ("asset_code", "asset_name", "purchase_date", "purchase_cost", "current_value", "created_at")
    ordering = ("asset_code",)

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
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

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


class DepreciationEntryViewSet(DomainErrorMixin, TenantScopedReadOnlyModelViewSet):
    """Read-only access to the immutable depreciation ledger."""

    queryset = DepreciationEntry.objects.select_related("asset").all()
    serializer_class = DepreciationEntrySerializer
    authentication_classes = (StrictSessionAuthentication,)
    permission_classes = (IsAuthenticated, IsDepreciationReader)
    throttle_classes = (TenantAssetRateThrottle,)
    pagination_class = AssetPagination
    filter_backends = (filters.OrderingFilter,)
    ordering_fields = ("entry_date", "depreciation_amount", "book_value", "created_at")
    ordering = ("-entry_date", "-created_at")

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


__all__ = ["AssetViewSet", "DepreciationEntryViewSet"]
