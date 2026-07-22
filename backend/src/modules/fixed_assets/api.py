"""Governed tenant-isolated API controllers for financial fixed assets."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Iterable
from uuid import UUID, uuid4

from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db.models import Count, Prefetch, Q, QuerySet, Subquery, Sum
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.api import CapabilityUnavailable as ApiCapabilityUnavailable
from src.core.api import GovernedAPIViewMixin, OperationFailed
from src.core.async_jobs.models import AsyncJob
from src.core.middleware.correlation import get_correlation_id
from src.core.state_machine import IdempotencyConflictError, StateMachineError

from .health import get_module_health
from .integrations import (
    AccountingPeriodClosed,
    AccountingPostingRejected,
    AccountMappingError,
    CapabilityUnavailable as IntegrationCapabilityUnavailable,
)
from .models import AssetCategory, AssetTransaction, DepreciationLine, DepreciationSchedule, FixedAsset
from .permissions import ActionAccessMixin
from .serializers import (
    ASSET_STATUSES,
    DEPRECIATION_METHODS,
    LINE_STATUSES,
    SCHEDULE_STATUSES,
    AssetCreateSerializer,
    AssetDetailSerializer,
    AssetDraftUpdateSerializer,
    AssetListSerializer,
    CapitalizeCommandSerializer,
    CategoryCreateSerializer,
    CategoryDetailSerializer,
    CategoryListSerializer,
    CategoryUpdateSerializer,
    DashboardSerializer,
    DepreciationLineDetailSerializer,
    DepreciationLineListSerializer,
    DisposalCommandSerializer,
    DuePostingSerializer,
    HealthResponseSerializer,
    ImpairmentCommandSerializer,
    JobStatusSerializer,
    LegacyFixedAssetSerializer,
    LegacyFixedAssetWriteSerializer,
    LifecyclePreviewSerializer,
    LinePostingSerializer,
    ScheduleCalculateSerializer,
    ScheduleCreateSerializer,
    ScheduleDetailSerializer,
    ScheduleListSerializer,
    ScheduleTransitionSerializer,
    ScheduleUpdateSerializer,
    TransactionDetailSerializer,
    TransactionListSerializer,
    TransferCommandSerializer,
)
from .services import (
    AssetCategoryService,
    AssetTransactionService,
    DepreciationService,
    FixedAssetService,
    FixedAssetServiceError,
    StaleVersionError,
)


def _ordering(value: object, allowed: set[str], default: str) -> str:
    ordering = str(value or default)
    if ordering.lstrip("-") not in allowed:
        raise ValidationError({"ordering": "Unsupported ordering field."})
    return ordering


def _boolean(value: object, field: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true"}:
        return True
    if normalized in {"0", "false"}:
        return False
    raise ValidationError({field: "Use true or false."})


def _as_date(value: object, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: "Use an ISO-8601 date (YYYY-MM-DD)."}) from exc


def _choice(value: object, field: str, choices: Iterable[str]) -> str:
    normalized = str(value)
    if normalized not in choices:
        raise ValidationError({field: "Unsupported filter value."})
    return normalized


class TenantGovernedViewSet(GovernedAPIViewMixin, ActionAccessMixin, viewsets.GenericViewSet):
    """Bind tenant, actor, pagination, and stable domain errors once."""

    def tenant_id(self) -> UUID:
        value = getattr(self.request, "tenant_id", None)
        try:
            tenant = value if isinstance(value, UUID) else UUID(str(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise PermissionDenied("Authenticated identity has no valid tenant.") from exc
        return tenant

    def actor_id(self) -> str:
        value = getattr(self.request.user, "id", None)
        if value is None:
            raise PermissionDenied("Authenticated identity has no valid actor.")
        return str(value)

    def correlation_id(self) -> str:
        value = getattr(self.request, "correlation_id", None) or get_correlation_id()
        if value:
            return str(value)
        generated = f"req_{uuid4().hex[:24]}"
        self.request.correlation_id = generated
        return generated

    def idempotency_key(self, *, required: bool = True) -> str:
        value = str(self.request.headers.get("Idempotency-Key", "")).strip()
        if required and not value:
            raise ValidationError({"Idempotency-Key": "This header is required."})
        if len(value) > 255:
            raise ValidationError({"Idempotency-Key": "Must not exceed 255 characters."})
        return value

    def paginated(self, queryset: QuerySet[Any] | Iterable[Any], serializer_class: type, **context: object) -> Response:
        requested_size = self.request.query_params.get("page_size")
        if requested_size not in (None, ""):
            try:
                parsed_size = int(str(requested_size))
            except (TypeError, ValueError) as exc:
                raise ValidationError({"page_size": "Use a positive integer."}) from exc
            if parsed_size <= 0:
                raise ValidationError({"page_size": "Use a positive integer."})
        page = self.paginate_queryset(queryset)
        if page is None:
            raise RuntimeError("Governed pagination is required.")
        serializer = serializer_class(page, many=True, context={"request": self.request, **context})
        return self.get_paginated_response(serializer.data)

    def scoped_object(self) -> object:
        """Resolve through a tenant-filtered queryset before every command."""

        return self.get_object()

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, IntegrationCapabilityUnavailable):
            exc = ApiCapabilityUnavailable(capability="accounting_finance")
        elif isinstance(exc, AccountingPeriodClosed):
            exc = OperationFailed(
                error_code=exc.code,
                message="The accounting period is closed.",
                http_status=status.HTTP_409_CONFLICT,
            )
        elif isinstance(exc, AccountMappingError):
            exc = OperationFailed(
                error_code=exc.code,
                message="The fixed-asset account mapping is incomplete or invalid.",
            )
        elif isinstance(exc, AccountingPostingRejected):
            exc = OperationFailed(
                error_code=exc.code,
                message="Accounting did not accept the posting request.",
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        elif isinstance(exc, IdempotencyConflictError):
            exc = OperationFailed(
                error_code="IDEMPOTENCY_CONFLICT",
                message="The idempotency key was already used for a different command.",
                http_status=status.HTTP_409_CONFLICT,
            )
        elif isinstance(exc, StaleVersionError):
            exc = OperationFailed(
                error_code=exc.domain_code,
                message="The resource changed; reload it before retrying.",
                detail={"expected_version": exc.expected, "actual_version": exc.actual},
                http_status=status.HTTP_409_CONFLICT,
            )
        elif isinstance(exc, FixedAssetServiceError):
            conflict_codes = {
                "ACTIVE_SCHEDULE_EXISTS",
                "ASSET_HAS_HISTORY",
                "ASSET_NOT_DRAFT",
                "CATEGORY_IN_USE_BY_DRAFT",
                "DISPOSAL_NOT_ALLOWED",
                "IMPAIRMENT_NOT_ALLOWED",
                "LINE_NOT_POSTABLE",
                "NO_TRANSFER_CHANGE",
                "NOT_FULLY_DEPRECIATED",
                "OPENING_VALUE_MISMATCH",
                "POSTING_ALREADY_REQUESTED",
                "POSTING_OUT_OF_ORDER",
                "SCHEDULE_NOT_DELETABLE",
                "SCHEDULE_NOT_DRAFT",
                "TRANSFER_NOT_ALLOWED",
            }
            exc = OperationFailed(
                error_code=exc.domain_code,
                message="The fixed-asset operation could not be completed.",
                http_status=(
                    status.HTTP_409_CONFLICT
                    if exc.domain_code in conflict_codes
                    else status.HTTP_422_UNPROCESSABLE_ENTITY
                ),
            )
        elif isinstance(exc, StateMachineError):
            exc = OperationFailed(
                error_code="STATE_CONFLICT",
                message="The requested lifecycle transition conflicts with the current state.",
                http_status=status.HTTP_409_CONFLICT,
            )
        elif isinstance(exc, DjangoValidationError):
            detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or {}
            exc = ValidationError(detail)
        elif isinstance(exc, ObjectDoesNotExist):
            exc = NotFound()
        return super().handle_exception(exc)


class AssetCategoryViewSet(TenantGovernedViewSet):
    """Category CRUD with deactivation instead of destructive deletion."""

    action_permissions = {
        "list": "fixed_asset.category:read",
        "retrieve": "fixed_asset.category:read",
        "create": "fixed_asset.category:create",
        "partial_update": "fixed_asset.category:update",
        "destroy": "fixed_asset.category:delete",
    }

    def get_queryset(self) -> QuerySet[AssetCategory]:
        queryset = AssetCategory.objects.for_tenant(self.tenant_id())
        params = self.request.query_params
        if params.get("is_active") not in (None, ""):
            queryset = queryset.filter(is_active=_boolean(params["is_active"], "is_active"))
        if params.get("method"):
            method = _choice(params["method"], "method", DEPRECIATION_METHODS)
            queryset = queryset.filter(default_depreciation_method=method)
        if params.get("search"):
            search = str(params["search"]).strip()
            queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search))
        ordering = _ordering(params.get("ordering"), {"code", "name", "created_at"}, "code")
        return queryset.order_by(ordering, "id")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), CategoryListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(CategoryDetailSerializer(self.get_object(), context={"request": self.request}).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = CategoryCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        category = AssetCategoryService.create_category(
            self.tenant_id(), self.actor_id(), dict(serializer.validated_data), self.idempotency_key()
        )
        return Response(CategoryDetailSerializer(category, context={"request": self.request}).data, status=201)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        category = self.scoped_object()
        serializer = CategoryUpdateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        updated = AssetCategoryService.update_category(
            self.tenant_id(), category.id, self.actor_id(), data, expected_version
        )
        return Response(CategoryDetailSerializer(updated, context={"request": self.request}).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        category = self.scoped_object()
        AssetCategoryService.deactivate_category(self.tenant_id(), category.id, self.actor_id())
        return Response(status=status.HTTP_204_NO_CONTENT)


class FixedAssetViewSet(TenantGovernedViewSet):
    """Financial asset register and lifecycle commands."""

    action_permissions = {
        "list": "fixed_asset.asset:read",
        "retrieve": "fixed_asset.asset:read",
        "create": "fixed_asset.asset:create",
        "partial_update": "fixed_asset.asset:update",
        "destroy": "fixed_asset.asset:delete",
        "capitalize": "fixed_asset.asset:capitalize",
        "transfer": "fixed_asset.asset:transfer",
        "impair": "fixed_asset.asset:impair",
        "dispose": "fixed_asset.asset:dispose",
        "transactions": "fixed_asset.transaction:read",
        "preview_capitalize": "fixed_asset.asset:capitalize",
        "preview_transfer": "fixed_asset.asset:transfer",
        "preview_impair": "fixed_asset.asset:impair",
        "preview_dispose": "fixed_asset.asset:dispose",
    }

    def get_queryset(self) -> QuerySet[FixedAsset]:
        # The subquery is constructed locally to keep every component visibly
        # tenant-qualified and avoid per-row next-period queries.
        from django.db.models import OuterRef

        next_period = (
            DepreciationLine.objects.for_tenant(self.tenant_id())
            .filter(asset_id=OuterRef("pk"), status__in=("planned", "posting"))
            .order_by("period_end", "id")
            .values("period_end")[:1]
        )
        queryset = (
            FixedAsset.objects.for_tenant(self.tenant_id())
            .select_related("category")
            .annotate(next_depreciation_date=Subquery(next_period))
        )
        params = self.request.query_params
        simple_filters = {
            "category_id": "category_id",
            "location": "location",
            "cost_center": "cost_center",
        }
        for parameter, field in simple_filters.items():
            if params.get(parameter) not in (None, ""):
                queryset = queryset.filter(**{field: params[parameter]})
        if params.get("status"):
            queryset = queryset.filter(status=_choice(params["status"], "status", ASSET_STATUSES))
        if params.get("method"):
            queryset = queryset.filter(
                depreciation_method=_choice(params["method"], "method", DEPRECIATION_METHODS)
            )
        if params.get("currency"):
            currency = str(params["currency"]).strip().upper()
            if len(currency) != 3 or not currency.isalpha():
                raise ValidationError({"currency": "Use a three-letter ISO-4217 currency code."})
            queryset = queryset.filter(currency=currency)
        if params.get("capitalized_from"):
            queryset = queryset.filter(
                capitalization_date__gte=_as_date(params["capitalized_from"], "capitalized_from")
            )
        if params.get("capitalized_to"):
            queryset = queryset.filter(capitalization_date__lte=_as_date(params["capitalized_to"], "capitalized_to"))
        if params.get("search"):
            search = str(params["search"]).strip()
            queryset = queryset.filter(
                Q(asset_code__icontains=search) | Q(asset_name__icontains=search) | Q(description__icontains=search)
            )
        ordering = _ordering(
            params.get("ordering"),
            {
                "asset_code",
                "asset_name",
                "purchase_date",
                "capitalization_date",
                "net_book_value",
                "created_at",
            },
            "asset_code",
        )
        if self.action == "retrieve":
            active = DepreciationSchedule.objects.for_tenant(self.tenant_id()).filter(status="active")
            queryset = queryset.prefetch_related(
                Prefetch("depreciation_schedules", queryset=active, to_attr="prefetched_active_schedules")
            )
        return queryset.order_by(ordering, "id")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), AssetListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(AssetDetailSerializer(self.get_object(), context={"request": self.request}).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = AssetCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        asset = FixedAssetService.create_asset(
            self.tenant_id(), self.actor_id(), dict(serializer.validated_data), self.idempotency_key()
        )
        return Response(AssetDetailSerializer(asset, context={"request": self.request}).data, status=201)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        asset = self.scoped_object()
        serializer = AssetDraftUpdateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        updated = FixedAssetService.update_draft(self.tenant_id(), asset.id, self.actor_id(), data, expected_version)
        return Response(AssetDetailSerializer(updated, context={"request": self.request}).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        asset = self.scoped_object()
        FixedAssetService.delete_draft(self.tenant_id(), asset.id, self.actor_id())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def capitalize(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        asset = self.scoped_object()
        serializer = CapitalizeCommandSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        updated = FixedAssetService.capitalize(
            self.tenant_id(),
            asset.id,
            self.actor_id(),
            serializer.validated_data["effective_date"],
            self.idempotency_key(),
            depreciation_start_date=serializer.validated_data.get("depreciation_start_date"),
            expected_version=serializer.validated_data["expected_version"],
        )
        return Response(AssetDetailSerializer(updated, context={"request": self.request}).data)

    @action(detail=True, methods=["post"])
    def transfer(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        asset = self.scoped_object()
        serializer = TransferCommandSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        updated = FixedAssetService.transfer(
            self.tenant_id(),
            asset.id,
            self.actor_id(),
            data["effective_date"],
            data.get("to_location", ""),
            data.get("to_cost_center", ""),
            self.idempotency_key(),
        )
        return Response(AssetDetailSerializer(updated, context={"request": self.request}).data)

    @action(detail=True, methods=["post"])
    def impair(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        asset = self.scoped_object()
        serializer = ImpairmentCommandSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        updated = FixedAssetService.record_impairment(
            self.tenant_id(),
            asset.id,
            self.actor_id(),
            data["effective_date"],
            data["recoverable_amount"],
            data["reason"],
            self.idempotency_key(),
        )
        return Response(AssetDetailSerializer(updated, context={"request": self.request}).data)

    @action(detail=True, methods=["post"])
    def dispose(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        asset = self.scoped_object()
        serializer = DisposalCommandSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        updated = FixedAssetService.dispose(
            self.tenant_id(),
            asset.id,
            self.actor_id(),
            data["effective_date"],
            data["proceeds"],
            data["reason"],
            self.idempotency_key(),
        )
        return Response(AssetDetailSerializer(updated, context={"request": self.request}).data)

    @action(detail=True, methods=["get"])
    def transactions(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        asset = self.scoped_object()
        history = AssetTransactionService.get_asset_history(self.tenant_id(), asset.id).order_by("-created_at", "-id")
        return self.paginated(history, TransactionListSerializer)

    def _preview(self, serializer_class: type, service_method: str) -> Response:
        asset = self.scoped_object()
        serializer = serializer_class(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        preview = getattr(FixedAssetService, service_method)(
            self.tenant_id(), asset.id, **dict(serializer.validated_data)
        )
        output = LifecyclePreviewSerializer(data=preview)
        output.is_valid(raise_exception=True)
        return Response(output.data)

    @action(detail=True, methods=["post"], url_path="preview-capitalize")
    def preview_capitalize(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._preview(CapitalizeCommandSerializer, "preview_capitalization")

    @action(detail=True, methods=["post"], url_path="preview-transfer")
    def preview_transfer(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._preview(TransferCommandSerializer, "preview_transfer")

    @action(detail=True, methods=["post"], url_path="preview-impair")
    def preview_impair(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._preview(ImpairmentCommandSerializer, "preview_impairment")

    @action(detail=True, methods=["post"], url_path="preview-dispose")
    def preview_dispose(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self._preview(DisposalCommandSerializer, "preview_disposal")


class DepreciationScheduleViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "fixed_asset.depreciation:read",
        "retrieve": "fixed_asset.depreciation:read",
        "create": "fixed_asset.depreciation:calculate",
        "partial_update": "fixed_asset.depreciation:calculate",
        "destroy": "fixed_asset.depreciation:calculate",
        "calculate": "fixed_asset.depreciation:calculate",
        "activate": "fixed_asset.depreciation:calculate",
        "supersede": "fixed_asset.depreciation:calculate",
    }

    def get_queryset(self) -> QuerySet[DepreciationSchedule]:
        queryset = DepreciationSchedule.objects.for_tenant(self.tenant_id()).select_related("asset")
        params = self.request.query_params
        for parameter, field in (("asset_id", "asset_id"),):
            if params.get(parameter) not in (None, ""):
                queryset = queryset.filter(**{field: params[parameter]})
        if params.get("status"):
            queryset = queryset.filter(status=_choice(params["status"], "status", SCHEDULE_STATUSES))
        if params.get("method"):
            queryset = queryset.filter(method=_choice(params["method"], "method", DEPRECIATION_METHODS))
        if params.get("start_from"):
            queryset = queryset.filter(start_date__gte=_as_date(params["start_from"], "start_from"))
        if params.get("start_to"):
            queryset = queryset.filter(start_date__lte=_as_date(params["start_to"], "start_to"))
        if self.action == "retrieve":
            lines = DepreciationLine.objects.for_tenant(self.tenant_id()).order_by("sequence", "id")
            queryset = queryset.prefetch_related(Prefetch("lines", queryset=lines, to_attr="prefetched_lines"))
        return queryset.order_by("-created_at", "-revision", "id")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), ScheduleListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(ScheduleDetailSerializer(self.get_object(), context={"request": self.request}).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = ScheduleCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        asset_id = data.pop("asset_id")
        if not FixedAsset.objects.for_tenant(self.tenant_id()).filter(pk=asset_id).exists():
            raise NotFound()
        schedule = DepreciationService.create_schedule_draft(
            self.tenant_id(), asset_id, self.actor_id(), data, self.idempotency_key()
        )
        return Response(ScheduleDetailSerializer(schedule, context={"request": self.request}).data, status=201)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        schedule = self.scoped_object()
        serializer = ScheduleUpdateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        updated = DepreciationService.update_schedule_draft(
            self.tenant_id(), schedule.id, self.actor_id(), data, expected_version
        )
        return Response(ScheduleDetailSerializer(updated, context={"request": self.request}).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        schedule = self.scoped_object()
        DepreciationService.delete_schedule_draft(self.tenant_id(), schedule.id, self.actor_id())
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def calculate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        schedule = self.scoped_object()
        serializer = ScheduleCalculateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        units_by_period = {
            item["period_start"].isoformat(): item["units_consumed"] for item in data.get("units_by_period", [])
        }
        calculated = DepreciationService.calculate_schedule(
            self.tenant_id(), schedule.id, self.actor_id(), units_by_period, self.idempotency_key()
        )
        return Response(ScheduleDetailSerializer(calculated, context={"request": self.request}).data)

    @action(detail=True, methods=["post"])
    def activate(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        schedule = self.scoped_object()
        serializer = ScheduleTransitionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        activated = DepreciationService.activate_schedule(
            self.tenant_id(), schedule.id, self.actor_id(), serializer.validated_data["transition_key"]
        )
        return Response(ScheduleDetailSerializer(activated, context={"request": self.request}).data)

    @action(detail=True, methods=["post"])
    def supersede(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        schedule = self.scoped_object()
        serializer = ScheduleTransitionSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        superseded = DepreciationService.supersede_schedule(
            self.tenant_id(), schedule.id, self.actor_id(), data.get("reason", ""), data["transition_key"]
        )
        return Response(ScheduleDetailSerializer(superseded, context={"request": self.request}).data)


class DepreciationLineViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "fixed_asset.depreciation:read",
        "retrieve": "fixed_asset.depreciation:read",
        "post": "fixed_asset.depreciation:post",
        "post_due": "fixed_asset.depreciation:post",
    }
    action_quotas = {
        "post": "fixed_assets.depreciation_postings",
        "post_due": "fixed_assets.depreciation_postings",
    }

    def get_queryset(self) -> QuerySet[DepreciationLine]:
        queryset = DepreciationLine.objects.for_tenant(self.tenant_id()).select_related("asset", "schedule")
        params = self.request.query_params
        for parameter, field in (("asset_id", "asset_id"), ("schedule_id", "schedule_id")):
            if params.get(parameter) not in (None, ""):
                queryset = queryset.filter(**{field: params[parameter]})
        if params.get("status"):
            queryset = queryset.filter(status=_choice(params["status"], "status", LINE_STATUSES))
        if params.get("period_from"):
            queryset = queryset.filter(period_end__gte=_as_date(params["period_from"], "period_from"))
        if params.get("period_to"):
            queryset = queryset.filter(period_start__lte=_as_date(params["period_to"], "period_to"))
        return queryset.order_by("period_end", "sequence", "id")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), DepreciationLineListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(DepreciationLineDetailSerializer(self.get_object(), context={"request": self.request}).data)

    @action(detail=True, methods=["post"])
    def post(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        line = self.scoped_object()
        serializer = LinePostingSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        job = DepreciationService.enqueue_line_posting(
            self.tenant_id(), line.id, self.actor_id(), self.idempotency_key(), self.correlation_id()
        )
        return Response(JobStatusSerializer(job).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"], url_path="post-due")
    def post_due(self, request: object) -> Response:
        del request
        serializer = DuePostingSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        job = DepreciationService.enqueue_due_posting(
            self.tenant_id(),
            serializer.validated_data["through_date"],
            self.actor_id(),
            self.idempotency_key(),
            self.correlation_id(),
        )
        return Response(JobStatusSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class AssetTransactionViewSet(mixins.RetrieveModelMixin, TenantGovernedViewSet):
    action_permissions = {"retrieve": "fixed_asset.transaction:read"}

    def get_queryset(self) -> QuerySet[AssetTransaction]:
        return AssetTransaction.objects.for_tenant(self.tenant_id()).select_related("asset")

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(TransactionDetailSerializer(self.get_object()).data)


class FixedAssetJobViewSet(mixins.RetrieveModelMixin, TenantGovernedViewSet):
    # Both current durable job origins are depreciation posting operations.
    # Additional job commands must add an explicit mapped action before routing.
    action_permissions = {"retrieve": "fixed_asset.depreciation:post"}

    def get_queryset(self) -> QuerySet[AsyncJob]:
        return AsyncJob.objects.for_tenant(self.tenant_id()).filter(command__startswith="fixed_assets.")

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(JobStatusSerializer(self.get_object()).data)


class FixedAssetDashboardViewSet(TenantGovernedViewSet):
    action_permissions = {"list": "fixed_asset.asset:read"}

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        tenant = self.tenant_id()
        today = timezone.localdate()
        assets = FixedAsset.objects.for_tenant(tenant)
        transactions = AssetTransaction.objects.for_tenant(tenant)
        raw_counts = {row["status"]: row["count"] for row in assets.values("status").annotate(count=Count("id"))}
        counts = {
            "draft": raw_counts.get("draft", 0),
            "active": raw_counts.get("active", 0),
            "fully_depreciated": raw_counts.get("fully_depreciated", 0),
            "disposed": raw_counts.get("disposed", 0),
            "total": sum(raw_counts.values()),
        }
        book_values = [
            {"currency": row["currency"], "amount": row["amount"] or Decimal("0.00")}
            for row in assets.exclude(status="disposed")
            .values("currency")
            .annotate(amount=Sum("net_book_value"))
            .order_by("currency")
        ]
        current_transactions = transactions.filter(effective_date__year=today.year, effective_date__month=today.month)
        current_depreciation = [
            {"currency": row["currency"], "amount": row["amount"] or Decimal("0.00")}
            for row in current_transactions.filter(transaction_type="depreciation")
            .values("currency")
            .annotate(amount=Sum("amount"))
            .order_by("currency")
        ]
        payload = {
            "asset_counts": counts,
            "book_value_by_currency": book_values,
            "current_period_depreciation_by_currency": current_depreciation,
            "pending_postings": DepreciationLine.objects.for_tenant(tenant)
            .filter(status__in=("planned", "posting"))
            .count(),
            "failed_postings": DepreciationLine.objects.for_tenant(tenant).filter(status="failed").count(),
            "impairments": current_transactions.filter(transaction_type="impairment").count(),
            "disposals": current_transactions.filter(transaction_type="disposal").count(),
        }
        serializer = DashboardSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)


class FixedAssetHealthAPIView(GovernedAPIViewMixin, APIView):
    """Unauthenticated, sanitized readiness probe with no tenant data."""

    authentication_classes: tuple[type, ...] = ()
    permission_classes = (AllowAny,)

    def get(self, request: object) -> Response:
        del request
        report = get_module_health()
        if report.status == "unhealthy":
            raise OperationFailed(
                error_code="FIXED_ASSETS_UNHEALTHY",
                message="The fixed-assets module is not ready.",
                detail=report.payload,
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        serializer = HealthResponseSerializer(data=report.payload)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)


class LegacyFixedAssetViewSet(viewsets.ViewSet):
    """API v1 compatibility adapter backed by normalized v2 services."""

    from rest_framework.authentication import SessionAuthentication
    from rest_framework.permissions import IsAuthenticated

    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated,)

    def tenant_id(self) -> UUID:
        from src.core.auth_utils import get_user_tenant_id

        value = get_user_tenant_id(self.request.user)
        try:
            return UUID(str(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise PermissionDenied("User must belong to a tenant.") from exc

    def actor_id(self) -> str:
        value = getattr(self.request.user, "id", None)
        if value is None:
            raise PermissionDenied("Authenticated identity has no valid actor.")
        return str(value)

    def get_queryset(self) -> QuerySet[FixedAsset]:
        return (
            FixedAsset.objects.for_tenant(self.tenant_id())
            .exclude(status="disposed")
            .select_related("category")
            .order_by("asset_code", "id")
        )

    def _object(self, pk: object) -> FixedAsset:
        value = self.get_queryset().filter(pk=pk).first()
        if value is None:
            raise NotFound()
        return value

    def list(self, request: object) -> Response:
        del request
        return Response(LegacyFixedAssetSerializer(self.get_queryset(), many=True).data)

    def retrieve(self, request: object, pk: str | None = None) -> Response:
        del request
        return Response(LegacyFixedAssetSerializer(self._object(pk)).data)

    def _legacy_category(self, code: str, data: dict[str, Any]) -> AssetCategory:
        category = AssetCategory.objects.for_tenant(self.tenant_id()).filter(code=code).first()
        if category is not None:
            return category
        years = int(data.get("useful_life_years", 5))
        category = AssetCategoryService.create_category(
            self.tenant_id(),
            self.actor_id(),
            {
                "code": code,
                "name": code.replace("_", " ").replace("-", " ").title(),
                "description": "Created through the fixed-assets API v1 compatibility adapter.",
                "default_depreciation_method": data.get("depreciation_method", "straight_line"),
                "default_useful_life_months": years * 12,
                "default_residual_value_percent": Decimal("0.00"),
                "is_active": False,
            },
            f"v1-category:{code}",
        )
        category.is_active = True
        category.save(update_fields={"is_active", "updated_at"})
        return category

    def create(self, request: object) -> Response:
        del request
        serializer = LegacyFixedAssetWriteSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        required = {"asset_code", "asset_name", "asset_category", "purchase_date", "purchase_cost"}
        missing = sorted(required - set(data))
        if missing:
            raise ValidationError({field: "This field is required." for field in missing})
        category = self._legacy_category(data.pop("asset_category"), data)
        years = data.pop("useful_life_years", 5)
        asset = FixedAssetService.create_asset(
            self.tenant_id(),
            self.actor_id(),
            {
                **data,
                "category_id": category.id,
                "currency": "USD",
                "residual_value": Decimal("0.00"),
                "useful_life_months": years * 12,
            },
            str(self.request.headers.get("Idempotency-Key") or f"v1-asset:{uuid4()}"),
        )
        return Response(LegacyFixedAssetSerializer(asset).data, status=201)

    def partial_update(self, request: object, pk: str | None = None) -> Response:
        del request
        asset = self._object(pk)
        serializer = LegacyFixedAssetWriteSerializer(data=self.request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        category_code = data.pop("asset_category", None)
        if category_code:
            data["category_id"] = self._legacy_category(category_code, data).id
        if "useful_life_years" in data:
            data["useful_life_months"] = data.pop("useful_life_years") * 12
        updated = FixedAssetService.update_draft(self.tenant_id(), asset.id, self.actor_id(), data, asset.version)
        return Response(LegacyFixedAssetSerializer(updated).data)

    update = partial_update

    def destroy(self, request: object, pk: str | None = None) -> Response:
        del request
        asset = self._object(pk)
        FixedAssetService.delete_draft(self.tenant_id(), asset.id, self.actor_id())
        return Response(status=204)


__all__ = [
    "AssetCategoryViewSet",
    "AssetTransactionViewSet",
    "DepreciationLineViewSet",
    "DepreciationScheduleViewSet",
    "FixedAssetDashboardViewSet",
    "FixedAssetHealthAPIView",
    "FixedAssetJobViewSet",
    "FixedAssetViewSet",
    "LegacyFixedAssetViewSet",
]
