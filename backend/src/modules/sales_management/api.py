"""Governed v2 HTTP boundary for sales management."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination
from src.core.api.envelope import correlation_id_for_request
from src.core.api.results import OperationFailed
from src.core.auth_utils import get_user_tenant_id
from src.core.state_machine import StateMachineError

from .models import Customer, DeliveryNote, Quotation, SalesConfiguration, SalesOrder
from .permissions import (
    CONFIG_EXPORT,
    CONFIG_IMPORT,
    CONFIG_READ,
    CONFIG_ROLLBACK,
    CONFIG_UPDATE,
    CUSTOMER_CREATE,
    CUSTOMER_DELETE,
    CUSTOMER_READ,
    CUSTOMER_UPDATE,
    DELIVERY_CANCEL,
    DELIVERY_COMPLETE,
    DELIVERY_CREATE,
    DELIVERY_DELETE,
    DELIVERY_READ,
    DELIVERY_UPDATE,
    ORDER_CANCEL,
    ORDER_CONFIRM,
    ORDER_CREATE,
    ORDER_DELETE,
    ORDER_FULFILL,
    ORDER_INVOICE,
    ORDER_READ,
    ORDER_UPDATE,
    QUOTATION_ACCEPT,
    QUOTATION_CONVERT,
    QUOTATION_CREATE,
    QUOTATION_DELETE,
    QUOTATION_READ,
    QUOTATION_REJECT,
    QUOTATION_SEND,
    QUOTATION_UPDATE,
    SalesAccessMixin,
)
from .serializers import (
    ConfigurationImportSerializer,
    ConfigurationRollbackSerializer,
    CustomerDetailSerializer,
    CustomerListSerializer,
    CustomerWriteSerializer,
    DeliveryNoteCommandSerializer,
    DeliveryNoteDetailSerializer,
    DeliveryNoteListSerializer,
    DeliveryNoteWriteSerializer,
    QuotationCommandSerializer,
    QuotationDetailSerializer,
    QuotationListSerializer,
    QuotationPreviewSerializer,
    QuotationPreviewResultSerializer,
    QuotationWriteSerializer,
    SalesConfigurationSerializer,
    SalesConfigurationVersionSerializer,
    SalesConfigurationWriteSerializer,
    SalesOrderCommandSerializer,
    SalesOrderDetailSerializer,
    SalesOrderListSerializer,
    SalesOrderWriteSerializer,
)
from .services import (
    ConcurrentModification,
    CustomerService,
    DeliveryNoteService,
    IdempotencyConflict,
    QuotationService,
    ResourceConflict,
    SalesConfigurationService,
    SalesDashboardService,
    SalesOrderService,
)


def _tenant(request: Request) -> uuid.UUID:
    raw = getattr(request, "tenant_id", None) or get_user_tenant_id(request.user)
    try:
        return raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PermissionDenied("Authenticated tenant context is required.") from exc


def _actor(request: Request) -> uuid.UUID:
    raw = getattr(request.user, "id", getattr(request.user, "pk", None))
    if raw is None:
        raise PermissionDenied("Authenticated actor identity is required.")
    try:
        return raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw))
    except (TypeError, ValueError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise-user:{raw}")


def _correlation(request: Request) -> uuid.UUID:
    raw = correlation_id_for_request(request)
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise-correlation:{raw}")


def _idempotency(request: Request) -> str:
    value = request.headers.get("Idempotency-Key", "").strip()
    if not value or len(value) > 255:
        raise ValidationError({"idempotency_key": ["Idempotency-Key is required and must be at most 255 characters."]})
    return value


def _expected(request: Request, values: dict[str, Any]) -> int:
    raw = values.pop("expected_version", None)
    if raw is None:
        raw = request.headers.get("If-Match")
    if isinstance(raw, str):
        raw = raw.strip().removeprefix("W/").strip('"')
    try:
        result = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"expected_version": ["expected_version or If-Match is required."]}) from exc
    if result < 1:
        raise ValidationError({"expected_version": ["Expected version must be positive."]})
    return result


def _call(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except ConcurrentModification as exc:
        raise OperationFailed(
            error_code="CONCURRENT_MODIFICATION",
            message="The resource was modified by another request.",
            http_status=409,
        ) from exc
    except IdempotencyConflict as exc:
        raise OperationFailed(
            error_code="IDEMPOTENCY_CONFLICT",
            message="The idempotency key conflicts with an earlier request.",
            http_status=409,
        ) from exc
    except (ResourceConflict, StateMachineError) as exc:
        raise OperationFailed(error_code="RESOURCE_CONFLICT", message=str(exc), http_status=409) from exc
    except IntegrityError as exc:
        raise OperationFailed(
            error_code="RESOURCE_CONFLICT",
            message="The operation conflicts with persisted sales data.",
            http_status=409,
        ) from exc
    except DjangoValidationError as exc:
        detail = getattr(exc, "message_dict", None) or {
            "non_field_errors": getattr(exc, "messages", ["Sales validation failed."])
        }
        raise ValidationError(detail) from exc
    except LookupError as exc:
        raise NotFound("The requested sales resource was not found.") from exc
    except (KeyError, TypeError) as exc:
        raise ValidationError({"non_field_errors": ["The command document is invalid."]}) from exc


class SalesViewSet(GovernedAPIViewMixin, SalesAccessMixin, viewsets.GenericViewSet):  # type: ignore[misc]  # noqa: F405
    pagination_class = GovernedPageNumberPagination
    model: type[Any]
    service: type[Any]
    serializer_classes: Mapping[str, type[Any]] = {}
    ordering_default = "id"

    def get_serializer_class(self):
        serializer = self.serializer_classes.get(self.action)
        if serializer is None:
            raise RuntimeError(f"No serializer declared for {type(self).__name__}.{self.action}")
        return serializer

    def get_queryset(self) -> QuerySet[Any]:
        # Every viewset establishes the tenant boundary even though list methods
        # delegate filter policy to services.
        return self.model.objects.for_tenant(_tenant(self.request)).filter(deleted_at__isnull=True)

    def get_object(self):
        obj = super().get_object()
        self.check_object_permissions(self.request, obj)
        return obj

    def _list(self, queryset: QuerySet[Any]) -> Response:
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)


class CustomerViewSet(SalesViewSet):
    model = Customer
    service = CustomerService
    action_permissions = {
        "list": CUSTOMER_READ,
        "retrieve": CUSTOMER_READ,
        "create": CUSTOMER_CREATE,
        "partial_update": CUSTOMER_UPDATE,
        "destroy": CUSTOMER_DELETE,
    }  # noqa: F405
    serializer_classes = {
        "list": CustomerListSerializer,
        "retrieve": CustomerDetailSerializer,
        "create": CustomerWriteSerializer,
        "partial_update": CustomerWriteSerializer,
        "destroy": CustomerDetailSerializer,
    }  # noqa: F405

    def get_queryset(self):
        params = self.request.query_params
        return CustomerService.list_customers(
            _tenant(self.request), params, None, params.get("ordering", "customer_code")
        )

    def list(self, request):
        return self._list(self.get_queryset())

    def retrieve(self, request, pk=None):
        return Response(
            CustomerDetailSerializer(_call(lambda: CustomerService.get_customer(_tenant(request), pk))).data
        )  # noqa: F405

    def create(self, request):
        serializer = CustomerWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # noqa: F405
        obj = _call(
            lambda: CustomerService.create_customer(
                _tenant(request),
                _actor(request),
                _correlation(request),
                _idempotency(request),
                dict(serializer.validated_data),
            )
        )
        return Response(CustomerDetailSerializer(obj).data, status=status.HTTP_201_CREATED)  # noqa: F405

    def partial_update(self, request, pk=None):
        serializer = CustomerWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)  # noqa: F405
        obj = _call(
            lambda: CustomerService.update_customer(
                _tenant(request), pk, _actor(request), _correlation(request), _expected(request, values), values
            )
        )
        return Response(CustomerDetailSerializer(obj).data)  # noqa: F405

    def destroy(self, request, pk=None):
        obj = _call(
            lambda: CustomerService.archive_customer(
                _tenant(request), pk, _actor(request), _correlation(request), _expected(request, {})
            )
        )
        return Response(CustomerDetailSerializer(obj).data)  # noqa: F405


class QuotationViewSet(SalesViewSet):
    model = Quotation
    service = QuotationService
    action_permissions = {
        "list": QUOTATION_READ,
        "retrieve": QUOTATION_READ,
        "create": QUOTATION_CREATE,
        "partial_update": QUOTATION_UPDATE,
        "destroy": QUOTATION_DELETE,
        "preview": QUOTATION_CREATE,
        "send": QUOTATION_SEND,
        "accept": QUOTATION_ACCEPT,
        "reject": QUOTATION_REJECT,
        "expire": QUOTATION_UPDATE,
        "revise": QUOTATION_UPDATE,
        "convert": QUOTATION_CONVERT,
    }  # noqa: F405
    serializer_classes = {
        "list": QuotationListSerializer,
        "retrieve": QuotationDetailSerializer,
        "create": QuotationWriteSerializer,
        "partial_update": QuotationWriteSerializer,
        "destroy": QuotationDetailSerializer,
        "preview": QuotationPreviewSerializer,
        "send": QuotationCommandSerializer,
        "accept": QuotationCommandSerializer,
        "reject": QuotationCommandSerializer,
        "expire": QuotationCommandSerializer,
        "revise": QuotationCommandSerializer,
        "convert": QuotationCommandSerializer,
    }  # noqa: F405

    def get_queryset(self):
        p = self.request.query_params
        return QuotationService.list_quotations(_tenant(self.request), p, None, p.get("ordering", "-quotation_date"))

    def list(self, request):
        return self._list(self.get_queryset())

    def retrieve(self, request, pk=None):
        return Response(
            QuotationDetailSerializer(_call(lambda: QuotationService.get_quotation(_tenant(request), pk))).data
        )  # noqa: F405

    def create(self, request):
        s = QuotationWriteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj = _call(
            lambda: QuotationService.create_quotation(
                _tenant(request), _actor(request), _correlation(request), _idempotency(request), dict(s.validated_data)
            )
        )
        return Response(QuotationDetailSerializer(obj).data, status=201)  # noqa: F405

    def partial_update(self, request, pk=None):
        s = QuotationWriteSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        v = dict(s.validated_data)
        obj = _call(
            lambda: QuotationService.update_draft(
                _tenant(request), pk, _actor(request), _correlation(request), _expected(request, v), v
            )
        )
        return Response(QuotationDetailSerializer(obj).data)  # noqa: F405

    def destroy(self, request, pk=None):
        obj = _call(
            lambda: QuotationService.archive_draft(
                _tenant(request), pk, _actor(request), _correlation(request), _expected(request, {})
            )
        )
        return Response(QuotationDetailSerializer(obj).data)  # noqa: F405

    @action(detail=False, methods=["post"])
    def preview(self, request):
        s = QuotationPreviewSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        result = _call(
            lambda: QuotationService.preview_quotation(_tenant(request), _actor(request), dict(s.validated_data))
        )
        return Response(QuotationPreviewResultSerializer(result).data)

    def _command(self, request, pk, method):
        s = QuotationCommandSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        kwargs = {}  # noqa: F405
        if method == "reject":
            kwargs["reason"] = s.validated_data.get("reason", "")
        obj = _call(
            lambda: getattr(QuotationService, method)(
                _tenant(request), pk, _actor(request), _correlation(request), _idempotency(request), **kwargs
            )
        )
        serializer = SalesOrderDetailSerializer if method == "convert_to_sales_order" else QuotationDetailSerializer
        return Response(serializer(obj).data)  # noqa: F405

    @action(detail=True, methods=["post"], url_path="commands/send")
    def send(self, request, pk=None):
        return self._command(request, pk, "send")

    @action(detail=True, methods=["post"], url_path="commands/accept")
    def accept(self, request, pk=None):
        return self._command(request, pk, "accept")

    @action(detail=True, methods=["post"], url_path="commands/reject")
    def reject(self, request, pk=None):
        return self._command(request, pk, "reject")

    @action(detail=True, methods=["post"], url_path="commands/expire")
    def expire(self, request, pk=None):
        return self._command(request, pk, "expire")

    @action(detail=True, methods=["post"], url_path="commands/revise")
    def revise(self, request, pk=None):
        return self._command(request, pk, "revise")

    @action(detail=True, methods=["post"], url_path="commands/convert")
    def convert(self, request, pk=None):
        return self._command(request, pk, "convert_to_sales_order")


class SalesOrderViewSet(SalesViewSet):
    model = SalesOrder
    service = SalesOrderService
    action_permissions = {
        "list": ORDER_READ,
        "retrieve": ORDER_READ,
        "create": ORDER_CREATE,
        "partial_update": ORDER_UPDATE,
        "destroy": ORDER_DELETE,
        "confirm": ORDER_CONFIRM,
        "start_picking": ORDER_FULFILL,
        "start_packing": ORDER_FULFILL,
        "mark_ready": ORDER_FULFILL,
        "ship": ORDER_FULFILL,
        "deliver": ORDER_FULFILL,
        "mark_invoiced": ORDER_INVOICE,
        "cancel": ORDER_CANCEL,
    }  # noqa: F405
    serializer_classes = {
        **{
            name: SalesOrderCommandSerializer
            for name in (
                "confirm",
                "start_picking",
                "start_packing",
                "mark_ready",
                "ship",
                "deliver",
                "mark_invoiced",
                "cancel",
            )
        },
        "list": SalesOrderListSerializer,
        "retrieve": SalesOrderDetailSerializer,
        "create": SalesOrderWriteSerializer,
        "partial_update": SalesOrderWriteSerializer,
        "destroy": SalesOrderDetailSerializer,
    }  # noqa: F405

    def get_queryset(self):
        p = self.request.query_params
        return SalesOrderService.list_orders(_tenant(self.request), p, None, p.get("ordering", "-order_date"))

    def list(self, request):
        return self._list(self.get_queryset())

    def retrieve(self, request, pk=None):
        return Response(
            SalesOrderDetailSerializer(_call(lambda: SalesOrderService.get_order(_tenant(request), pk))).data
        )  # noqa: F405

    def create(self, request):
        s = SalesOrderWriteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj = _call(
            lambda: SalesOrderService.create_order(
                _tenant(request), _actor(request), _correlation(request), _idempotency(request), dict(s.validated_data)
            )
        )
        return Response(SalesOrderDetailSerializer(obj).data, status=201)  # noqa: F405

    def partial_update(self, request, pk=None):
        s = SalesOrderWriteSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        v = dict(s.validated_data)
        obj = _call(
            lambda: SalesOrderService.update_draft(
                _tenant(request), pk, _actor(request), _correlation(request), _expected(request, v), v
            )
        )
        return Response(SalesOrderDetailSerializer(obj).data)  # noqa: F405

    def destroy(self, request, pk=None):
        obj = _call(
            lambda: SalesOrderService.archive_draft(
                _tenant(request), pk, _actor(request), _correlation(request), _expected(request, {})
            )
        )
        return Response(SalesOrderDetailSerializer(obj).data)  # noqa: F405

    def _command(self, request, pk, method):
        s = SalesOrderCommandSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        kwargs = {}  # noqa: F405
        if method == "cancel":
            kwargs["reason"] = s.validated_data.get("reason", "")
        if method == "mark_invoiced":
            kwargs["invoice_id"] = s.validated_data.get("invoice_id")
        obj = _call(
            lambda: getattr(SalesOrderService, method)(
                _tenant(request), pk, _actor(request), _correlation(request), _idempotency(request), **kwargs
            )
        )
        return Response(SalesOrderDetailSerializer(obj).data)  # noqa: F405

    @action(detail=True, methods=["post"], url_path="commands/confirm")
    def confirm(self, r, pk=None):
        return self._command(r, pk, "confirm")

    @action(detail=True, methods=["post"], url_path="commands/start-picking")
    def start_picking(self, r, pk=None):
        return self._command(r, pk, "start_picking")

    @action(detail=True, methods=["post"], url_path="commands/start-packing")
    def start_packing(self, r, pk=None):
        return self._command(r, pk, "start_packing")

    @action(detail=True, methods=["post"], url_path="commands/mark-ready")
    def mark_ready(self, r, pk=None):
        return self._command(r, pk, "mark_ready")

    @action(detail=True, methods=["post"], url_path="commands/ship")
    def ship(self, r, pk=None):
        return self._command(r, pk, "ship")

    @action(detail=True, methods=["post"], url_path="commands/deliver")
    def deliver(self, r, pk=None):
        return self._command(r, pk, "deliver")

    @action(detail=True, methods=["post"], url_path="commands/mark-invoiced")
    def mark_invoiced(self, r, pk=None):
        return self._command(r, pk, "mark_invoiced")

    @action(detail=True, methods=["post"], url_path="commands/cancel")
    def cancel(self, r, pk=None):
        return self._command(r, pk, "cancel")


class DeliveryNoteViewSet(SalesViewSet):
    model = DeliveryNote
    service = DeliveryNoteService
    action_permissions = {
        "list": DELIVERY_READ,
        "retrieve": DELIVERY_READ,
        "create": DELIVERY_CREATE,
        "partial_update": DELIVERY_UPDATE,
        "destroy": DELIVERY_DELETE,
        "complete": DELIVERY_COMPLETE,
        "cancel": DELIVERY_CANCEL,
    }  # noqa: F405
    serializer_classes = {
        "list": DeliveryNoteListSerializer,
        "retrieve": DeliveryNoteDetailSerializer,
        "create": DeliveryNoteWriteSerializer,
        "partial_update": DeliveryNoteWriteSerializer,
        "destroy": DeliveryNoteDetailSerializer,
        "complete": DeliveryNoteCommandSerializer,
        "cancel": DeliveryNoteCommandSerializer,
    }  # noqa: F405

    def get_queryset(self):
        p = self.request.query_params
        return DeliveryNoteService.list_delivery_notes(
            _tenant(self.request), p, None, p.get("ordering", "-delivery_date")
        )

    def list(self, r):
        return self._list(self.get_queryset())

    def retrieve(self, r, pk=None):
        return Response(
            DeliveryNoteDetailSerializer(_call(lambda: DeliveryNoteService.get_delivery_note(_tenant(r), pk))).data
        )  # noqa: F405

    def create(self, r):
        s = DeliveryNoteWriteSerializer(data=r.data)
        s.is_valid(raise_exception=True)
        obj = _call(
            lambda: DeliveryNoteService.create_delivery_note(
                _tenant(r), _actor(r), _correlation(r), _idempotency(r), dict(s.validated_data)
            )
        )
        return Response(DeliveryNoteDetailSerializer(obj).data, status=201)  # noqa: F405

    def partial_update(self, r, pk=None):
        s = DeliveryNoteWriteSerializer(data=r.data, partial=True)
        s.is_valid(raise_exception=True)
        v = dict(s.validated_data)
        obj = _call(
            lambda: DeliveryNoteService.update_draft(_tenant(r), pk, _actor(r), _correlation(r), _expected(r, v), v)
        )
        return Response(DeliveryNoteDetailSerializer(obj).data)  # noqa: F405

    def destroy(self, r, pk=None):
        obj = _call(
            lambda: DeliveryNoteService.archive_draft(_tenant(r), pk, _actor(r), _correlation(r), _expected(r, {}))
        )
        return Response(DeliveryNoteDetailSerializer(obj).data)  # noqa: F405

    def _command(self, r, pk, method):
        s = DeliveryNoteCommandSerializer(data=r.data)
        s.is_valid(raise_exception=True)
        obj = _call(
            lambda: getattr(DeliveryNoteService, method)(_tenant(r), pk, _actor(r), _correlation(r), _idempotency(r))
        )
        return Response(DeliveryNoteDetailSerializer(obj).data)  # noqa: F405

    @action(detail=True, methods=["post"], url_path="commands/complete")
    def complete(self, r, pk=None):
        return self._command(r, pk, "complete")

    @action(detail=True, methods=["post"], url_path="commands/cancel")
    def cancel(self, r, pk=None):
        return self._command(r, pk, "cancel")


class ConfigurationViewSet(GovernedAPIViewMixin, SalesAccessMixin, viewsets.ViewSet):  # type: ignore[misc]
    action_permissions = {
        "current": CONFIG_READ,
        "apply": CONFIG_UPDATE,
        "preview": CONFIG_UPDATE,
        "versions": CONFIG_READ,
        "version_detail": CONFIG_READ,
        "rollback": CONFIG_ROLLBACK,
        "export": CONFIG_EXPORT,
        "import_configuration": CONFIG_IMPORT,
    }  # noqa: F405

    def _environment(self):
        from django.conf import settings

        return str(getattr(settings, "SARAISE_ENVIRONMENT", getattr(settings, "SARAISE_MODE", "development")))

    def current(self, r):
        return Response(
            SalesConfigurationSerializer(
                _call(lambda: SalesConfigurationService.get_current(_tenant(r), self._environment()))
            ).data
        )  # noqa: F405

    def apply(self, r):
        proposed = r.data.get("proposed_values", r.data)
        s = SalesConfigurationWriteSerializer(data=proposed)
        s.is_valid(raise_exception=True)
        v = dict(s.validated_data)
        expected = _expected(r, {"expected_version": r.data.get("expected_version")})
        reason = str(r.data.get("reason", ""))
        obj = _call(
            lambda: SalesConfigurationService.apply_change(
                _tenant(r), _actor(r), _correlation(r), self._environment(), expected, v, reason
            )
        )
        return Response(SalesConfigurationSerializer(obj).data)  # noqa: F405

    def preview(self, r):
        proposed = r.data.get("proposed_values", r.data)
        s = SalesConfigurationWriteSerializer(data=proposed, partial=True)
        s.is_valid(raise_exception=True)
        v = dict(s.validated_data)
        v.pop("expected_version", None)
        v.pop("reason", None)
        return Response(
            _call(lambda: SalesConfigurationService.preview_change(_tenant(r), _actor(r), self._environment(), v))
        )

    def versions(self, r):
        qs = _call(lambda: SalesConfigurationService.list_versions(_tenant(r), self._environment()))
        p = GovernedPageNumberPagination()
        page = p.paginate_queryset(qs, r, view=self)
        data = SalesConfigurationVersionSerializer(page, many=True).data
        return p.get_paginated_response(data)  # noqa: F405

    def version_detail(self, r, version=None):
        return Response(
            SalesConfigurationVersionSerializer(
                _call(lambda: SalesConfigurationService.get_version(_tenant(r), self._environment(), version))
            ).data
        )  # noqa: F405

    def rollback(self, r):
        s = ConfigurationRollbackSerializer(data=r.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        obj = _call(
            lambda: SalesConfigurationService.rollback(
                _tenant(r),
                _actor(r),
                _correlation(r),
                self._environment(),
                v["target_version"],
                v["expected_version"],
                v["reason"],
            )
        )
        return Response(SalesConfigurationSerializer(obj).data)  # noqa: F405

    def export(self, r):
        return Response(_call(lambda: SalesConfigurationService.export_configuration(_tenant(r), self._environment())))

    def import_configuration(self, r):
        s = ConfigurationImportSerializer(data=r.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        result = _call(
            lambda: SalesConfigurationService.import_configuration(
                _tenant(r),
                _actor(r),
                _correlation(r),
                self._environment(),
                v["expected_version"],
                v["document"],
                v["dry_run"],
                v["reason"],
            )
        )
        return Response(
            SalesConfigurationSerializer(result).data if isinstance(result, SalesConfiguration) else result
        )  # noqa: F405


class SalesInsightsViewSet(GovernedAPIViewMixin, SalesAccessMixin, viewsets.ViewSet):  # type: ignore[misc]
    """Authoritative dashboard aggregates and extension availability."""

    action_permissions = {"summary": ORDER_READ, "capabilities": CUSTOMER_READ}  # noqa: F405

    def summary(self, request: Request) -> Response:
        return Response(_call(lambda: SalesDashboardService.summary(_tenant(request))))

    def capabilities(self, request: Request) -> Response:
        return Response(_call(lambda: SalesDashboardService.capabilities(_tenant(request))))
