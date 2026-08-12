"""Governed v2 procurement API.  Controllers contain no domain mutation logic."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any, Mapping, cast

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q, QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination, OperationFailed
from src.core.async_jobs.models import AsyncJob
from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import (
    ProcurementConfiguration,
    PurchaseOrder,
    PurchaseReceipt,
    PurchaseRequisition,
    RequestForQuotation,
    Supplier,
    SupplierQuote,
)
from .permissions import ACTION_ACCESS, PurchaseRequiresAccess
from .serializers import (
    ConfigurationImportSerializer,
    ConfigurationPreviewSerializer,
    ConfigurationRollbackSerializer,
    ConfigurationSerializer,
    ConfigurationWriteSerializer,
    EmptyTransitionSerializer,
    PurchaseOrderDetailSerializer,
    PurchaseOrderListSerializer,
    PurchaseOrderWriteSerializer,
    QuoteDetailSerializer,
    QuoteListSerializer,
    QuoteWriteSerializer,
    ReasonTransitionSerializer,
    ReceiptCompleteSerializer,
    ReceiptDetailSerializer,
    ReceiptListSerializer,
    ReceiptWriteSerializer,
    RequisitionConvertSerializer,
    RequisitionDetailSerializer,
    RequisitionListSerializer,
    RequisitionWriteSerializer,
    RFQAwardSerializer,
    RFQDetailSerializer,
    RFQListSerializer,
    RFQPublishSerializer,
    RFQWriteSerializer,
    SupplierDetailSerializer,
    SupplierListSerializer,
    SupplierStatusSerializer,
    SupplierWriteSerializer,
)
from .services import (
    ProcurementConfigurationService,
    ProcurementError,
    PurchaseOrderService,
    PurchaseReceiptService,
    QuoteService,
    RequisitionService,
    RFQService,
    SupplierService,
)


def _actor(user: Any) -> uuid.UUID:
    value = getattr(user, "id", None)
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{value}")


def _route_value(value: str | None) -> str:
    return cast(str, value)


def _text_value(value: Any) -> str:
    return cast(str, value)


class PurchaseViewSet(GovernedAPIViewMixin, viewsets.GenericViewSet[Any]):
    permission_classes = (IsAuthenticated, PurchaseRequiresAccess)
    authentication_classes = (RelaxedCsrfSessionAuthentication,)
    pagination_class = GovernedPageNumberPagination
    resource = "resource"
    ordering_fields: tuple[str, ...] = ()
    default_ordering = "-created_at"
    filter_fields: tuple[str, ...] = ()
    search_fields: tuple[str, ...] = ()

    def get_permissions(self) -> Any:
        verb = ACTION_ACCESS.get(getattr(self, "action", ""))
        if not verb:
            verb = "read"
        permission = f"purchase_management.{self.resource}:{verb}"
        self.required_permission = permission
        self.required_entitlement = permission
        self.quota_resource = permission
        self.quota_cost = 1
        return super().get_permissions()

    @property
    def tenant_id(self) -> uuid.UUID:
        value = get_user_tenant_id(self.request.user)
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError) as exc:
            raise OperationFailed(
                error_code="TENANT_REQUIRED", message="A valid tenant identity is required.", http_status=403
            ) from exc

    @property
    def actor_id(self) -> uuid.UUID:
        return _actor(self.request.user)

    @property
    def correlation_id(self) -> str:
        return (
            getattr(self.request, "correlation_id", "")
            or self.request.headers.get("X-Correlation-ID", "")
            or f"req_{uuid.uuid4().hex[:24]}"
        )

    def handle_exception(self, exc: Exception) -> Response:
        # Tenant-filtered service lookups intentionally make a foreign-tenant
        # identifier indistinguishable from an absent record.
        if isinstance(exc, ObjectDoesNotExist):
            exc = NotFound("Resource not found.")
        if isinstance(exc, ProcurementError):
            exc = OperationFailed(error_code=exc.code, message=str(exc), detail=exc.detail, http_status=exc.status_code)
        return super().handle_exception(exc)

    def _validate_query(self) -> None:
        common = {"page", "page_size", "search", "ordering"}
        allowed = common | set(self.filter_fields)
        unknown = set(self.request.query_params) - allowed
        if unknown:
            raise ValidationError({key: "Unknown query parameter." for key in sorted(unknown)})

    def _filter(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        self._validate_query()
        for name in self.filter_fields:
            value = self.request.query_params.get(name)
            if value not in (None, ""):
                queryset = queryset.filter(**{name: value})
        search = self.request.query_params.get("search", "").strip()
        if search and self.search_fields:
            predicate = Q()
            for name in self.search_fields:
                predicate |= Q(**{f"{name}__icontains": search})
            queryset = queryset.filter(predicate)
        ordering = self.request.query_params.get("ordering", self.default_ordering)
        if ordering.lstrip("-") not in self.ordering_fields:
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return queryset.order_by(ordering)

    def _list(self, queryset: QuerySet[Any], serializer: type[Any]) -> Response:
        page = self.paginate_queryset(self._filter(queryset))
        return self.get_paginated_response(serializer(page, many=True).data)

    def _validate(self, serializer_class: type[Any], *, partial: bool = False) -> dict[str, Any]:
        serializer = serializer_class(data=self.request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        return cast(dict[str, Any], serializer.validated_data)

    def _lock_version(self, data: Mapping[str, Any] | None = None) -> int:
        raw = self.request.headers.get("If-Match") or (data or {}).get("lock_version")
        try:
            return int(str(raw).strip('"'))
        except (TypeError, ValueError):
            raise ValidationError({"lock_version": "If-Match or lock_version is required."})

    def _idempotency(self) -> str:
        value = self.request.headers.get("Idempotency-Key", "").strip()
        if not value:
            raise ValidationError({"Idempotency-Key": "This header is required."})
        if len(value) > 255:
            raise ValidationError({"Idempotency-Key": "Must not exceed 255 characters."})
        return value


class SupplierViewSet(PurchaseViewSet):
    resource = "supplier"
    queryset = Supplier.objects.none()
    ordering_fields = ("supplier_code", "supplier_name", "created_at")
    default_ordering = "supplier_code"
    filter_fields = ("status", "currency")
    search_fields = ("supplier_code", "supplier_name", "email")

    def get_queryset(self) -> QuerySet[Any]:
        return cast(QuerySet[Any], Supplier.objects.for_tenant(self.tenant_id))

    def list(self, request: Request) -> Response:
        return self._list(self.get_queryset(), SupplierListSerializer)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(SupplierDetailSerializer(SupplierService.get_supplier(self.tenant_id, _route_value(pk))).data)

    def create(self, request: Request) -> Response:
        data = self._validate(SupplierWriteSerializer)
        return Response(
            SupplierDetailSerializer(
                SupplierService.create_supplier(self.tenant_id, self.actor_id, data, self.correlation_id)
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def _update(self, request: Request, pk: str | None, partial: bool) -> Response:
        data = self._validate(SupplierWriteSerializer, partial=partial)
        lock = self._lock_version(data)
        data.pop("lock_version", None)
        return Response(
            SupplierDetailSerializer(
                SupplierService.update_supplier(
                    self.tenant_id, self.actor_id, _route_value(pk), data, lock, self.correlation_id
                )
            ).data
        )

    def update(self, request: Request, pk: str | None = None) -> Response:
        return self._update(request, pk, False)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        return self._update(request, pk, True)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        data = self._validate(SupplierStatusSerializer)
        supplier = SupplierService.archive_supplier(
            self.tenant_id, self.actor_id, _route_value(pk), data["reason"], self._idempotency(), self.correlation_id
        )
        return Response(SupplierDetailSerializer(supplier).data)

    @action(detail=True, methods=("post",))
    def activate(self, request: Request, pk: str | None = None) -> Response:
        data = self._validate(SupplierStatusSerializer)
        return Response(
            SupplierDetailSerializer(
                SupplierService.restore_supplier(
                    self.tenant_id,
                    self.actor_id,
                    _route_value(pk),
                    data["reason"],
                    self._idempotency(),
                    self.correlation_id,
                )
            ).data
        )

    @action(detail=True, methods=("post",))
    def deactivate(self, request: Request, pk: str | None = None) -> Response:
        data = self._validate(SupplierStatusSerializer)
        return Response(
            SupplierDetailSerializer(
                SupplierService.set_supplier_status(
                    self.tenant_id,
                    self.actor_id,
                    _route_value(pk),
                    "inactive",
                    data["reason"],
                    self._idempotency(),
                    self.correlation_id,
                )
            ).data
        )


class RequisitionViewSet(PurchaseViewSet):
    resource = "requisition"
    queryset = PurchaseRequisition.objects.none()
    ordering_fields = ("requisition_date", "required_date", "requisition_number")
    default_ordering = "-requisition_date"
    filter_fields = ("status", "requested_by", "requisition_date__gte", "requisition_date__lte")
    search_fields = ("requisition_number", "purpose")

    def get_queryset(self) -> QuerySet[Any]:
        return cast(
            QuerySet[Any], PurchaseRequisition.objects.for_tenant(self.tenant_id).filter(deleted_at__isnull=True)
        )

    def list(self, request: Request) -> Response:
        return self._list(self.get_queryset(), RequisitionListSerializer)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(
            RequisitionDetailSerializer(RequisitionService.get_requisition(self.tenant_id, _route_value(pk))).data
        )

    def create(self, request: Request) -> Response:
        data = self._validate(RequisitionWriteSerializer)
        return Response(
            RequisitionDetailSerializer(
                RequisitionService.create_requisition(self.tenant_id, self.actor_id, data, self.correlation_id)
            ).data,
            status=201,
        )

    def _update(self, request: Request, pk: str | None, partial: bool) -> Response:
        data = self._validate(RequisitionWriteSerializer, partial=partial)
        lock = self._lock_version(data)
        data.pop("lock_version", None)
        return Response(
            RequisitionDetailSerializer(
                RequisitionService.update_requisition(
                    self.tenant_id, self.actor_id, _route_value(pk), data, lock, self.correlation_id
                )
            ).data
        )

    def update(self, request: Request, pk: str | None = None) -> Response:
        return self._update(request, pk, False)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        return self._update(request, pk, True)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        return Response(
            RequisitionDetailSerializer(
                RequisitionService.delete_draft_requisition(
                    self.tenant_id, self.actor_id, _route_value(pk), self._lock_version(), self.correlation_id
                )
            ).data
        )

    def _transition(self, serializer: type[Any], service: Callable[..., Any], pk: str | None) -> Response:
        data = self._validate(serializer)
        result = service(
            self.tenant_id,
            self.actor_id,
            _route_value(pk),
            correlation_id=self.correlation_id,
            idempotency_key=self._idempotency(),
            **data,
        )
        return Response(RequisitionDetailSerializer(result).data)

    @action(detail=True, methods=("post",))
    def submit(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(EmptyTransitionSerializer, RequisitionService.submit_requisition, pk)

    @action(detail=True, methods=("post",))
    def approve(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(EmptyTransitionSerializer, RequisitionService.approve_requisition, pk)

    @action(detail=True, methods=("post",))
    def reject(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(ReasonTransitionSerializer, RequisitionService.reject_requisition, pk)

    @action(detail=True, methods=("post",))
    def revise(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(EmptyTransitionSerializer, RequisitionService.revise_requisition, pk)

    @action(detail=True, methods=("post",))
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(EmptyTransitionSerializer, RequisitionService.cancel_requisition, pk)

    @action(detail=True, methods=("post",), url_path="convert-to-order")
    def convert_to_order(self, request: Request, pk: str | None = None) -> Response:
        data = self._validate(RequisitionConvertSerializer)
        order = RequisitionService.convert_to_purchase_order(
            self.tenant_id,
            self.actor_id,
            _route_value(pk),
            data["supplier_id"],
            data["line_selections"],
            self.correlation_id,
            self._idempotency(),
        )
        return Response(PurchaseOrderDetailSerializer(order).data)


class RFQViewSet(PurchaseViewSet):
    resource = "rfq"
    queryset = RequestForQuotation.objects.none()
    ordering_fields = ("issue_date", "submission_deadline", "rfq_number")
    default_ordering = "-issue_date"
    filter_fields = ("status", "submission_deadline__gte", "submission_deadline__lte")
    search_fields = ("rfq_number", "title")

    def get_queryset(self) -> QuerySet[Any]:
        return cast(
            QuerySet[Any], RequestForQuotation.objects.for_tenant(self.tenant_id).filter(deleted_at__isnull=True)
        )

    def list(self, request: Request) -> Response:
        return self._list(self.get_queryset(), RFQListSerializer)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(RFQDetailSerializer(RFQService.get_rfq(self.tenant_id, pk)).data)

    def create(self, request: Request) -> Response:
        return Response(
            RFQDetailSerializer(
                RFQService.create_rfq(
                    self.tenant_id, self.actor_id, self._validate(RFQWriteSerializer), self.correlation_id
                )
            ).data,
            status=201,
        )

    def _update(self, request: Request, pk: str | None, partial: bool) -> Response:
        data = self._validate(RFQWriteSerializer, partial=partial)
        lock = self._lock_version(data)
        data.pop("lock_version", None)
        return Response(
            RFQDetailSerializer(
                RFQService.update_rfq(self.tenant_id, self.actor_id, _route_value(pk), data, lock, self.correlation_id)
            ).data
        )

    def update(self, request: Request, pk: str | None = None) -> Response:
        return self._update(request, pk, False)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        return self._update(request, pk, True)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        return Response(
            RFQDetailSerializer(
                RFQService.delete_draft_rfq(
                    self.tenant_id, self.actor_id, _route_value(pk), self._lock_version(), self.correlation_id
                )
            ).data
        )

    @action(detail=True, methods=("post",))
    def publish(self, request: Request, pk: str | None = None) -> Response:
        data = self._validate(RFQPublishSerializer)
        rfq, job = RFQService.publish_rfq(
            self.tenant_id,
            self.actor_id,
            _route_value(pk),
            data["supplier_ids"],
            self._idempotency(),
            self.correlation_id,
        )
        return Response({"rfq": RFQDetailSerializer(rfq).data, "job_id": str(job.id)}, status=202)

    @action(detail=True, methods=("post",))
    def close(self, request: Request, pk: str | None = None) -> Response:
        return Response(
            RFQDetailSerializer(RFQService.close_rfq(self.tenant_id, self.actor_id, pk, self.correlation_id)).data
        )

    @action(detail=True, methods=("post",))
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        return Response(
            RFQDetailSerializer(RFQService.cancel_rfq(self.tenant_id, self.actor_id, pk, self.correlation_id)).data
        )

    @action(detail=True, methods=("get",), url_path="compare-quotes")
    def compare_quotes(self, request: Request, pk: str | None = None) -> Response:
        return Response(RFQService.compare_quotes(self.tenant_id, _route_value(pk)))

    @action(detail=True, methods=("post",))
    def award(self, request: Request, pk: str | None = None) -> Response:
        data = self._validate(RFQAwardSerializer)
        quote, order = RFQService.award_quote(
            self.tenant_id,
            self.actor_id,
            _route_value(pk),
            data["quote_id"],
            data["create_purchase_order"],
            self._idempotency(),
            self.correlation_id,
        )
        return Response(
            {
                "quote": QuoteDetailSerializer(quote).data,
                "purchase_order": PurchaseOrderDetailSerializer(order).data if order else None,
            }
        )


class QuoteViewSet(PurchaseViewSet):
    resource = "quote"
    queryset = SupplierQuote.objects.none()
    ordering_fields = ("total_amount", "delivery_date", "submitted_at")
    default_ordering = "-submitted_at"
    filter_fields = ("rfq_id", "supplier_id", "status")
    search_fields = ("quote_number",)

    def get_queryset(self) -> QuerySet[Any]:
        return cast(QuerySet[Any], SupplierQuote.objects.for_tenant(self.tenant_id))

    def list(self, request: Request) -> Response:
        return self._list(self.get_queryset(), QuoteListSerializer)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(QuoteDetailSerializer(QuoteService.get_quote(self.tenant_id, pk)).data)

    def create(self, request: Request) -> Response:
        return Response(
            QuoteDetailSerializer(
                QuoteService.create_quote(
                    self.tenant_id, self.actor_id, self._validate(QuoteWriteSerializer), self.correlation_id
                )
            ).data,
            status=201,
        )

    def _update(self, request: Request, pk: str | None, partial: bool) -> Response:
        data = self._validate(QuoteWriteSerializer, partial=partial)
        lock = self._lock_version(data)
        data.pop("lock_version", None)
        return Response(
            QuoteDetailSerializer(
                QuoteService.update_quote(
                    self.tenant_id, self.actor_id, _route_value(pk), data, lock, self.correlation_id
                )
            ).data
        )

    def update(self, request: Request, pk: str | None = None) -> Response:
        return self._update(request, pk, False)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        return self._update(request, pk, True)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        QuoteService.delete_draft_quote(
            self.tenant_id, self.actor_id, _route_value(pk), self._lock_version(), self.correlation_id
        )
        return Response({"status": "deleted"})

    @action(detail=True, methods=("post",))
    def submit(self, request: Request, pk: str | None = None) -> Response:
        return Response(
            QuoteDetailSerializer(
                QuoteService.submit_quote(
                    self.tenant_id, self.actor_id, pk, self.correlation_id, idempotency_key=self._idempotency()
                )
            ).data
        )

    @action(detail=True, methods=("post",))
    def withdraw(self, request: Request, pk: str | None = None) -> Response:
        return Response(
            QuoteDetailSerializer(
                QuoteService.withdraw_quote(
                    self.tenant_id, self.actor_id, pk, self.correlation_id, idempotency_key=self._idempotency()
                )
            ).data
        )


class PurchaseOrderViewSet(PurchaseViewSet):
    resource = "purchase_order"
    queryset = PurchaseOrder.objects.none()
    ordering_fields = ("po_date", "expected_delivery_date", "total_amount")
    default_ordering = "-po_date"
    filter_fields = ("status", "supplier_id", "requisition_id", "po_date__gte", "po_date__lte")
    search_fields = ("po_number", "supplier__supplier_name")

    def get_queryset(self) -> QuerySet[Any]:
        return cast(QuerySet[Any], PurchaseOrder.objects.for_tenant(self.tenant_id).filter(deleted_at__isnull=True))

    def list(self, request: Request) -> Response:
        return self._list(self.get_queryset(), PurchaseOrderListSerializer)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(PurchaseOrderDetailSerializer(PurchaseOrderService.get_purchase_order(self.tenant_id, pk)).data)

    def create(self, request: Request) -> Response:
        return Response(
            PurchaseOrderDetailSerializer(
                PurchaseOrderService.create_purchase_order(
                    self.tenant_id, self.actor_id, self._validate(PurchaseOrderWriteSerializer), self.correlation_id
                )
            ).data,
            status=201,
        )

    def _update(self, request: Request, pk: str | None, partial: bool) -> Response:
        data = self._validate(PurchaseOrderWriteSerializer, partial=partial)
        lock = self._lock_version(data)
        data.pop("lock_version", None)
        return Response(
            PurchaseOrderDetailSerializer(
                PurchaseOrderService.update_purchase_order(
                    self.tenant_id, self.actor_id, _route_value(pk), data, lock, self.correlation_id
                )
            ).data
        )

    def update(self, request: Request, pk: str | None = None) -> Response:
        return self._update(request, pk, False)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        return self._update(request, pk, True)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        return Response(
            PurchaseOrderDetailSerializer(
                PurchaseOrderService.delete_draft_purchase_order(
                    self.tenant_id, self.actor_id, _route_value(pk), self._lock_version(), self.correlation_id
                )
            ).data
        )

    def _transition(self, service: Callable[..., Any], pk: str | None) -> Response:
        return Response(
            PurchaseOrderDetailSerializer(
                service(self.tenant_id, self.actor_id, pk, self.correlation_id, idempotency_key=self._idempotency())
            ).data
        )

    @action(detail=True, methods=("post",))
    def submit(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(PurchaseOrderService.submit_purchase_order, pk)

    @action(detail=True, methods=("post",))
    def approve(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(PurchaseOrderService.approve_purchase_order, pk)

    @action(detail=True, methods=("post",))
    def reject(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(PurchaseOrderService.reject_purchase_order, pk)

    @action(detail=True, methods=("post",))
    def acknowledge(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(PurchaseOrderService.acknowledge_purchase_order, pk)

    @action(detail=True, methods=("post",))
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(PurchaseOrderService.cancel_purchase_order, pk)

    @action(detail=True, methods=("post",), url_path="dispatch")
    def dispatch_order(self, request: Request, pk: str | None = None) -> Response:
        order, job = PurchaseOrderService.dispatch_purchase_order(
            self.tenant_id, self.actor_id, _route_value(pk), self._idempotency(), self.correlation_id
        )
        return Response(
            {"purchase_order": PurchaseOrderDetailSerializer(order).data, "job_id": str(job.id)}, status=202
        )


class ReceiptViewSet(PurchaseViewSet):
    resource = "receipt"
    queryset = PurchaseReceipt.objects.none()
    ordering_fields = ("receipt_date", "receipt_number")
    default_ordering = "-receipt_date"
    filter_fields = ("status", "purchase_order_id", "warehouse_id", "receipt_date__gte", "receipt_date__lte")
    search_fields = ("receipt_number", "purchase_order__po_number")

    def get_queryset(self) -> QuerySet[Any]:
        return cast(QuerySet[Any], PurchaseReceipt.objects.for_tenant(self.tenant_id))

    def list(self, request: Request) -> Response:
        return self._list(self.get_queryset(), ReceiptListSerializer)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(ReceiptDetailSerializer(PurchaseReceiptService.get_receipt(self.tenant_id, pk)).data)

    def create(self, request: Request) -> Response:
        return Response(
            ReceiptDetailSerializer(
                PurchaseReceiptService.create_receipt(
                    self.tenant_id, self.actor_id, self._validate(ReceiptWriteSerializer), self.correlation_id
                )
            ).data,
            status=201,
        )

    def _update(self, request: Request, pk: str | None, partial: bool) -> Response:
        data = self._validate(ReceiptWriteSerializer, partial=partial)
        lock = self._lock_version(data)
        data.pop("lock_version", None)
        return Response(
            ReceiptDetailSerializer(
                PurchaseReceiptService.update_receipt(
                    self.tenant_id, self.actor_id, _route_value(pk), data, lock, self.correlation_id
                )
            ).data
        )

    def update(self, request: Request, pk: str | None = None) -> Response:
        return self._update(request, pk, False)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        return self._update(request, pk, True)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        PurchaseReceiptService.delete_draft_receipt(
            self.tenant_id, self.actor_id, _route_value(pk), self._lock_version(), self.correlation_id
        )
        return Response({"status": "deleted"})

    @action(detail=True, methods=("post",))
    def complete(self, request: Request, pk: str | None = None) -> Response:
        self._validate(ReceiptCompleteSerializer)
        return Response(
            ReceiptDetailSerializer(
                PurchaseReceiptService.complete_receipt(
                    self.tenant_id, self.actor_id, _route_value(pk), self._idempotency(), self.correlation_id
                )
            ).data
        )

    @action(detail=True, methods=("post",))
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        return Response(
            ReceiptDetailSerializer(
                PurchaseReceiptService.cancel_receipt(
                    self.tenant_id, self.actor_id, _route_value(pk), self.correlation_id
                )
            ).data
        )


class ConfigurationViewSet(PurchaseViewSet):
    resource = "configuration"
    queryset = ProcurementConfiguration.objects.none()
    ordering_fields = ("version",)
    default_ordering = "-version"
    filter_fields = ("environment", "status")

    def get_queryset(self) -> QuerySet[Any]:
        return cast(QuerySet[Any], ProcurementConfiguration.objects.for_tenant(self.tenant_id))

    @action(detail=False, methods=("get",))
    def active(self, request: Request) -> Response:
        environment = request.query_params.get("environment")
        return Response(
            ConfigurationSerializer(
                ProcurementConfigurationService.get_active_configuration(self.tenant_id, _text_value(environment))
            ).data
        )

    @action(detail=False, methods=("get", "post"), url_path="versions")
    def versions(self, request: Request) -> Response:
        environment = request.query_params.get("environment") or request.data.get("environment")
        if request.method == "GET":
            return self._list(
                ProcurementConfigurationService.list_versions(self.tenant_id, _text_value(environment)),
                ConfigurationSerializer,
            )
        data = self._validate(ConfigurationWriteSerializer)
        config = ProcurementConfigurationService.create_draft(
            self.tenant_id, self.actor_id, _text_value(environment), data, self.correlation_id
        )
        return Response(ConfigurationSerializer(config).data, status=201)

    @action(detail=False, methods=("get", "patch"), url_path=r"versions/(?P<version_id>[0-9a-f-]+)")
    def version_detail(self, request: Request, version_id: str | None = None) -> Response:
        if request.method == "GET":
            return Response(
                ConfigurationSerializer(
                    ProcurementConfigurationService.get_version(self.tenant_id, _route_value(version_id))
                ).data
            )
        data = self._validate(ConfigurationWriteSerializer, partial=True)
        lock = self._lock_version(data)
        data.pop("lock_version", None)
        return Response(
            ConfigurationSerializer(
                ProcurementConfigurationService.update_draft(
                    self.tenant_id, self.actor_id, _route_value(version_id), data, lock, self.correlation_id
                )
            ).data
        )

    @action(detail=False, methods=("post",))
    def preview(self, request: Request) -> Response:
        data = self._validate(ConfigurationPreviewSerializer)
        environment = data.pop("environment")
        simulations = data.pop("simulations", [])
        return Response(
            ProcurementConfigurationService.preview_configuration(self.tenant_id, environment, data, simulations)
        )

    @action(detail=False, methods=("post",), url_path=r"versions/(?P<version_id>[0-9a-f-]+)/activate")
    def activate_version(self, request: Request, version_id: str | None = None) -> Response:
        data = self._validate(ConfigurationRollbackSerializer)
        return Response(
            ConfigurationSerializer(
                ProcurementConfigurationService.activate_configuration(
                    self.tenant_id, self.actor_id, _route_value(version_id), data["reason"], self.correlation_id
                )
            ).data
        )

    @action(detail=False, methods=("post",), url_path=r"versions/(?P<version_id>[0-9a-f-]+)/rollback")
    def rollback(self, request: Request, version_id: str | None = None) -> Response:
        data = self._validate(ConfigurationRollbackSerializer)
        return Response(
            ConfigurationSerializer(
                ProcurementConfigurationService.rollback_configuration(
                    self.tenant_id, self.actor_id, _route_value(version_id), data["reason"], self.correlation_id
                )
            ).data
        )

    @action(detail=False, methods=("get",), url_path="export")
    def export_configuration(self, request: Request) -> Response:
        version = request.query_params.get("version")
        return Response(
            ProcurementConfigurationService.export_configuration(
                self.tenant_id, _text_value(request.query_params.get("environment")), int(version) if version else None
            )
        )

    @action(detail=False, methods=("post",), url_path="import")
    def import_configuration(self, request: Request) -> Response:
        data = self._validate(ConfigurationImportSerializer)
        return Response(
            ConfigurationSerializer(
                ProcurementConfigurationService.import_configuration(
                    self.tenant_id, self.actor_id, data["document"], self.correlation_id
                )
            ).data,
            status=201,
        )


class JobViewSet(PurchaseViewSet):
    resource = "job"
    queryset = AsyncJob.objects.none()

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        try:
            job = AsyncJob.objects.for_tenant(self.tenant_id).get(pk=_route_value(pk), command__startswith="purchase.")
        except AsyncJob.DoesNotExist as exc:
            raise NotFound() from exc
        return Response(
            {
                "id": str(job.id),
                "command": job.command,
                "status": job.status,
                "attempts": job.attempts,
                "result": job.result,
                "error_message": job.error_message,
                "correlation_id": job.correlation_id,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
            }
        )


# Compatibility class names for existing imports.
PurchaseRequisitionViewSet = RequisitionViewSet
PurchaseReceiptViewSet = ReceiptViewSet
