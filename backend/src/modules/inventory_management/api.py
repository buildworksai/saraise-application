"""Governed v2 HTTP adapters for inventory services.

Controllers validate transport data, establish tenant/actor/idempotency inputs,
and delegate every mutation to ``services.py``.  They never call ``save`` or
``delete`` on a model instance.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import F, Q, QuerySet
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination
from src.core.api.envelope import correlation_id_for_request
from src.core.auth_utils import get_user_tenant_id

from .models import (
    Batch, CycleCount, InventoryConfiguration, Item, SerialNumber, StockBalance,
    StockEntry, StockLedgerEntry, StockReservation, StorageLocation, Warehouse,
)
from .permissions import *  # noqa: F403 - constants form the auditable route map
from .serializers import *  # noqa: F403 - explicit serializer lookup maps below
from .services import (
    BatchService, CycleCountService, InventoryBulkService, InventoryConfigurationService,
    InventoryPostingService, InventoryQueryService, ItemService, ReservationService,
    SerialNumberService, StockEntryService, StorageLocationService, WarehouseService,
)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The operation conflicts with the current resource state."
    default_code = "conflict"


class Unprocessable(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "The command is valid JSON but violates an inventory rule."
    default_code = "unprocessable_entity"


def _tenant(request: Request) -> uuid.UUID:
    value = getattr(request, "tenant_id", None) or get_user_tenant_id(request.user)
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PermissionDenied("Authenticated tenant context is required.") from exc


def _actor(request: Request) -> uuid.UUID:
    value = getattr(request.user, "id", getattr(request.user, "pk", None))
    if value is None:
        raise PermissionDenied("Authenticated actor identity is required.")
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        # Django's default user key is an integer while domain audit columns
        # are UUIDs.  UUIDv5 gives that stable local identity a deterministic,
        # non-guess-dependent domain identifier without changing auth models.
        return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise-user:{value}")


def _idempotency_key(request: Request) -> str:
    value = request.headers.get("Idempotency-Key", "").strip()
    if not value or len(value) > 255:
        raise ValidationError({"idempotency_key": ["Idempotency-Key is required and must be at most 255 characters."]})
    return value


def _expected_version(request: Request, values: dict[str, Any]) -> int:
    raw = values.pop("expected_version", None)
    if raw is None:
        raw = request.headers.get("If-Match")
    if isinstance(raw, str):
        raw = raw.strip().removeprefix("W/").strip('"')
    try:
        version = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"expected_version": ["If-Match or expected_version is required."]}) from exc
    if version < 1:
        raise ValidationError({"expected_version": ["Version must be a positive integer."]})
    return version


def _call(operation: Callable[[], Any]) -> Any:
    """Map domain failures to stable, non-leaking API errors."""

    try:
        return operation()
    except IntegrityError as exc:
        raise Conflict("The command conflicts with persisted inventory data.") from exc
    except DjangoValidationError as exc:
        detail = getattr(exc, "message_dict", None) or {"non_field_errors": getattr(exc, "messages", ["Inventory validation failed."])}
        raise ValidationError(detail) from exc
    except PermissionError as exc:
        raise PermissionDenied(str(exc)) from exc
    except (KeyError, TypeError) as exc:
        raise ValidationError({"non_field_errors": ["The command document is invalid."]}) from exc
    except LookupError as exc:
        raise NotFound("The requested inventory resource was not found.") from exc
    except ValueError as exc:
        raise Unprocessable(str(exc)) from exc


def _manager_for_tenant(model: type[Any], tenant_id: uuid.UUID) -> QuerySet[Any]:
    manager = model.objects
    if hasattr(manager, "for_tenant"):
        return manager.for_tenant(tenant_id)
    return manager.filter(tenant_id=tenant_id)


class InventoryViewSet(GovernedAPIViewMixin, InventoryAccessMixin, viewsets.GenericViewSet):  # type: ignore[misc]  # noqa: F405
    """Common tenant isolation, pagination, filtering, and serialization."""

    pagination_class = GovernedPageNumberPagination
    model: type[Any]
    serializer_classes: Mapping[str, type[Any]] = {}
    search_fields: tuple[str, ...] = ()
    exact_filters: Mapping[str, str] = {}
    ordering_fields: tuple[str, ...] = ()
    default_ordering: tuple[str, ...] = ("id",)

    def get_serializer_class(self):  # type: ignore[no-untyped-def]
        serializer = self.serializer_classes.get(self.action)
        if serializer is None:
            raise RuntimeError(f"No serializer declared for {type(self).__name__}.{self.action}")
        return serializer

    def get_queryset(self) -> QuerySet[Any]:
        queryset = _manager_for_tenant(self.model, _tenant(self.request))
        params = self.request.query_params
        for parameter, field in self.exact_filters.items():
            value = params.get(parameter)
            if value not in (None, ""):
                queryset = queryset.filter(**{field: value})
        search = params.get("search", "").strip()
        if search and self.search_fields:
            predicate = Q()
            for field in self.search_fields:
                predicate |= Q(**{f"{field}__icontains": search})
            queryset = queryset.filter(predicate)
        ordering = tuple(part.strip() for part in params.get("ordering", "").split(",") if part.strip())
        allowed = set(self.ordering_fields)
        if ordering and all(part.removeprefix("-") in allowed for part in ordering):
            fields = ordering
        else:
            fields = self.default_ordering
        if not any(part.removeprefix("-") == "id" for part in fields):
            fields = (*fields, "id")
        return self.apply_filters(queryset, params).order_by(*fields)

    def apply_filters(self, queryset: QuerySet[Any], params: Mapping[str, Any]) -> QuerySet[Any]:
        del params
        return queryset

    def get_object(self):  # type: ignore[no-untyped-def]
        obj = super().get_object()
        self.check_object_permissions(self.request, obj)
        return obj

    def _serialize(self, instance: Any, *, many: bool = False, serializer_class: type[Any] | None = None):
        return (serializer_class or self.get_serializer_class())(instance, many=many, context=self.get_serializer_context())

    def list(self, request: Request) -> Response:
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = self._serialize(page if page is not None else queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        return Response(self._serialize(self.get_object()).data)


class WarehouseViewSet(InventoryViewSet):
    model = Warehouse
    action_permissions = {"list": WAREHOUSE_READ, "retrieve": WAREHOUSE_READ, "create": WAREHOUSE_CREATE,
                          "partial_update": WAREHOUSE_UPDATE, "destroy": WAREHOUSE_DELETE, "set_default": WAREHOUSE_UPDATE}  # noqa: F405
    serializer_classes = {"list": WarehouseListSerializer, "retrieve": WarehouseDetailSerializer,
                          "create": WarehouseCreateSerializer, "partial_update": WarehouseUpdateSerializer,
                          "destroy": WarehouseDetailSerializer, "set_default": WarehouseDetailSerializer}  # noqa: F405
    search_fields = ("warehouse_code", "warehouse_name", "city")
    exact_filters = {"warehouse_type": "warehouse_type", "is_active": "is_active", "is_default": "is_default"}
    ordering_fields = ("warehouse_code", "warehouse_name", "warehouse_type", "created_at", "updated_at")
    default_ordering = ("warehouse_code",)

    def create(self, request: Request) -> Response:
        serializer = WarehouseCreateSerializer(data=request.data)  # noqa: F405
        serializer.is_valid(raise_exception=True)
        obj = _call(lambda: WarehouseService.create(_tenant(request), _actor(request), dict(serializer.validated_data), _idempotency_key(request)))
        return Response(WarehouseDetailSerializer(obj).data, status=status.HTTP_201_CREATED)  # noqa: F405

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object()
        serializer = WarehouseUpdateSerializer(data=request.data, partial=True)  # noqa: F405
        serializer.is_valid(raise_exception=True)
        command = dict(serializer.validated_data)
        updated = _call(lambda: WarehouseService.update(_tenant(request), obj.id, _expected_version(request, command), _actor(request), command))
        return Response(WarehouseDetailSerializer(updated).data)  # noqa: F405

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object()
        archived = _call(lambda: WarehouseService.archive(_tenant(request), obj.id, _expected_version(request, {}), _actor(request)))
        return Response(WarehouseDetailSerializer(archived).data)  # noqa: F405

    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object()
        updated = _call(lambda: WarehouseService.set_default(_tenant(request), obj.id, _actor(request), _idempotency_key(request)))
        return Response(WarehouseDetailSerializer(updated).data)  # noqa: F405


class StorageLocationViewSet(InventoryViewSet):
    model = StorageLocation
    action_permissions = {"list": LOCATION_READ, "retrieve": LOCATION_READ, "create": LOCATION_CREATE,
                          "partial_update": LOCATION_UPDATE, "destroy": LOCATION_DELETE}  # noqa: F405
    serializer_classes = {"list": StorageLocationListSerializer, "retrieve": StorageLocationDetailSerializer,
                          "create": StorageLocationCreateSerializer, "partial_update": StorageLocationUpdateSerializer,
                          "destroy": StorageLocationDetailSerializer}  # noqa: F405
    search_fields = ("location_code", "location_name", "barcode")
    exact_filters = {"warehouse_id": "warehouse_id", "zone_type": "zone_type", "location_type": "location_type",
                     "is_active": "is_active", "barcode": "barcode"}
    ordering_fields = ("location_code", "location_name", "pick_sequence", "created_at")
    default_ordering = ("warehouse_id", "pick_sequence", "location_code")

    def create(self, request: Request) -> Response:
        serializer = StorageLocationCreateSerializer(data=request.data)  # noqa: F405
        serializer.is_valid(raise_exception=True)
        obj = _call(lambda: StorageLocationService.create(_tenant(request), _actor(request), dict(serializer.validated_data), _idempotency_key(request)))
        return Response(StorageLocationDetailSerializer(obj).data, status=status.HTTP_201_CREATED)  # noqa: F405

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object(); serializer = StorageLocationUpdateSerializer(data=request.data, partial=True)  # noqa: F405,E702
        serializer.is_valid(raise_exception=True); command = dict(serializer.validated_data)  # noqa: E702
        result = _call(lambda: StorageLocationService.update(_tenant(request), obj.id, _expected_version(request, command), _actor(request), command))
        return Response(StorageLocationDetailSerializer(result).data)  # noqa: F405

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object()
        result = _call(lambda: StorageLocationService.archive(_tenant(request), obj.id, _expected_version(request, {}), _actor(request)))
        return Response(StorageLocationDetailSerializer(result).data)  # noqa: F405


class ItemViewSet(InventoryViewSet):
    model = Item
    action_permissions = {"list": ITEM_READ, "retrieve": ITEM_READ, "create": ITEM_CREATE,
                          "partial_update": ITEM_UPDATE, "destroy": ITEM_DELETE}  # noqa: F405
    serializer_classes = {"list": ItemListSerializer, "retrieve": ItemDetailSerializer, "create": ItemCreateSerializer,
                          "partial_update": ItemUpdateSerializer, "destroy": ItemDetailSerializer}  # noqa: F405
    search_fields = ("item_code", "item_name", "description", "barcode")
    exact_filters = {"category": "category", "tracking_mode": "tracking_mode", "valuation_method": "valuation_method", "is_active": "is_active"}
    ordering_fields = ("item_code", "item_name", "category", "reorder_point", "created_at")
    default_ordering = ("item_code",)

    def apply_filters(self, queryset: QuerySet[Any], params: Mapping[str, Any]) -> QuerySet[Any]:
        if str(params.get("below_reorder", "")).lower() in {"1", "true"}:
            queryset = queryset.filter(
                reorder_point__isnull=False,
                stock_balances__quantity_available__lt=F("reorder_point"),
            ).distinct()
        return queryset

    def create(self, request: Request) -> Response:
        serializer = ItemCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True)  # noqa: F405,E702
        obj = _call(lambda: ItemService.create(_tenant(request), _actor(request), dict(serializer.validated_data), _idempotency_key(request)))
        return Response(ItemDetailSerializer(obj).data, status=status.HTTP_201_CREATED)  # noqa: F405

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object(); serializer = ItemUpdateSerializer(data=request.data, partial=True)  # noqa: F405,E702
        serializer.is_valid(raise_exception=True); command = dict(serializer.validated_data)  # noqa: E702
        result = _call(lambda: ItemService.update(_tenant(request), obj.id, _expected_version(request, command), _actor(request), command))
        return Response(ItemDetailSerializer(result).data)  # noqa: F405

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object()
        result = _call(lambda: ItemService.archive(_tenant(request), obj.id, _expected_version(request, {}), _actor(request)))
        return Response(ItemDetailSerializer(result).data)  # noqa: F405


class BatchViewSet(InventoryViewSet):
    model = Batch
    action_permissions = {"list": BATCH_READ, "retrieve": BATCH_READ, "create": BATCH_CREATE,
                          "partial_update": BATCH_UPDATE, "activate": BATCH_TRANSITION, "quarantine": BATCH_TRANSITION,
                          "release": BATCH_TRANSITION, "recall": BATCH_TRANSITION, "trace": BATCH_READ}  # noqa: F405
    serializer_classes = {"list": BatchListSerializer, "retrieve": BatchDetailSerializer, "create": BatchCreateSerializer,
                          "partial_update": BatchUpdateSerializer, "activate": VersionedCommandSerializer,
                          "quarantine": VersionedCommandSerializer, "release": VersionedCommandSerializer,
                          "recall": ReasonCommandSerializer, "trace": StockLedgerSerializer}  # noqa: F405
    search_fields = ("batch_number", "supplier_batch_number")
    exact_filters = {"item_id": "item_id", "status": "status"}
    ordering_fields = ("batch_number", "expires_on", "status", "created_at")
    default_ordering = ("item_id", "batch_number")

    def apply_filters(self, queryset: QuerySet[Any], params: Mapping[str, Any]) -> QuerySet[Any]:
        if params.get("expires_before"): queryset = queryset.filter(expires_on__lte=params["expires_before"])
        if params.get("expires_after"): queryset = queryset.filter(expires_on__gte=params["expires_after"])
        return queryset

    def create(self, request: Request) -> Response:
        serializer = BatchCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True)  # noqa: F405,E702
        obj = _call(lambda: BatchService.register(_tenant(request), _actor(request), dict(serializer.validated_data), _idempotency_key(request)))
        return Response(BatchDetailSerializer(obj).data, status=status.HTTP_201_CREATED)  # noqa: F405

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object(); serializer = BatchUpdateSerializer(data=request.data, partial=True)  # noqa: F405,E702
        serializer.is_valid(raise_exception=True); command = dict(serializer.validated_data)  # noqa: E702
        result = _call(lambda: BatchService.update_metadata(_tenant(request), obj.id, _expected_version(request, command), _actor(request), command))
        return Response(BatchDetailSerializer(result).data)  # noqa: F405

    def _transition(self, request: Request, method: str) -> Response:
        obj = self.get_object(); serializer = self.get_serializer(data=request.data)  # noqa: E702
        serializer.is_valid(raise_exception=True)
        result = _call(lambda: getattr(BatchService, method)(_tenant(request), obj.id, _actor(request), _idempotency_key(request)))
        return Response(BatchDetailSerializer(result).data)  # noqa: F405

    @action(detail=True, methods=["post"])
    def activate(self, request: Request, pk: str | None = None) -> Response: return self._transition(request, "activate")
    @action(detail=True, methods=["post"])
    def quarantine(self, request: Request, pk: str | None = None) -> Response: return self._transition(request, "quarantine")
    @action(detail=True, methods=["post"])
    def release(self, request: Request, pk: str | None = None) -> Response: return self._transition(request, "release")
    @action(detail=True, methods=["post"])
    def recall(self, request: Request, pk: str | None = None) -> Response: return self._transition(request, "recall")

    @action(detail=True, methods=["get"])
    def trace(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object()
        ledger = _call(lambda: InventoryQueryService.trace_batch(_tenant(request), obj.id))
        page = self.paginate_queryset(ledger)
        serializer = StockLedgerSerializer(page if page is not None else ledger, many=True)  # noqa: F405
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)


class SerialNumberViewSet(InventoryViewSet):
    model = SerialNumber
    action_permissions = {"list": SERIAL_READ, "retrieve": SERIAL_READ, "create": SERIAL_CREATE,
                          "partial_update": SERIAL_UPDATE, "trace": SERIAL_READ}  # noqa: F405
    serializer_classes = {"list": SerialNumberListSerializer, "retrieve": SerialNumberDetailSerializer,
                          "create": SerialNumberCreateSerializer, "partial_update": SerialNumberUpdateSerializer,
                          "trace": SerialNumberDetailSerializer}  # noqa: F405
    search_fields = ("serial_number", "manufacturer", "model_number")
    exact_filters = {"item_id": "item_id", "status": "status", "warehouse_id": "current_warehouse_id", "location_id": "current_location_id"}
    ordering_fields = ("serial_number", "status", "created_at")
    default_ordering = ("serial_number",)

    def create(self, request: Request) -> Response:
        serializer = SerialNumberCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True)  # noqa: F405,E702
        obj = _call(lambda: SerialNumberService.register(_tenant(request), _actor(request), dict(serializer.validated_data), _idempotency_key(request)))
        return Response(SerialNumberDetailSerializer(obj).data, status=status.HTTP_201_CREATED)  # noqa: F405

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object(); serializer = SerialNumberUpdateSerializer(data=request.data, partial=True)  # noqa: F405,E702
        serializer.is_valid(raise_exception=True); command = dict(serializer.validated_data)  # noqa: E702
        result = _call(lambda: SerialNumberService.update_metadata(_tenant(request), obj.id, _expected_version(request, command), _actor(request), command))
        return Response(SerialNumberDetailSerializer(result).data)  # noqa: F405

    @action(detail=True, methods=["get"])
    def trace(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object()
        ledger = _call(lambda: InventoryQueryService.trace_serial(_tenant(request), obj.id))
        return Response(StockLedgerSerializer(ledger, many=True).data)  # noqa: F405


class StockEntryViewSet(InventoryViewSet):
    model = StockEntry
    action_permissions = {"list": STOCK_ENTRY_READ, "retrieve": STOCK_ENTRY_READ, "create": STOCK_ENTRY_CREATE,
                          "partial_update": STOCK_ENTRY_UPDATE, "destroy": STOCK_ENTRY_DELETE, "submit": STOCK_ENTRY_SUBMIT,
                          "approve": STOCK_ENTRY_APPROVE, "reject": STOCK_ENTRY_REJECT, "post": STOCK_ENTRY_POST,
                          "cancel": STOCK_ENTRY_CANCEL, "reverse": STOCK_ENTRY_REVERSE}  # noqa: F405
    action_quotas = {"post": POST_QUOTA}  # noqa: F405
    serializer_classes = {"list": StockEntryListSerializer, "retrieve": StockEntryDetailSerializer,
                          "create": StockEntryCreateSerializer, "partial_update": StockEntryUpdateSerializer,
                          "destroy": StockEntryDetailSerializer, "submit": VersionedCommandSerializer,
                          "approve": VersionedCommandSerializer, "reject": ReasonCommandSerializer,
                          "post": VersionedCommandSerializer, "cancel": ReasonCommandSerializer,
                          "reverse": ReasonCommandSerializer}  # noqa: F405
    search_fields = ("entry_number", "reason", "reference_module", "reference_type")
    exact_filters = {"entry_type": "entry_type", "status": "status", "reference_id": "reference_id"}
    ordering_fields = ("entry_number", "posting_at", "entry_type", "status", "created_at")
    default_ordering = ("-posting_at", "entry_number")

    def apply_filters(self, queryset: QuerySet[Any], params: Mapping[str, Any]) -> QuerySet[Any]:
        if params.get("from"): queryset = queryset.filter(posting_at__gte=params["from"])
        if params.get("to"): queryset = queryset.filter(posting_at__lte=params["to"])
        if params.get("warehouse_id"):
            queryset = queryset.filter(Q(source_warehouse_id=params["warehouse_id"]) | Q(destination_warehouse_id=params["warehouse_id"]))
        return queryset

    def create(self, request: Request) -> Response:
        serializer = StockEntryCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True)  # noqa: F405,E702
        obj = _call(lambda: StockEntryService.create_draft(_tenant(request), _actor(request), dict(serializer.validated_data), _idempotency_key(request)))
        return Response(StockEntryDetailSerializer(obj).data, status=status.HTTP_201_CREATED)  # noqa: F405

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object(); serializer = StockEntryUpdateSerializer(data=request.data, partial=True)  # noqa: F405,E702
        serializer.is_valid(raise_exception=True); command = dict(serializer.validated_data)  # noqa: E702
        result = _call(lambda: StockEntryService.update_draft(_tenant(request), obj.id, _expected_version(request, command), _actor(request), command))
        return Response(StockEntryDetailSerializer(result).data)  # noqa: F405

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object()
        result = _call(lambda: StockEntryService.delete_draft(_tenant(request), obj.id, _expected_version(request, {}), _actor(request)))
        return Response(StockEntryDetailSerializer(result).data)  # noqa: F405

    def _command(self, request: Request, method: str, *, posting: bool = False) -> Response:
        obj = self.get_object(); serializer = self.get_serializer(data=request.data)  # noqa: E702
        serializer.is_valid(raise_exception=True); values = dict(serializer.validated_data)  # noqa: E702
        key = _idempotency_key(request)
        if posting:
            result = _call(lambda: InventoryPostingService.post(_tenant(request), obj.id, _actor(request), key))
        elif method == "reverse":
            result = _call(lambda: StockEntryService.reverse(_tenant(request), obj.id, _actor(request), values["reason"], key))
        else:
            result = _call(lambda: getattr(StockEntryService, method)(_tenant(request), obj.id, _actor(request), key))
        return Response(StockEntryDetailSerializer(result).data)  # noqa: F405

    @action(detail=True, methods=["post"])
    def submit(self, request: Request, pk: str | None = None) -> Response: return self._command(request, "submit")
    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk: str | None = None) -> Response: return self._command(request, "approve")
    @action(detail=True, methods=["post"])
    def reject(self, request: Request, pk: str | None = None) -> Response: return self._command(request, "reject")
    @action(detail=True, methods=["post"])
    def post(self, request: Request, pk: str | None = None) -> Response: return self._command(request, "post", posting=True)
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str | None = None) -> Response: return self._command(request, "cancel")
    @action(detail=True, methods=["post"])
    def reverse(self, request: Request, pk: str | None = None) -> Response: return self._command(request, "reverse")


class StockBalanceViewSet(InventoryViewSet):
    model = StockBalance
    action_permissions = {"list": STOCK_BALANCE_READ, "retrieve": STOCK_BALANCE_READ}  # noqa: F405
    serializer_classes = {"list": StockBalanceSerializer, "retrieve": StockBalanceSerializer}  # noqa: F405
    exact_filters = {"item_id": "item_id", "warehouse_id": "warehouse_id", "location_id": "location_id", "batch_id": "batch_id", "serial_id": "serial_number_id"}
    ordering_fields = ("item_id", "warehouse_id", "quantity_on_hand", "quantity_available", "stock_value", "updated_at")
    default_ordering = ("item_id", "warehouse_id", "location_id")

    def apply_filters(self, queryset: QuerySet[Any], params: Mapping[str, Any]) -> QuerySet[Any]:
        if str(params.get("nonzero", "")).lower() in {"1", "true"}: queryset = queryset.exclude(quantity_on_hand=0)
        if str(params.get("below_reorder", "")).lower() in {"1", "true"}:
            queryset = queryset.filter(item__reorder_point__isnull=False, quantity_available__lt=F("item__reorder_point"))
        return queryset


class StockLedgerViewSet(InventoryViewSet):
    model = StockLedgerEntry
    action_permissions = {"list": STOCK_LEDGER_READ, "retrieve": STOCK_LEDGER_READ}  # noqa: F405
    serializer_classes = {"list": StockLedgerSerializer, "retrieve": StockLedgerSerializer}  # noqa: F405
    exact_filters = {"item_id": "item_id", "warehouse_id": "warehouse_id", "location_id": "location_id", "batch_id": "batch_id", "serial_id": "serial_number_id", "entry_id": "stock_entry_id"}
    ordering_fields = ("sequence", "posted_at", "item_id", "warehouse_id")
    default_ordering = ("-sequence",)

    def apply_filters(self, queryset: QuerySet[Any], params: Mapping[str, Any]) -> QuerySet[Any]:
        if params.get("from"): queryset = queryset.filter(posted_at__gte=params["from"])
        if params.get("to"): queryset = queryset.filter(posted_at__lte=params["to"])
        return queryset


class ReservationViewSet(InventoryViewSet):
    model = StockReservation
    action_permissions = {"list": RESERVATION_READ, "retrieve": RESERVATION_READ, "create": RESERVATION_CREATE,
                          "partial_update": RESERVATION_UPDATE, "release": RESERVATION_TRANSITION,
                          "consume": RESERVATION_TRANSITION, "cancel": RESERVATION_TRANSITION}  # noqa: F405
    serializer_classes = {"list": ReservationListSerializer, "retrieve": ReservationDetailSerializer,
                          "create": ReservationCreateSerializer, "partial_update": ReservationUpdateSerializer,
                          "release": VersionedCommandSerializer, "consume": ReservationConsumeSerializer,
                          "cancel": ReasonCommandSerializer}  # noqa: F405
    exact_filters = {"status": "status", "item_id": "item_id", "reference_id": "reference_id"}
    ordering_fields = ("reservation_number", "status", "expires_at", "created_at")
    default_ordering = ("-created_at",)

    def apply_filters(self, queryset: QuerySet[Any], params: Mapping[str, Any]) -> QuerySet[Any]:
        return queryset.filter(expires_at__lte=params["expires_before"]) if params.get("expires_before") else queryset

    def create(self, request: Request) -> Response:
        serializer = ReservationCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True)  # noqa: F405,E702
        obj = _call(lambda: ReservationService.reserve(_tenant(request), _actor(request), dict(serializer.validated_data), _idempotency_key(request)))
        return Response(ReservationDetailSerializer(obj).data, status=status.HTTP_201_CREATED)  # noqa: F405

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object(); serializer = ReservationUpdateSerializer(data=request.data, partial=True)  # noqa: F405,E702
        serializer.is_valid(raise_exception=True); command = dict(serializer.validated_data)  # noqa: E702
        result = _call(lambda: ReservationService.update(_tenant(request), obj.id, _expected_version(request, command), _actor(request), command))
        return Response(ReservationDetailSerializer(result).data)  # noqa: F405

    def _transition(self, request: Request, method: str) -> Response:
        obj = self.get_object(); serializer = self.get_serializer(data=request.data)  # noqa: E702
        serializer.is_valid(raise_exception=True)
        result = _call(lambda: getattr(ReservationService, method)(_tenant(request), obj.id, _actor(request), _idempotency_key(request)))
        return Response(ReservationDetailSerializer(result).data)  # noqa: F405

    @action(detail=True, methods=["post"])
    def release(self, request: Request, pk: str | None = None) -> Response: return self._transition(request, "release")
    @action(detail=True, methods=["post"])
    def consume(self, request: Request, pk: str | None = None) -> Response: return self._transition(request, "consume")
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str | None = None) -> Response: return self._transition(request, "cancel")


class CycleCountViewSet(InventoryViewSet):
    model = CycleCount
    action_permissions = {"list": CYCLE_COUNT_READ, "retrieve": CYCLE_COUNT_READ, "create": CYCLE_COUNT_CREATE,
                          "partial_update": CYCLE_COUNT_UPDATE, "start": CYCLE_COUNT_START, "submit": CYCLE_COUNT_SUBMIT,
                          "approve": CYCLE_COUNT_APPROVE, "reject": CYCLE_COUNT_REJECT, "post": CYCLE_COUNT_POST,
                          "cancel": CYCLE_COUNT_CANCEL}  # noqa: F405
    action_quotas = {"post": POST_QUOTA}  # noqa: F405
    serializer_classes = {"list": CycleCountListSerializer, "retrieve": CycleCountDetailSerializer,
                          "create": CycleCountCreateSerializer, "partial_update": CycleCountUpdateSerializer,
                          "start": VersionedCommandSerializer, "submit": VersionedCommandSerializer,
                          "approve": VersionedCommandSerializer, "reject": ReasonCommandSerializer,
                          "post": VersionedCommandSerializer, "cancel": ReasonCommandSerializer}  # noqa: F405
    exact_filters = {"warehouse_id": "warehouse_id", "location_id": "location_id", "status": "status", "assigned_to_id": "assigned_to_id"}
    ordering_fields = ("count_number", "scheduled_for", "status", "created_at")
    default_ordering = ("-scheduled_for", "count_number")

    def apply_filters(self, queryset: QuerySet[Any], params: Mapping[str, Any]) -> QuerySet[Any]:
        if params.get("scheduled_from"): queryset = queryset.filter(scheduled_for__gte=params["scheduled_from"])
        if params.get("scheduled_to"): queryset = queryset.filter(scheduled_for__lte=params["scheduled_to"])
        return queryset

    def create(self, request: Request) -> Response:
        serializer = CycleCountCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True)  # noqa: F405,E702
        obj = _call(lambda: CycleCountService.create(_tenant(request), _actor(request), dict(serializer.validated_data), _idempotency_key(request)))
        return Response(CycleCountDetailSerializer(obj).data, status=status.HTTP_201_CREATED)  # noqa: F405

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        obj = self.get_object(); serializer = CycleCountUpdateSerializer(data=request.data, partial=True)  # noqa: F405,E702
        serializer.is_valid(raise_exception=True); command = dict(serializer.validated_data)  # noqa: E702
        result = _call(lambda: CycleCountService.update_scheduled(_tenant(request), obj.id, _expected_version(request, command), _actor(request), command))
        return Response(CycleCountDetailSerializer(result).data)  # noqa: F405

    def _transition(self, request: Request, method: str) -> Response:
        obj = self.get_object(); serializer = self.get_serializer(data=request.data)  # noqa: E702
        serializer.is_valid(raise_exception=True)
        result = _call(lambda: getattr(CycleCountService, method)(_tenant(request), obj.id, _actor(request), _idempotency_key(request)))
        return Response(CycleCountDetailSerializer(result).data)  # noqa: F405

    @action(detail=True, methods=["post"])
    def start(self, request: Request, pk: str | None = None) -> Response: return self._transition(request, "start")
    @action(detail=True, methods=["post"])
    def submit(self, request: Request, pk: str | None = None) -> Response: return self._transition(request, "submit")
    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk: str | None = None) -> Response: return self._transition(request, "approve")
    @action(detail=True, methods=["post"])
    def reject(self, request: Request, pk: str | None = None) -> Response: return self._transition(request, "reject")
    @action(detail=True, methods=["post"])
    def post(self, request: Request, pk: str | None = None) -> Response: return self._transition(request, "post_adjustment")
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str | None = None) -> Response: return self._transition(request, "cancel")


class ConfigurationViewSet(InventoryViewSet):
    model = InventoryConfiguration
    lookup_field = "environment"
    lookup_url_kwarg = "environment"
    action_permissions = {"list": CONFIGURATION_READ, "retrieve": CONFIGURATION_READ,
                          "partial_update": CONFIGURATION_UPDATE, "preview": CONFIGURATION_PREVIEW,
                          "activate": CONFIGURATION_ACTIVATE, "rollback": CONFIGURATION_ROLLBACK,
                          "import_document": CONFIGURATION_IMPORT, "export_document": CONFIGURATION_EXPORT,
                          "history": CONFIGURATION_AUDIT}  # noqa: F405
    serializer_classes = {"list": ConfigurationListSerializer, "retrieve": ConfigurationDetailSerializer,
                          "partial_update": ConfigurationUpdateSerializer, "preview": ConfigurationPreviewSerializer,
                          "activate": ConfigurationActivateSerializer, "rollback": ConfigurationRollbackSerializer,
                          "import_document": ConfigurationImportSerializer, "export_document": ConfigurationDetailSerializer,
                          "history": ConfigurationRevisionSerializer}  # noqa: F405
    ordering_fields = ("environment", "status", "updated_at")
    default_ordering = ("environment",)

    def get_object(self):  # type: ignore[no-untyped-def]
        """Resolve environment inside the authenticated tenant or return 404."""
        environment = self.kwargs.get("environment")
        if not environment:
            raise NotFound("The requested inventory configuration was not found.")
        try:
            configuration = InventoryConfiguration.objects.for_tenant(
                _tenant(self.request)
            ).get(environment=environment)
        except InventoryConfiguration.DoesNotExist as exc:
            raise NotFound("The requested inventory configuration was not found.") from exc
        self.check_object_permissions(self.request, configuration)
        return configuration

    def retrieve(self, request: Request, environment: str | None = None) -> Response:
        del request, environment
        return Response(ConfigurationDetailSerializer(self.get_object()).data)  # noqa: F405

    def partial_update(self, request: Request, environment: str | None = None) -> Response:
        self.get_object()
        serializer = ConfigurationUpdateSerializer(data=request.data, partial=True); serializer.is_valid(raise_exception=True)  # noqa: F405,E702
        values = dict(serializer.validated_data); values.pop("environment", None)  # noqa: E702
        reason = values.pop("change_reason")
        revision = _call(lambda: InventoryConfigurationService.create_revision(
            _tenant(request), environment, _actor(request), values, reason,
            correlation_id_for_request(request),
        ))
        return Response(ConfigurationRevisionSerializer(revision).data, status=status.HTTP_201_CREATED)  # noqa: F405

    @action(detail=True, methods=["post"])
    def preview(self, request: Request, environment: str | None = None) -> Response:
        serializer = ConfigurationPreviewSerializer(data=request.data); serializer.is_valid(raise_exception=True)  # noqa: F405,E702
        return Response(_call(lambda: InventoryConfigurationService.preview(_tenant(request), environment, serializer.validated_data["document"])))

    @action(detail=True, methods=["post"])
    def activate(self, request: Request, environment: str | None = None) -> Response:
        serializer = ConfigurationActivateSerializer(data=request.data); serializer.is_valid(raise_exception=True)  # noqa: F405,E702
        obj = _call(lambda: InventoryConfigurationService.activate(_tenant(request), environment, serializer.validated_data["revision"], _actor(request), _idempotency_key(request)))
        return Response(ConfigurationDetailSerializer(obj).data)  # noqa: F405

    @action(detail=True, methods=["post"])
    def rollback(self, request: Request, environment: str | None = None) -> Response:
        serializer = ConfigurationRollbackSerializer(data=request.data); serializer.is_valid(raise_exception=True)  # noqa: F405,E702
        obj = _call(lambda: InventoryConfigurationService.rollback(_tenant(request), environment, serializer.validated_data["revision"], _actor(request), serializer.validated_data["change_reason"], _idempotency_key(request)))
        return Response(ConfigurationDetailSerializer(obj).data)  # noqa: F405

    @action(detail=True, methods=["post"], url_path="import")
    def import_document(self, request: Request, environment: str | None = None) -> Response:
        serializer = ConfigurationImportSerializer(data=request.data); serializer.is_valid(raise_exception=True)  # noqa: F405,E702
        obj = _call(lambda: InventoryConfigurationService.import_document(_tenant(request), environment, _actor(request), serializer.validated_data["document"], serializer.validated_data["change_reason"], _idempotency_key(request)))
        return Response(ConfigurationRevisionSerializer(obj).data, status=status.HTTP_201_CREATED)  # noqa: F405

    @action(detail=True, methods=["get"], url_path="export")
    def export_document(self, request: Request, environment: str | None = None) -> Response:
        return Response(_call(lambda: InventoryConfigurationService.export_document(_tenant(request), environment)))

    @action(detail=True, methods=["get"])
    def history(self, request: Request, environment: str | None = None) -> Response:
        configuration = self.get_object()
        revisions = configuration.revisions.filter(tenant_id=_tenant(request)).order_by("-revision", "id")
        page = self.paginate_queryset(revisions)
        serializer = ConfigurationRevisionSerializer(page if page is not None else revisions, many=True)  # noqa: F405
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)


class DashboardViewSet(InventoryViewSet):
    model = StockBalance
    action_permissions = {"list": REPORT_READ}  # noqa: F405
    serializer_classes = {"list": StockBalanceSerializer}  # noqa: F405

    def list(self, request: Request) -> Response:
        return Response(_call(lambda: InventoryQueryService.dashboard(_tenant(request))))


class ImportViewSet(GovernedAPIViewMixin, InventoryAccessMixin, viewsets.ViewSet):  # type: ignore[misc]  # noqa: F405
    action_permissions = {"create": BULK_IMPORT}  # noqa: F405
    action_quotas = {"create": BULK_QUOTA}  # noqa: F405

    def get_quota_cost(self, action: str) -> int:
        if action != "create":
            return 1
        serializer = BulkImportSerializer(data=self.request.data)  # noqa: F405
        serializer.is_valid(raise_exception=True)
        return int(serializer.validated_data["row_count"])

    def create(self, request: Request) -> Response:
        serializer = BulkImportSerializer(data=request.data); serializer.is_valid(raise_exception=True)  # noqa: F405,E702
        values = serializer.validated_data
        job = _call(lambda: InventoryBulkService.enqueue_import(_tenant(request), _actor(request), values["resource_type"], values["document_ref"], _idempotency_key(request)))
        return Response(InventoryJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)  # noqa: F405


__all__ = [name for name in globals() if name.endswith("ViewSet")]
