"""Governed v2 API for tenant-isolated budget management."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable
from uuid import UUID

from django.db.models import Prefetch, Q, QuerySet
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination, OperationFailed

from .health import get_module_health
from .integrations import IntegrationError
from .models import Budget, BudgetApproval, BudgetLine, VarianceAlert
from .permissions import BudgetAccessMixin
from .serializers import (
    ActualsSyncRequestSerializer,
    AllocationReplaceSerializer,
    AsyncJobSummarySerializer,
    BudgetApprovalSerializer,
    BudgetApproveSerializer,
    BudgetAvailabilityRequestSerializer,
    BudgetAvailabilityResultSerializer,
    BudgetCloseSerializer,
    BudgetCreateSerializer,
    BudgetDeleteSerializer,
    BudgetDetailSerializer,
    BudgetLineCreateSerializer,
    BudgetLineReadSerializer,
    BudgetLineUpdateSerializer,
    BudgetListSerializer,
    BudgetRejectSerializer,
    BudgetReviseSerializer,
    BudgetSubmitSerializer,
    BudgetUpdateSerializer,
    HealthSerializer,
    VarianceAlertAcknowledgeSerializer,
    VarianceAlertDetailSerializer,
    VarianceAlertGenerateSerializer,
    VarianceAlertListSerializer,
    VarianceReportSerializer,
)
from .services import BudgetControlService, BudgetDomainError, BudgetService, VarianceAlertService


def _ordering(value: object, allowed: set[str], default: str) -> tuple[str, ...]:
    fields = tuple(part.strip() for part in str(value or default).split(",") if part.strip())
    if not fields or any(field.lstrip("-") not in allowed for field in fields):
        raise ValidationError({"ordering": "Unsupported ordering field."})
    return fields


def _uuid_filter(value: object, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({field: "Use a valid UUID."}) from exc


def _date_filter(value: object, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: "Use an ISO-8601 date."}) from exc


def _integer_filter(value: object, field: str, *, minimum: int = 1, maximum: int = 9999) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: "Use an integer."}) from exc
    if not minimum <= parsed <= maximum:
        raise ValidationError({field: f"Use a value from {minimum} to {maximum}."})
    return parsed


def _decimal_filter(value: object, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Use a decimal value."}) from exc
    if not parsed.is_finite() or parsed < 0 or parsed.as_tuple().exponent < -2:
        raise ValidationError({field: "Use a nonnegative decimal with at most two fractional digits."})
    return parsed.quantize(Decimal("0.01"))


def _choice_filter(value: object, field: str, choices: set[str]) -> str:
    parsed = str(value)
    if parsed not in choices:
        raise ValidationError({field: "Unsupported filter value."})
    return parsed


class BudgetPagination(GovernedPageNumberPagination):
    page_size = 25
    max_page_size = 100


class TenantGovernedViewSet(GovernedAPIViewMixin, BudgetAccessMixin, viewsets.GenericViewSet):
    pagination_class = BudgetPagination

    def tenant_id(self) -> UUID:
        value = getattr(self.request, "tenant_id", None)
        if not isinstance(value, UUID):
            raise PermissionDenied("Authenticated identity has no valid tenant.")
        return value

    def actor_id(self) -> UUID:
        raw = getattr(self.request.user, "id", None)
        if raw is None:
            raise PermissionDenied("Authenticated identity has no valid actor.")
        try:
            return UUID(str(raw))
        except (TypeError, ValueError, AttributeError):
            return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{raw}")

    def idempotency_key(self) -> str:
        value = str(self.request.headers.get("Idempotency-Key", "")).strip()
        if not value:
            raise ValidationError({"Idempotency-Key": "This header is required."})
        if len(value) > 255:
            raise ValidationError({"Idempotency-Key": "Must not exceed 255 characters."})
        return value

    def paginated(self, queryset: QuerySet[Any] | Iterable[Any], serializer: type) -> Response:
        page = self.paginate_queryset(queryset)
        if page is None:
            raise RuntimeError("Governed pagination is mandatory")
        return self.get_paginated_response(serializer(page, many=True, context={"request": self.request}).data)

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, BudgetDomainError):
            exc = OperationFailed(
                error_code=exc.code,
                message=str(exc),
                http_status=getattr(exc, "http_status", status.HTTP_400_BAD_REQUEST),
            )
        elif isinstance(exc, IntegrationError):
            exc = OperationFailed(
                error_code=exc.code,
                message="A required budget-management capability is unavailable.",
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return super().handle_exception(exc)


class BudgetViewSet(TenantGovernedViewSet):
    """Budget commands and projections; no mutation uses serializer.save()."""

    action_permissions = {
        "list": "budget.budget:read", "retrieve": "budget.budget:read",
        "create": "budget.budget:create", "partial_update": "budget.budget:update",
        "destroy": "budget.budget:delete", "allocations": "budget.budget_line:update",
        "submit": "budget.budget:submit", "approve": "budget.budget:approve",
        "reject": "budget.budget:approve", "revise": "budget.budget:update",
        "close": "budget.budget:close", "variance": "budget.variance:read",
        "sync_actuals": "budget.actuals:sync",
    }
    action_quotas = {
        "list": "budget_management.api_reads", "retrieve": "budget_management.api_reads",
        "variance": "budget_management.api_reads", "create": "budget_management.api_writes",
        "partial_update": "budget_management.api_writes", "destroy": "budget_management.api_writes",
        "allocations": "budget_management.api_writes", "submit": "budget_management.api_writes",
        "approve": "budget_management.api_writes", "reject": "budget_management.api_writes",
        "revise": "budget_management.api_writes", "close": "budget_management.api_writes",
        "sync_actuals": "budget_management.actual_sync",
    }

    def get_queryset(self) -> QuerySet[Budget]:
        tenant_id = self.tenant_id()
        lines = BudgetLine.objects.filter(tenant_id=tenant_id, is_deleted=False).order_by(
            "account_code", "period_type", "period_number"
        )
        queryset = Budget.objects.filter(tenant_id=tenant_id, is_deleted=False).prefetch_related(
            Prefetch("lines", queryset=lines), "approvals__decisions", "transitions", "variance_alerts"
        )
        params = self.request.query_params
        if params.get("fiscal_year") not in (None, ""):
            queryset = queryset.filter(fiscal_year=_integer_filter(params["fiscal_year"], "fiscal_year"))
        choices = {
            "budget_type": {"operating", "capital", "project", "departmental"},
            "status": {"draft", "pending_approval", "approved", "rejected", "revision", "closed"},
        }
        for field, allowed in choices.items():
            if params.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: _choice_filter(params[field], field, allowed)})
        if params.get("currency") not in (None, ""):
            currency = str(params["currency"]).strip().upper()
            if len(currency) != 3 or not currency.isalpha():
                raise ValidationError({"currency": "Use an ISO 4217 three-letter code."})
            queryset = queryset.filter(currency=currency)
        for field in ("department_id", "project_id"):
            if params.get(field):
                queryset = queryset.filter(**{field: _uuid_filter(params[field], field)})
        if params.get("start_date_from"):
            queryset = queryset.filter(start_date__gte=_date_filter(params["start_date_from"], "start_date_from"))
        if params.get("end_date_to"):
            queryset = queryset.filter(end_date__lte=_date_filter(params["end_date_to"], "end_date_to"))
        if params.get("search"):
            search = str(params["search"]).strip()
            queryset = queryset.filter(Q(budget_code__icontains=search) | Q(budget_name__icontains=search))
        ordering = _ordering(
            params.get("ordering"),
            {"budget_code", "budget_name", "fiscal_year", "start_date", "end_date", "total_budget", "updated_at"},
            "-fiscal_year,budget_code",
        )
        return queryset.order_by(*ordering)

    def list(self, request: Any) -> Response:
        del request
        return self.paginated(self.get_queryset(), BudgetListSerializer)

    def retrieve(self, request: Any, pk: str | None = None) -> Response:
        del request, pk
        return Response(BudgetDetailSerializer(self.get_object(), context={"request": self.request}).data)

    def create(self, request: Any) -> Response:
        serializer = BudgetCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        budget = BudgetService.create_budget(self.tenant_id(), self.actor_id(), **serializer.validated_data)
        return Response(BudgetDetailSerializer(budget).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Any, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        serializer = BudgetUpdateSerializer(data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected = data.pop("expected_updated_at")
        budget = BudgetService.update_budget(
            self.tenant_id(), UUID(str(self.kwargs["pk"])), self.actor_id(),
            expected_updated_at=expected, changes=data,
        )
        return Response(BudgetDetailSerializer(budget).data)

    def destroy(self, request: Any, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        serializer = BudgetDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        BudgetService.delete_budget(
            self.tenant_id(), UUID(str(self.kwargs["pk"])), self.actor_id(),
            expected_updated_at=serializer.validated_data["expected_updated_at"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("put",), url_path="allocations")
    def allocations(self, request: Any, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        serializer = AllocationReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        budget = BudgetService.replace_allocations(
            self.tenant_id(), UUID(str(self.kwargs["pk"])), self.actor_id(),
            list(serializer.validated_data["allocations"]),
            expected_updated_at=serializer.validated_data["expected_updated_at"],
        )
        return Response(BudgetDetailSerializer(budget).data)

    def _transition(self, serializer_class: type, method: str) -> Response:
        self.get_object()
        serializer = serializer_class(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        budget = getattr(BudgetService, method)(
            self.tenant_id(), UUID(str(self.kwargs["pk"])), self.actor_id(),
            idempotency_key=self.idempotency_key(), **serializer.validated_data,
        )
        return Response(BudgetDetailSerializer(budget).data)

    @action(detail=True, methods=("post",))
    def submit(self, request: Any, pk: str | None = None) -> Response:
        del request, pk
        return self._transition(BudgetSubmitSerializer, "submit_for_approval")

    @action(detail=True, methods=("post",))
    def approve(self, request: Any, pk: str | None = None) -> Response:
        del request, pk
        return self._transition(BudgetApproveSerializer, "approve_budget")

    @action(detail=True, methods=("post",))
    def reject(self, request: Any, pk: str | None = None) -> Response:
        del request, pk
        return self._transition(BudgetRejectSerializer, "reject_budget")

    @action(detail=True, methods=("post",))
    def revise(self, request: Any, pk: str | None = None) -> Response:
        del request, pk
        return self._transition(BudgetReviseSerializer, "revise_budget")

    @action(detail=True, methods=("post",))
    def close(self, request: Any, pk: str | None = None) -> Response:
        del request, pk
        return self._transition(BudgetCloseSerializer, "close_budget")

    @action(detail=True, methods=("get",))
    def variance(self, request: Any, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        report = BudgetControlService.calculate_variance(
            self.tenant_id(), UUID(str(self.kwargs["pk"])),
            period_type=(
                _choice_filter(request.query_params["period_type"], "period_type", {"annual", "monthly", "quarterly"})
                if request.query_params.get("period_type") else None
            ),
            period_number=(
                _integer_filter(request.query_params["period_number"], "period_number", maximum=12)
                if request.query_params.get("period_number") else None
            ),
            account_code=request.query_params.get("account_code"),
            threshold_percentage=_decimal_filter(request.query_params.get("threshold_percentage", "10.00"), "threshold_percentage"),
        )
        return Response(VarianceReportSerializer(report).data)

    @action(detail=True, methods=("post",), url_path="sync-actuals")
    def sync_actuals(self, request: Any, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        serializer = ActualsSyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = BudgetControlService.request_actuals_sync(
            self.tenant_id(), UUID(str(self.kwargs["pk"])), self.actor_id(),
            idempotency_key=self.idempotency_key(),
        )
        return Response(AsyncJobSummarySerializer(job).data, status=status.HTTP_202_ACCEPTED)


class BudgetLineViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "budget.budget_line:read", "retrieve": "budget.budget_line:read",
        "create": "budget.budget_line:create", "partial_update": "budget.budget_line:update",
        "destroy": "budget.budget_line:delete",
    }
    action_quotas = {name: "budget_management.api_reads" for name in ("list", "retrieve")} | {
        name: "budget_management.api_writes" for name in ("create", "partial_update", "destroy")
    }

    def get_queryset(self) -> QuerySet[BudgetLine]:
        queryset = BudgetLine.objects.filter(tenant_id=self.tenant_id(), is_deleted=False, budget__is_deleted=False)
        params = self.request.query_params
        if params.get("budget_id"):
            queryset = queryset.filter(budget_id=_uuid_filter(params["budget_id"], "budget_id"))
        if params.get("account_code") not in (None, ""):
            queryset = queryset.filter(account_code=str(params["account_code"]).strip().upper())
        if params.get("period_type") not in (None, ""):
            queryset = queryset.filter(period_type=_choice_filter(
                params["period_type"], "period_type", {"annual", "monthly", "quarterly"}
            ))
        if params.get("period_number") not in (None, ""):
            queryset = queryset.filter(period_number=_integer_filter(params["period_number"], "period_number", maximum=12))
        if params.get("source") not in (None, ""):
            queryset = queryset.filter(source=_choice_filter(
                params["source"], "source", {"manual", "accounting_sync"}
            ))
        if params.get("account_id"):
            queryset = queryset.filter(account_id=_uuid_filter(params["account_id"], "account_id"))
        return queryset.order_by(*_ordering(
            params.get("ordering"),
            {"account_code", "period_type", "period_number", "budget_amount", "actual_amount", "variance"},
            "account_code,period_type,period_number",
        ))

    def list(self, request: Any) -> Response:
        del request
        return self.paginated(self.get_queryset(), BudgetLineReadSerializer)

    def retrieve(self, request: Any, pk: str | None = None) -> Response:
        del request, pk
        return Response(BudgetLineReadSerializer(self.get_object()).data)

    def create(self, request: Any) -> Response:
        serializer = BudgetLineCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        budget_id = data.pop("budget_id")
        line = BudgetService.create_line(self.tenant_id(), budget_id, self.actor_id(), data)
        return Response(BudgetLineReadSerializer(line).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Any, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        serializer = BudgetLineUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected = data.pop("expected_updated_at")
        line = BudgetService.update_line(
            self.tenant_id(), UUID(str(self.kwargs["pk"])), self.actor_id(),
            expected_updated_at=expected, changes=data,
        )
        return Response(BudgetLineReadSerializer(line).data)

    def destroy(self, request: Any, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        serializer = BudgetDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        BudgetService.delete_line(
            self.tenant_id(), UUID(str(self.kwargs["pk"])), self.actor_id(),
            expected_updated_at=serializer.validated_data["expected_updated_at"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ApprovalViewSet(TenantGovernedViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    action_permissions = {"list": "budget.budget:approve", "retrieve": "budget.budget:approve"}
    action_quotas = {"list": "budget_management.api_reads", "retrieve": "budget_management.api_reads"}
    serializer_class = BudgetApprovalSerializer

    def get_queryset(self) -> QuerySet[BudgetApproval]:
        queryset = BudgetApproval.objects.filter(
            tenant_id=self.tenant_id(), budget__is_deleted=False
        ).prefetch_related("decisions")
        params = self.request.query_params
        for field in ("budget_id", "approver_id"):
            if params.get(field):
                queryset = queryset.filter(**{field: _uuid_filter(params[field], field)})
        if params.get("status") not in (None, ""):
            approval_status = _choice_filter(
                params["status"], "status", {"pending", "approved", "rejected", "cancelled"}
            )
            queryset = (
                queryset.filter(decisions__isnull=True)
                if approval_status == "pending"
                else queryset.filter(decisions__status=approval_status)
            )
        if params.get("approval_level") not in (None, ""):
            queryset = queryset.filter(approval_level=_integer_filter(params["approval_level"], "approval_level"))
        return queryset.order_by("approval_level", "created_at")


class VarianceAlertViewSet(TenantGovernedViewSet):
    action_permissions = {
        "list": "budget.variance:read", "retrieve": "budget.variance:read",
        "generate": "budget.variance:generate", "acknowledge": "budget.variance:acknowledge",
    }
    action_quotas = {
        "list": "budget_management.api_reads", "retrieve": "budget_management.api_reads",
        "generate": "budget_management.alert_generation", "acknowledge": "budget_management.api_writes",
    }

    def get_queryset(self) -> QuerySet[VarianceAlert]:
        queryset = VarianceAlert.objects.filter(tenant_id=self.tenant_id(), budget__is_deleted=False)
        params = self.request.query_params
        for field in ("budget_id", "budget_line_id"):
            if params.get(field):
                queryset = queryset.filter(**{field: _uuid_filter(params[field], field)})
        if params.get("alert_type"):
            queryset = queryset.filter(alert_type=_choice_filter(
                params["alert_type"], "alert_type", {"over_budget", "approaching_limit", "underspend"}
            ))
        if params.get("notification_status"):
            queryset = queryset.filter(notification_status=_choice_filter(
                params["notification_status"], "notification_status", {"pending", "sent", "failed", "unavailable"}
            ))
        if params.get("acknowledged"):
            normalized = str(params["acknowledged"]).lower()
            if normalized not in {"true", "false"}:
                raise ValidationError({"acknowledged": "Use true or false."})
            queryset = queryset.filter(acknowledged_at__isnull=normalized == "false")
        if params.get("date_from"):
            queryset = queryset.filter(alert_date__gte=_date_filter(params["date_from"], "date_from"))
        if params.get("date_to"):
            queryset = queryset.filter(alert_date__lte=_date_filter(params["date_to"], "date_to"))
        return queryset.order_by("-alert_date", "-created_at")

    def list(self, request: Any) -> Response:
        del request
        return self.paginated(self.get_queryset(), VarianceAlertListSerializer)

    def retrieve(self, request: Any, pk: str | None = None) -> Response:
        del request, pk
        return Response(VarianceAlertDetailSerializer(self.get_object()).data)

    @action(detail=False, methods=("post",))
    def generate(self, request: Any) -> Response:
        serializer = VarianceAlertGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = VarianceAlertService.request_alert_generation(
            self.tenant_id(), self.actor_id(), idempotency_key=self.idempotency_key(),
            **serializer.validated_data,
        )
        return Response(AsyncJobSummarySerializer(job).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=("post",))
    def acknowledge(self, request: Any, pk: str | None = None) -> Response:
        del pk
        self.get_object()
        serializer = VarianceAlertAcknowledgeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alert = VarianceAlertService.acknowledge_alert(
            self.tenant_id(), UUID(str(self.kwargs["pk"])), self.actor_id()
        )
        return Response(VarianceAlertDetailSerializer(alert).data)


class AvailabilityAPIView(GovernedAPIViewMixin, BudgetAccessMixin, APIView):
    permission_action = "calculate"
    action_permissions = {"calculate": "budget.availability:read"}
    action_quotas = {"calculate": "budget_management.api_reads"}

    def post(self, request: Any) -> Response:
        serializer = BudgetAvailabilityRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = BudgetControlService.check_budget_availability(request.tenant_id, **serializer.validated_data)
        return Response(BudgetAvailabilityResultSerializer(result).data)

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, BudgetDomainError):
            exc = OperationFailed(error_code=exc.code, message=str(exc), http_status=exc.http_status)
        return super().handle_exception(exc)


class HealthAPIView(GovernedAPIViewMixin, BudgetAccessMixin, APIView):
    permission_action = "health"
    action_permissions = {"health": "budget.health:read"}
    action_quotas = {"health": "budget_management.api_reads"}

    def get(self, request: Any) -> Response:
        result = get_module_health(request.tenant_id)
        response_status = status.HTTP_503_SERVICE_UNAVAILABLE if result["status"] == "unhealthy" else status.HTTP_200_OK
        return Response(HealthSerializer(result).data, status=response_status)
