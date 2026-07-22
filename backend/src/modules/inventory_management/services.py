"""Transactional inventory application services.

The API is intentionally command-oriented: controllers validate transport
shape, then delegate every mutation here.  Every public operation binds the
typed tenant context, validates relationship ownership again at the trust
boundary, and uses database transactions for state plus outbox effects.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from collections.abc import Iterable, Mapping
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q, Sum
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent
from src.core.async_jobs.services import enqueue
from src.core.middleware.correlation import get_correlation_id
from src.core.tenancy.rls import tenant_context
from src.core.state_machine.machine import StateMachineError

from .models import (
    Batch,
    CycleCount,
    CycleCountLine,
    InventoryConfiguration,
    InventoryConfigurationRevision,
    Item,
    SerialNumber,
    StockBalance,
    StockCostLayer,
    StockEntry,
    StockEntryLine,
    StockLedgerEntry,
    StockReservation,
    StorageLocation,
    Warehouse,
)

logger = logging.getLogger(__name__)
QTY_ZERO = Decimal("0.000000")
MONEY_ZERO = Decimal("0.0000")
MONEY_QUANTUM = Decimal("0.0001")
CONFIG_SCHEMA_VERSION = 1
CONFIG_FIELDS = (
    "default_valuation_method",
    "allow_negative_stock",
    "require_stock_entry_approval",
    "enforce_creator_approver_separation",
    "max_lines_per_entry",
    "reservation_ttl_minutes",
    "expiry_warning_days",
    "auto_expire_batches",
    "enabled_capabilities",
    "rollout_rules",
)


class InventoryError(ValidationError):
    """Base domain validation failure safe for API presentation."""


class InventoryConflict(InventoryError):
    """A stale version, duplicate command, or illegal transition."""


class InsufficientStock(InventoryError):
    """The requested movement would violate the active stock policy."""


class CapabilityUnavailable(InventoryError):
    """An explicitly requested extension capability is not registered."""


def _uuid(value: UUID | str, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise InventoryError({field: "Must be a valid UUID."}) from exc


def _required_text(value: object, field: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise InventoryError({field: "This field is required."})
    if len(normalized) > maximum:
        raise InventoryError({field: f"Must contain at most {maximum} characters."})
    return normalized


def _tenant_object(model: type[Any], tenant_id: UUID, object_id: UUID | str, field: str = "id") -> Any:
    try:
        return model.objects.for_tenant(tenant_id).get(pk=_uuid(object_id, field))
    except model.DoesNotExist as exc:
        raise InventoryError({field: "Resource does not exist."}) from exc


def _assert_version(instance: Any, expected_version: int) -> None:
    if not isinstance(expected_version, int) or expected_version < 1:
        raise InventoryError({"expected_version": "Must be a positive integer."})
    if instance.version != expected_version:
        raise InventoryConflict({"expected_version": "Resource was changed by another operation."})


def _validate(instance: Any) -> None:
    instance.full_clean()


def _correlation() -> str:
    return get_correlation_id() or str(uuid.uuid4())


def _emit(tenant_id: UUID, aggregate_type: str, aggregate_id: UUID, event_type: str, facts: Mapping[str, Any]) -> None:
    correlation_id = _correlation()
    payload = {
        "schema_version": 1,
        "tenant_id": str(tenant_id),
        "aggregate_id": str(aggregate_id),
        "occurred_at": timezone.now().isoformat(),
        "correlation_id": correlation_id,
        **dict(facts),
    }
    OutboxEvent.objects.create(
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
    )


def _log(event: str, tenant_id: UUID, actor_id: UUID | str | None, resource_id: UUID, result: str) -> None:
    logger.info(
        "inventory mutation",
        extra={
            "event": event,
            "tenant_id": str(tenant_id),
            "actor_id": str(actor_id) if actor_id else None,
            "resource_id": str(resource_id),
            "result": result,
            "correlation_id": _correlation(),
        },
    )


def _transition(instance: Any, command: str, actor_id: UUID | str, transition_key: str, graph: Mapping[str, Mapping[str, str]]) -> Any:
    del graph  # Graph ownership lives in state_machines.py; retained for call-site readability.
    key = _required_text(transition_key, "transition_key", 255)
    try:
        from .state_machines import transition

        persisted = transition(
            instance,
            command,
            actor_id,
            key,
            metadata={"correlation_id": _correlation()},
        )
    except StateMachineError as exc:
        raise InventoryConflict({"status": str(exc)}) from exc
    return persisted


BATCH_GRAPH = {
    "planned": {"activate": "active"},
    "active": {"quarantine": "quarantined", "recall": "recalled", "exhaust": "exhausted", "expire": "expired"},
    "quarantined": {"release": "active", "recall": "recalled", "expire": "expired"},
}
ENTRY_GRAPH = {
    "draft": {"submit": "submitted", "cancel": "cancelled"},
    "rejected": {"submit": "submitted", "cancel": "cancelled"},
    "submitted": {"approve": "approved", "reject": "rejected", "post": "posted", "cancel": "cancelled"},
    "approved": {"reject": "rejected", "post": "posted", "cancel": "cancelled"},
    "posted": {"reverse": "reversed"},
}
RESERVATION_GRAPH = {"active": {name: name + ("d" if name.endswith("e") else "ed") for name in ("release", "consume", "expire", "cancel")}}
RESERVATION_GRAPH["active"] = {"release": "released", "consume": "consumed", "expire": "expired", "cancel": "cancelled"}
CYCLE_GRAPH = {
    "scheduled": {"start": "in_progress", "cancel": "cancelled"},
    "in_progress": {"submit": "submitted", "cancel": "cancelled"},
    "submitted": {"approve": "approved", "reject": "in_progress", "cancel": "cancelled"},
    "approved": {"post": "posted", "reject": "in_progress", "cancel": "cancelled"},
}


def _apply_command(instance: Any, command: Mapping[str, Any], allowed: Iterable[str], *, exclude: Iterable[str] = ()) -> None:
    allowed_set = set(allowed)
    excluded = set(exclude) | {"tenant_id", "id", "status", "transition_history", "version", "created_at", "updated_at"}
    unknown = set(command) - allowed_set
    if unknown:
        raise InventoryError({key: "Unknown or read-only field." for key in sorted(unknown)})
    for field, value in command.items():
        if field not in excluded:
            setattr(instance, field, value)


class WarehouseService:
    fields = {
        "warehouse_code", "warehouse_name", "warehouse_type", "address_line1", "address_line2", "city",
        "state_region", "postal_code", "country_code", "timezone", "contact_name", "contact_email", "contact_phone",
        "is_default", "is_active",
    }

    @classmethod
    def create(cls, tenant_id: UUID | str, actor_id: UUID | str, command: Mapping[str, Any], idempotency_key: str) -> Warehouse:
        tenant = _uuid(tenant_id, "tenant_id")
        _required_text(idempotency_key, "idempotency_key", 255)
        with tenant_context(tenant), transaction.atomic():
            warehouse = Warehouse(tenant_id=tenant)
            _apply_command(warehouse, command, cls.fields)
            _validate(warehouse)
            warehouse.save()
            StorageLocationService.ensure_default_location(tenant, warehouse.id)
            if warehouse.is_default:
                cls.set_default(tenant, warehouse.id, actor_id, idempotency_key + ":default")
            _emit(tenant, "warehouse", warehouse.id, "inventory.warehouse.created/v1", {"warehouse_code": warehouse.warehouse_code})
            _log("inventory.warehouse.created", tenant, actor_id, warehouse.id, "created")
            return warehouse

    @classmethod
    def create_warehouse(cls, tenant_id: UUID | str, warehouse_code: str, warehouse_name: str, **kwargs: Any) -> Warehouse:
        """Compatibility wrapper for legacy callers; still uses the governed service."""
        actor_id = kwargs.pop("actor_id", uuid.UUID(int=0))
        key = kwargs.pop("idempotency_key", f"legacy:{warehouse_code}")
        command = {
            "warehouse_code": warehouse_code,
            "warehouse_name": warehouse_name,
            "warehouse_type": "distribution_center",
            "country_code": "ZZ",
            "timezone": "UTC",
            **kwargs,
        }
        return cls.create(tenant_id, actor_id, command, key)

    @classmethod
    def update(cls, tenant_id: UUID | str, warehouse_id: UUID | str, expected_version: int, actor_id: UUID | str, command: Mapping[str, Any]) -> Warehouse:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            warehouse = Warehouse.objects.for_tenant(tenant).select_for_update().get(pk=warehouse_id)
            _assert_version(warehouse, expected_version)
            _apply_command(warehouse, command, cls.fields)
            warehouse.version += 1
            _validate(warehouse)
            warehouse.save()
            _log("inventory.warehouse.updated", tenant, actor_id, warehouse.id, "updated")
            return warehouse

    @classmethod
    def archive(cls, tenant_id: UUID | str, warehouse_id: UUID | str, expected_version: int, actor_id: UUID | str) -> Warehouse:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            warehouse = Warehouse.objects.for_tenant(tenant).select_for_update().get(pk=warehouse_id)
            _assert_version(warehouse, expected_version)
            if StockBalance.objects.for_tenant(tenant).filter(warehouse=warehouse).exclude(quantity_on_hand=0).exists():
                raise InventoryConflict("Warehouse contains active stock.")
            if StockReservation.objects.for_tenant(tenant).filter(warehouse=warehouse, status="active").exists():
                raise InventoryConflict("Warehouse has active reservations.")
            if StockEntry.objects.for_tenant(tenant).filter(Q(source_warehouse=warehouse) | Q(destination_warehouse=warehouse), status__in=("draft", "submitted", "approved")).exists():
                raise InventoryConflict("Warehouse has open stock entries.")
            warehouse.archived_at = timezone.now()
            warehouse.is_active = False
            warehouse.is_default = False
            warehouse.version += 1
            warehouse.save()
            _log("inventory.warehouse.archived", tenant, actor_id, warehouse.id, "archived")
            return warehouse

    @classmethod
    def set_default(cls, tenant_id: UUID | str, warehouse_id: UUID | str, actor_id: UUID | str, transition_key: str) -> Warehouse:
        tenant = _uuid(tenant_id, "tenant_id")
        _required_text(transition_key, "transition_key", 255)
        with tenant_context(tenant), transaction.atomic():
            warehouse = Warehouse.objects.for_tenant(tenant).select_for_update().get(pk=warehouse_id)
            if not warehouse.is_active or warehouse.archived_at:
                raise InventoryConflict("An archived or inactive warehouse cannot be default.")
            Warehouse.objects.for_tenant(tenant).exclude(pk=warehouse.pk).filter(is_default=True).update(is_default=False, version=F("version") + 1)
            if not warehouse.is_default:
                warehouse.is_default = True
                warehouse.version += 1
                warehouse.save()
            return warehouse


class StorageLocationService:
    fields = {
        "warehouse", "warehouse_id", "parent", "parent_id", "location_code", "location_name", "zone_type", "location_type",
        "barcode", "pick_sequence", "capacity_units", "capacity_weight_kg", "capacity_volume_cbm", "temperature_controlled",
        "hazmat_approved", "is_default", "is_active",
    }

    @classmethod
    def validate_hierarchy(cls, tenant_id: UUID | str, warehouse_id: UUID | str, parent_id: UUID | str | None, current_id: UUID | None = None) -> None:
        tenant = _uuid(tenant_id, "tenant_id")
        warehouse = _tenant_object(Warehouse, tenant, warehouse_id, "warehouse_id")
        if parent_id is None:
            return
        parent = _tenant_object(StorageLocation, tenant, parent_id, "parent_id")
        if parent.warehouse_id != warehouse.id:
            raise InventoryError({"parent_id": "Parent must belong to the selected warehouse."})
        seen = {current_id} if current_id else set()
        node = parent
        while node:
            if node.id in seen:
                raise InventoryError({"parent_id": "Location hierarchy cannot contain a cycle."})
            seen.add(node.id)
            node = node.parent

    @classmethod
    def create(cls, tenant_id: UUID | str, actor_id: UUID | str, command: Mapping[str, Any], idempotency_key: str) -> StorageLocation:
        tenant = _uuid(tenant_id, "tenant_id")
        _required_text(idempotency_key, "idempotency_key", 255)
        with tenant_context(tenant), transaction.atomic():
            warehouse_id = command.get("warehouse_id") or getattr(command.get("warehouse"), "id", None)
            cls.validate_hierarchy(tenant, warehouse_id, command.get("parent_id"))
            location = StorageLocation(tenant_id=tenant)
            _apply_command(location, command, cls.fields)
            _validate(location)
            location.save()
            if location.is_default:
                StorageLocation.objects.for_tenant(tenant).filter(warehouse_id=location.warehouse_id, is_default=True).exclude(pk=location.pk).update(is_default=False, version=F("version") + 1)
            return location

    @classmethod
    def update(cls, tenant_id: UUID | str, location_id: UUID | str, expected_version: int, actor_id: UUID | str, command: Mapping[str, Any]) -> StorageLocation:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            location = StorageLocation.objects.for_tenant(tenant).select_for_update().get(pk=location_id)
            _assert_version(location, expected_version)
            warehouse_id = command.get("warehouse_id", location.warehouse_id)
            parent_id = command.get("parent_id", location.parent_id)
            cls.validate_hierarchy(tenant, warehouse_id, parent_id, location.id)
            _apply_command(location, command, cls.fields)
            location.version += 1
            _validate(location)
            location.save()
            return location

    @classmethod
    def archive(cls, tenant_id: UUID | str, location_id: UUID | str, expected_version: int, actor_id: UUID | str) -> StorageLocation:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            location = StorageLocation.objects.for_tenant(tenant).select_for_update().get(pk=location_id)
            _assert_version(location, expected_version)
            if StockBalance.objects.for_tenant(tenant).filter(location=location).exclude(quantity_on_hand=0).exists():
                raise InventoryConflict("Location contains active stock.")
            location.archived_at, location.is_active, location.is_default = timezone.now(), False, False
            location.version += 1
            location.save()
            return location

    @classmethod
    def ensure_default_location(cls, tenant_id: UUID | str, warehouse_id: UUID | str) -> StorageLocation:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            warehouse = _tenant_object(Warehouse, tenant, warehouse_id, "warehouse_id")
            existing = StorageLocation.objects.for_tenant(tenant).filter(warehouse=warehouse, is_default=True, archived_at__isnull=True).first()
            if existing:
                return existing
            location = StorageLocation.objects.create(
                tenant_id=tenant, warehouse=warehouse, location_code="DEFAULT", location_name="Default location",
                zone_type="storage", location_type="bin", is_default=True, is_active=True,
            )
            return location


class ItemService:
    fields = {
        "item_code", "item_name", "description", "category", "brand", "barcode", "base_uom", "tracking_mode",
        "tracks_expiry", "valuation_method", "standard_cost", "reorder_point", "reorder_quantity", "safety_stock",
        "default_warehouse", "default_warehouse_id", "abc_classification", "is_active",
    }

    @classmethod
    def create(cls, tenant_id: UUID | str, actor_id: UUID | str, command: Mapping[str, Any], idempotency_key: str) -> Item:
        tenant = _uuid(tenant_id, "tenant_id")
        _required_text(idempotency_key, "idempotency_key", 255)
        with tenant_context(tenant), transaction.atomic():
            item = Item(tenant_id=tenant)
            _apply_command(item, command, cls.fields)
            if item.default_warehouse_id:
                _tenant_object(Warehouse, tenant, item.default_warehouse_id, "default_warehouse_id")
            _validate(item)
            item.save()
            _emit(tenant, "item", item.id, "inventory.item.created/v1", {"item_code": item.item_code})
            return item

    @classmethod
    def update(cls, tenant_id: UUID | str, item_id: UUID | str, expected_version: int, actor_id: UUID | str, command: Mapping[str, Any]) -> Item:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            item = Item.objects.for_tenant(tenant).select_for_update().get(pk=item_id)
            _assert_version(item, expected_version)
            if StockLedgerEntry.objects.for_tenant(tenant).filter(item=item).exists() and ({"tracking_mode", "valuation_method"} & set(command)):
                if any(command.get(name, getattr(item, name)) != getattr(item, name) for name in ("tracking_mode", "valuation_method")):
                    raise InventoryConflict("Tracking and valuation cannot change after ledger history exists.")
            _apply_command(item, command, cls.fields)
            item.version += 1
            _validate(item)
            item.save()
            _emit(tenant, "item", item.id, "inventory.item.updated/v1", {"item_code": item.item_code})
            return item

    @classmethod
    def archive(cls, tenant_id: UUID | str, item_id: UUID | str, expected_version: int, actor_id: UUID | str) -> Item:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            item = Item.objects.for_tenant(tenant).select_for_update().get(pk=item_id)
            _assert_version(item, expected_version)
            if StockBalance.objects.for_tenant(tenant).filter(item=item).exclude(quantity_on_hand=0).exists():
                raise InventoryConflict("Item has active stock.")
            item.archived_at, item.is_active = timezone.now(), False
            item.version += 1
            item.save()
            return item


class BatchService:
    @classmethod
    def register(cls, tenant_id: UUID | str, actor_id: UUID | str, command: Mapping[str, Any], idempotency_key: str) -> Batch:
        tenant = _uuid(tenant_id, "tenant_id")
        _required_text(idempotency_key, "idempotency_key", 255)
        with tenant_context(tenant), transaction.atomic():
            item = _tenant_object(Item, tenant, command.get("item_id"), "item_id")
            if item.tracking_mode != "batch":
                raise InventoryError({"item_id": "Item is not batch tracked."})
            batch = Batch(tenant_id=tenant, item=item)
            _apply_command(batch, command, {"item_id", "batch_number", "supplier_batch_number", "manufactured_on", "expires_on"}, exclude={"item_id"})
            _validate(batch)
            batch.save()
            return batch

    @classmethod
    def update_metadata(cls, tenant_id: UUID | str, batch_id: UUID | str, expected_version: int, actor_id: UUID | str, command: Mapping[str, Any]) -> Batch:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            batch = Batch.objects.for_tenant(tenant).select_for_update().get(pk=batch_id)
            _assert_version(batch, expected_version)
            _apply_command(batch, command, {"supplier_batch_number", "manufactured_on", "expires_on"})
            batch.version += 1
            _validate(batch)
            batch.save()
            return batch

    @classmethod
    def transition(cls, tenant_id: UUID | str, batch_id: UUID | str, actor_id: UUID | str, command: str, transition_key: str) -> Batch:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            batch = Batch.objects.for_tenant(tenant).select_for_update().get(pk=batch_id)
            result = _transition(batch, command, actor_id, transition_key, BATCH_GRAPH)
            if command == "recall":
                _emit(tenant, "batch", batch.id, "inventory.batch.recalled/v1", {"item_id": str(batch.item_id)})
            return result

    activate = classmethod(lambda cls, tenant_id, batch_id, actor_id, transition_key: cls.transition(tenant_id, batch_id, actor_id, "activate", transition_key))
    quarantine = classmethod(lambda cls, tenant_id, batch_id, actor_id, transition_key: cls.transition(tenant_id, batch_id, actor_id, "quarantine", transition_key))
    release = classmethod(lambda cls, tenant_id, batch_id, actor_id, transition_key: cls.transition(tenant_id, batch_id, actor_id, "release", transition_key))
    recall = classmethod(lambda cls, tenant_id, batch_id, actor_id, transition_key: cls.transition(tenant_id, batch_id, actor_id, "recall", transition_key))
    exhaust = classmethod(lambda cls, tenant_id, batch_id, actor_id, transition_key: cls.transition(tenant_id, batch_id, actor_id, "exhaust", transition_key))
    expire = classmethod(lambda cls, tenant_id, batch_id, actor_id, transition_key: cls.transition(tenant_id, batch_id, actor_id, "expire", transition_key))


class SerialNumberService:
    @classmethod
    def register(cls, tenant_id: UUID | str, actor_id: UUID | str, command: Mapping[str, Any], idempotency_key: str) -> SerialNumber:
        tenant = _uuid(tenant_id, "tenant_id")
        _required_text(idempotency_key, "idempotency_key", 255)
        with tenant_context(tenant), transaction.atomic():
            item = _tenant_object(Item, tenant, command.get("item_id"), "item_id")
            if item.tracking_mode != "serial":
                raise InventoryError({"item_id": "Item is not serial tracked."})
            serial = SerialNumber(tenant_id=tenant, item=item)
            _apply_command(serial, command, {"item_id", "serial_number", "manufacturer", "model_number", "warranty_starts_on", "warranty_ends_on"}, exclude={"item_id"})
            _validate(serial)
            serial.save()
            return serial

    @classmethod
    def update_metadata(cls, tenant_id: UUID | str, serial_id: UUID | str, expected_version: int, actor_id: UUID | str, command: Mapping[str, Any]) -> SerialNumber:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            serial = SerialNumber.objects.for_tenant(tenant).select_for_update().get(pk=serial_id)
            _assert_version(serial, expected_version)
            _apply_command(serial, command, {"manufacturer", "model_number", "warranty_starts_on", "warranty_ends_on"})
            serial.version += 1
            _validate(serial)
            serial.save()
            return serial

    @classmethod
    def scrap(cls, tenant_id: UUID | str, serial_id: UUID | str, actor_id: UUID | str, transition_key: str) -> SerialNumber:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            serial = SerialNumber.objects.for_tenant(tenant).select_for_update().get(pk=serial_id)
            if serial.status == "scrapped" and any(
                event.get("transition_key") == transition_key for event in serial.transition_history
            ):
                return serial
            serial = _transition(serial, "scrap", actor_id, transition_key, {})
            serial.current_warehouse = serial.current_location = None
            serial.save(update_fields=("current_warehouse", "current_location"))
            return serial


class StockEntryService:
    entry_fields = {"entry_number", "entry_type", "posting_at", "source_warehouse_id", "destination_warehouse_id", "reference_module", "reference_type", "reference_id", "reason"}

    @classmethod
    def _replace_lines(cls, tenant: UUID, entry: StockEntry, lines: list[Mapping[str, Any]]) -> None:
        config = InventoryConfigurationService.get_effective(tenant)
        if len(lines) > config.max_lines_per_entry:
            raise InventoryError({"lines": f"At most {config.max_lines_per_entry} lines are permitted."})
        entry.lines.all().delete()
        for index, line_command in enumerate(lines, 1):
            item = _tenant_object(Item, tenant, line_command.get("item_id"), f"lines.{index}.item_id")
            line = StockEntryLine(
                tenant_id=tenant, stock_entry=entry, line_number=line_command.get("line_number", index), item=item,
                source_location_id=line_command.get("source_location_id"), destination_location_id=line_command.get("destination_location_id"),
                batch_id=line_command.get("batch_id"), serial_number_id=line_command.get("serial_number_id"), quantity=line_command.get("quantity"),
                uom=line_command.get("uom", item.base_uom), unit_cost=line_command.get("unit_cost"), notes=line_command.get("notes", ""),
            )
            for relation_name, relation_model in (("source_location", StorageLocation), ("destination_location", StorageLocation), ("batch", Batch), ("serial_number", SerialNumber)):
                relation_id = getattr(line, relation_name + "_id")
                if relation_id:
                    _tenant_object(relation_model, tenant, relation_id, f"lines.{index}.{relation_name}_id")
            _validate(line)
            line.save()

    @classmethod
    def create_draft(cls, tenant_id: UUID | str, actor_id: UUID | str, command: Mapping[str, Any], idempotency_key: str) -> StockEntry:
        tenant = _uuid(tenant_id, "tenant_id")
        key = _required_text(idempotency_key, "idempotency_key", 255)
        with tenant_context(tenant), transaction.atomic():
            existing = StockEntry.objects.for_tenant(tenant).filter(idempotency_key=key).first()
            if existing:
                return existing
            entry = StockEntry(tenant_id=tenant, idempotency_key=key, created_by_id=_uuid(actor_id, "actor_id"))
            _apply_command(entry, {k: v for k, v in command.items() if k != "lines"}, cls.entry_fields)
            for field in ("source_warehouse_id", "destination_warehouse_id"):
                if getattr(entry, field):
                    _tenant_object(Warehouse, tenant, getattr(entry, field), field)
            _validate(entry)
            entry.save()
            cls._replace_lines(tenant, entry, list(command.get("lines", [])))
            return entry

    @classmethod
    def update_draft(cls, tenant_id: UUID | str, entry_id: UUID | str, expected_version: int, actor_id: UUID | str, command: Mapping[str, Any]) -> StockEntry:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            entry = StockEntry.objects.for_tenant(tenant).select_for_update().get(pk=entry_id)
            _assert_version(entry, expected_version)
            if entry.status != "draft":
                raise InventoryConflict("Only draft entries can be edited.")
            _apply_command(entry, {k: v for k, v in command.items() if k != "lines"}, cls.entry_fields)
            entry.version += 1
            _validate(entry)
            entry.save()
            if "lines" in command:
                cls._replace_lines(tenant, entry, list(command["lines"]))
            return entry

    @classmethod
    def delete_draft(cls, tenant_id: UUID | str, entry_id: UUID | str, expected_version: int, actor_id: UUID | str) -> StockEntry:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            entry = StockEntry.objects.for_tenant(tenant).select_for_update().get(pk=entry_id)
            _assert_version(entry, expected_version)
            if entry.status != "draft":
                raise InventoryConflict("Only draft entries can be deleted.")
            entry.archived_at, entry.status = timezone.now(), "cancelled"
            entry.version += 1
            entry.save()
            return entry

    @classmethod
    def submit(cls, tenant_id: UUID | str, entry_id: UUID | str, actor_id: UUID | str, transition_key: str) -> StockEntry:
        return cls._command(tenant_id, entry_id, actor_id, "submit", transition_key)

    @classmethod
    def approve(cls, tenant_id: UUID | str, entry_id: UUID | str, actor_id: UUID | str, transition_key: str) -> StockEntry:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant):
            entry = _tenant_object(StockEntry, tenant, entry_id)
            config = InventoryConfigurationService.get_effective(tenant)
            if config.enforce_creator_approver_separation and str(entry.created_by_id) == str(actor_id):
                raise InventoryConflict("Creator and approver must be different users.")
        return cls._command(tenant, entry_id, actor_id, "approve", transition_key)

    @classmethod
    def reject(cls, tenant_id: UUID | str, entry_id: UUID | str, actor_id: UUID | str, transition_key: str) -> StockEntry:
        return cls._command(tenant_id, entry_id, actor_id, "reject", transition_key)

    @classmethod
    def cancel(cls, tenant_id: UUID | str, entry_id: UUID | str, actor_id: UUID | str, transition_key: str) -> StockEntry:
        return cls._command(tenant_id, entry_id, actor_id, "cancel", transition_key)

    @classmethod
    def _command(cls, tenant_id: UUID | str, entry_id: UUID | str, actor_id: UUID | str, command: str, transition_key: str) -> StockEntry:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            entry = StockEntry.objects.for_tenant(tenant).select_for_update().get(pk=entry_id)
            result = _transition(entry, command, actor_id, transition_key, ENTRY_GRAPH)
            if command == "approve":
                result.approved_by_id, result.approved_at = _uuid(actor_id, "actor_id"), timezone.now()
                result.save()
            _emit(tenant, "stock_entry", entry.id, f"inventory.stock_entry.{command}ed/v1", {"status": result.status})
            return result

    @classmethod
    def reverse(cls, tenant_id: UUID | str, entry_id: UUID | str, actor_id: UUID | str, reason: str, idempotency_key: str) -> StockEntry:
        tenant = _uuid(tenant_id, "tenant_id")
        key = _required_text(idempotency_key, "idempotency_key", 255)
        with tenant_context(tenant), transaction.atomic():
            original = StockEntry.objects.for_tenant(tenant).select_for_update().get(pk=entry_id)
            if original.status == "reversed" and hasattr(original, "reversal_entry"):
                return original.reversal_entry
            if original.status != "posted":
                raise InventoryConflict("Only a posted entry can be reversed.")
            reverse_type = {"receipt": "issue", "return": "issue", "issue": "receipt", "scrap": "receipt", "transfer": "transfer", "adjustment": "adjustment", "manufacturing": "adjustment"}[original.entry_type]
            command = {
                "entry_number": f"REV-{original.entry_number}"[:50], "entry_type": reverse_type, "posting_at": timezone.now(),
                "source_warehouse_id": original.destination_warehouse_id, "destination_warehouse_id": original.source_warehouse_id,
                "reason": _required_text(reason, "reason", 5000),
                "lines": [
                    {"line_number": line.line_number, "item_id": line.item_id, "source_location_id": line.destination_location_id,
                     "destination_location_id": line.source_location_id, "batch_id": line.batch_id, "serial_number_id": line.serial_number_id,
                     "quantity": line.quantity, "uom": line.uom, "unit_cost": line.unit_cost, "notes": "Reversal"}
                    for line in original.lines.order_by("line_number", "id")
                ],
            }
            reversal = cls.create_draft(tenant, actor_id, command, key)
            reversal.reversal_of = original
            reversal.status = "approved"
            reversal.save()
            InventoryPostingService.post(tenant, reversal.id, actor_id, key + ":post")
            _transition(original, "reverse", actor_id, key + ":original", ENTRY_GRAPH)
            original.reversed_at = timezone.now()
            original.save()
            _emit(tenant, "stock_entry", original.id, "inventory.stock.reversed/v1", {"reversal_id": str(reversal.id)})
            return reversal


class InventoryPostingService:
    @classmethod
    def _consume_reservations(
        cls,
        tenant: UUID,
        line: StockEntryLine,
        warehouse: Warehouse,
        location: StorageLocation,
        quantity: Decimal,
        actor_id: UUID | str,
        transition_key: str,
    ) -> None:
        """Consume matching allocations before an outbound balance movement."""
        remaining = quantity
        reservations = StockReservation.objects.for_tenant(tenant).select_for_update().filter(
            status="active",
            item=line.item,
            warehouse=warehouse,
            location=location,
            batch=line.batch,
            serial_number=line.serial_number,
        ).order_by("expires_at", "created_at", "id")
        for reservation in reservations:
            if remaining <= 0:
                break
            consumed = min(reservation.quantity, remaining)
            balance = cls._balance(tenant, line, warehouse, location)
            balance.quantity_allocated -= consumed
            balance.quantity_available = balance.quantity_on_hand - balance.quantity_allocated
            balance.save()
            if consumed == reservation.quantity:
                _transition(
                    reservation,
                    "consume",
                    actor_id,
                    f"{transition_key}:reservation:{reservation.id}",
                    RESERVATION_GRAPH,
                )
            else:
                reservation.quantity -= consumed
                reservation.version += 1
                reservation.save(update_fields=("quantity", "version", "updated_at"))
            remaining -= consumed

    @classmethod
    def _balance(cls, tenant: UUID, line: StockEntryLine, warehouse: Warehouse, location: StorageLocation) -> StockBalance:
        balance = StockBalance.objects.for_tenant(tenant).select_for_update().filter(
            item=line.item, warehouse=warehouse, location=location, batch=line.batch, serial_number=line.serial_number,
        ).first()
        if balance:
            return balance
        return StockBalance.objects.create(
            tenant_id=tenant, item=line.item, warehouse=warehouse, location=location, batch=line.batch,
            serial_number=line.serial_number, quantity_on_hand=QTY_ZERO, quantity_allocated=QTY_ZERO,
            quantity_available=QTY_ZERO, stock_value=MONEY_ZERO, valuation_rate=MONEY_ZERO,
        )

    @classmethod
    def _consume_layers(cls, tenant: UUID, line: StockEntryLine, warehouse: Warehouse, location: StorageLocation, quantity: Decimal) -> tuple[Decimal, Decimal]:
        order = "-acquired_at" if line.item.valuation_method == "lifo" else "acquired_at"
        layers = StockCostLayer.objects.for_tenant(tenant).select_for_update().filter(
            item=line.item, warehouse=warehouse, location=location, batch=line.batch, remaining_quantity__gt=0,
        ).order_by(order, "id")
        needed, value = quantity, MONEY_ZERO
        for layer in layers:
            take = min(layer.remaining_quantity, needed)
            value += take * layer.unit_cost
            layer.remaining_quantity -= take
            if layer.remaining_quantity == 0:
                layer.closed_at = timezone.now()
            layer.save()
            needed -= take
            if needed == 0:
                break
        if needed > 0:
            raise InsufficientStock("Cost layers do not cover the requested quantity.")
        return (value / quantity).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)

    @classmethod
    def _movement(cls, tenant: UUID, entry: StockEntry, line: StockEntryLine, warehouse: Warehouse, location: StorageLocation, delta: Decimal, sequence: int, config: InventoryConfiguration) -> tuple[StockLedgerEntry, int]:
        balance = cls._balance(tenant, line, warehouse, location)
        before_qty, before_value = balance.quantity_on_hand, balance.stock_value
        after_qty = before_qty + delta
        if after_qty < 0 and not config.allow_negative_stock:
            raise InsufficientStock({"quantity": f"Insufficient stock for item {line.item.item_code}."})
        if line.serial_number_id and after_qty not in (QTY_ZERO, Decimal("1.000000")):
            raise InventoryError({"quantity": "Serial balance must be zero or one."})
        if delta > 0:
            unit_cost = line.unit_cost if line.unit_cost is not None else (line.item.standard_cost or balance.valuation_rate or MONEY_ZERO)
            value_delta = (delta * unit_cost).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        elif line.item.valuation_method in ("fifo", "lifo") and before_qty > 0:
            unit_cost, consumed = cls._consume_layers(tenant, line, warehouse, location, -delta)
            value_delta = -consumed
        else:
            unit_cost = line.item.standard_cost if line.item.valuation_method == "standard_cost" else balance.valuation_rate
            value_delta = (delta * unit_cost).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        after_value = (before_value + value_delta).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        rate = (after_value / after_qty).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP) if after_qty else MONEY_ZERO
        ledger = StockLedgerEntry.objects.create(
            tenant_id=tenant, stock_entry=entry, stock_entry_line=line, sequence=sequence, item=line.item,
            warehouse=warehouse, location=location, batch=line.batch, serial_number=line.serial_number,
            quantity_delta=delta, quantity_after=after_qty, unit_cost=unit_cost, value_delta=value_delta,
            value_after=after_value, posted_at=timezone.now(), correlation_id=_correlation(),
        )
        balance.quantity_on_hand = after_qty
        balance.quantity_available = after_qty - balance.quantity_allocated
        balance.stock_value, balance.valuation_rate, balance.last_ledger_entry = after_value, rate, ledger
        balance.save()
        if delta > 0 and line.item.valuation_method in ("fifo", "lifo"):
            StockCostLayer.objects.create(
                tenant_id=tenant, item=line.item, warehouse=warehouse, location=location, batch=line.batch,
                originating_ledger_entry=ledger, received_quantity=delta, remaining_quantity=delta,
                unit_cost=unit_cost, acquired_at=entry.posting_at,
            )
        return ledger, sequence + 1

    @classmethod
    def post(cls, tenant_id: UUID | str, entry_id: UUID | str, actor_id: UUID | str, idempotency_key: str) -> StockEntry:
        tenant = _uuid(tenant_id, "tenant_id")
        key = _required_text(idempotency_key, "idempotency_key", 255)
        with tenant_context(tenant), transaction.atomic():
            entry = StockEntry.objects.for_tenant(tenant).select_for_update().get(pk=entry_id)
            if entry.status == "posted":
                return entry
            config = InventoryConfigurationService.get_effective(tenant)
            allowed = "approved" if config.require_stock_entry_approval else "submitted"
            if entry.status != allowed:
                raise InventoryConflict(f"Entry must be {allowed} before posting.")
            lines = list(entry.lines.select_for_update().select_related("item", "batch", "serial_number").order_by("line_number", "id"))
            if not lines:
                raise InventoryError({"lines": "At least one line is required."})
            if len(lines) > config.max_lines_per_entry:
                raise InventoryError({"lines": "Entry exceeds the configured line limit."})
            dimensions: set[tuple[Any, ...]] = set()
            sequence = (StockLedgerEntry.objects.for_tenant(tenant).select_for_update().aggregate(last=Max("sequence"))["last"] or 0) + 1
            for line in lines:
                if not line.item.is_active or line.item.archived_at:
                    raise InventoryError({"item": f"Item {line.item.item_code} is inactive."})
                if line.batch and line.batch.status in ("recalled", "expired", "exhausted"):
                    raise InventoryError({"batch": f"Batch {line.batch.batch_number} cannot be posted."})
                key_dimensions = (line.item_id, line.source_location_id, line.destination_location_id, line.batch_id, line.serial_number_id)
                if key_dimensions in dimensions:
                    raise InventoryError({"lines": "Duplicate stock dimensions are not permitted."})
                dimensions.add(key_dimensions)
                movements: list[tuple[Warehouse, StorageLocation, Decimal]] = []
                if entry.entry_type in ("issue", "scrap") or (entry.entry_type in ("adjustment", "manufacturing") and line.source_location_id):
                    movements.append((entry.source_warehouse, line.source_location, -line.quantity))
                elif entry.entry_type in ("receipt", "return") or (entry.entry_type in ("adjustment", "manufacturing") and line.destination_location_id):
                    movements.append((entry.destination_warehouse, line.destination_location, line.quantity))
                elif entry.entry_type == "transfer":
                    movements.extend(((entry.source_warehouse, line.source_location, -line.quantity), (entry.destination_warehouse, line.destination_location, line.quantity)))
                else:
                    raise InventoryError({"entry_type": "Entry direction is incomplete."})
                for warehouse, location, delta in movements:
                    if delta < 0 and entry.entry_type in ("issue", "manufacturing"):
                        cls._consume_reservations(
                            tenant,
                            line,
                            warehouse,
                            location,
                            -delta,
                            actor_id,
                            key,
                        )
                    _, sequence = cls._movement(tenant, entry, line, warehouse, location, delta, sequence, config)
                if line.batch and line.batch.status == "planned":
                    _transition(line.batch, "activate", actor_id, key + f":batch:{line.batch_id}", BATCH_GRAPH)
                if line.serial_number:
                    serial = SerialNumber.objects.for_tenant(tenant).select_for_update().get(pk=line.serial_number_id)
                    destination = next(((w, l) for w, l, d in movements if d > 0), None)
                    if entry.entry_type == "transfer":
                        serial = _transition(serial, "ship", actor_id, key + f":serial:{serial.id}:ship", {})
                        serial.current_warehouse, serial.current_location = None, None
                        serial.save(update_fields=("current_warehouse", "current_location"))
                        serial = _transition(serial, "receive", actor_id, key + f":serial:{serial.id}:receive", {})
                    elif destination:
                        serial = _transition(serial, "receive", actor_id, key + f":serial:{serial.id}:receive", {})
                    else:
                        command = "issue" if entry.entry_type == "issue" else "scrap"
                        serial = _transition(serial, command, actor_id, key + f":serial:{serial.id}:{command}", {})
                    if destination:
                        serial.current_warehouse, serial.current_location = destination
                    else:
                        serial.current_warehouse = serial.current_location = None
                    serial.save(update_fields=("current_warehouse", "current_location"))
            entry.posted_by_id, entry.posted_at = _uuid(actor_id, "actor_id"), timezone.now()
            entry.save(update_fields=("posted_by_id", "posted_at", "updated_at"))
            entry = _transition(entry, "post", actor_id, key, ENTRY_GRAPH)
            _emit(tenant, "stock_entry", entry.id, "inventory.stock.posted/v1", {"entry_type": entry.entry_type, "line_count": len(lines)})
            _log("inventory.stock.posted", tenant, actor_id, entry.id, "posted")
            return entry


class ReservationService:
    @classmethod
    def reserve(cls, tenant_id: UUID | str, actor_id: UUID | str, command: Mapping[str, Any], idempotency_key: str) -> StockReservation:
        tenant = _uuid(tenant_id, "tenant_id")
        key = _required_text(idempotency_key, "idempotency_key", 255)
        with tenant_context(tenant), transaction.atomic():
            existing = StockReservation.objects.for_tenant(tenant).filter(idempotency_key=key).first()
            if existing:
                return existing
            item = _tenant_object(Item, tenant, command.get("item_id"), "item_id")
            warehouse = _tenant_object(Warehouse, tenant, command.get("warehouse_id"), "warehouse_id")
            dimensions = {name: command.get(name + "_id") for name in ("location", "batch", "serial_number")}
            query = StockBalance.objects.for_tenant(tenant).select_for_update().filter(item=item, warehouse=warehouse)
            for name, value in dimensions.items():
                if value:
                    query = query.filter(**{name + "_id": value})
            balance = query.order_by("id").first()
            quantity = Decimal(str(command.get("quantity")))
            if not balance or quantity <= 0 or balance.quantity_available < quantity:
                raise InsufficientStock("Reservation exceeds available stock.")
            config = InventoryConfigurationService.get_effective(tenant)
            expires_at = command.get("expires_at") or timezone.now() + timedelta(minutes=config.reservation_ttl_minutes)
            reservation = StockReservation(
                tenant_id=tenant, reservation_number=command.get("reservation_number"), reference_module=command.get("reference_module"),
                reference_type=command.get("reference_type"), reference_id=command.get("reference_id"), item=item, warehouse=warehouse,
                location_id=dimensions["location"], batch_id=dimensions["batch"], serial_number_id=dimensions["serial_number"],
                quantity=quantity, expires_at=expires_at, idempotency_key=key,
            )
            _validate(reservation)
            reservation.save()
            balance.quantity_allocated += quantity
            balance.quantity_available = balance.quantity_on_hand - balance.quantity_allocated
            balance.save()
            if reservation.serial_number_id:
                serial = SerialNumber.objects.for_tenant(tenant).select_for_update().get(pk=reservation.serial_number_id)
                if serial.status != "in_stock":
                    raise InventoryConflict("Serial number is not available.")
                _transition(serial, "reserve", actor_id, key + f":serial:{serial.id}", {})
            _emit(tenant, "reservation", reservation.id, "inventory.reservation.changed/v1", {"status": "active"})
            return reservation

    @classmethod
    def _finish(cls, tenant_id: UUID | str, reservation_id: UUID | str, actor_id: UUID | str, command: str, transition_key: str) -> StockReservation:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            reservation = StockReservation.objects.for_tenant(tenant).select_for_update().get(pk=reservation_id)
            if reservation.status != "active":
                return reservation if any(x.get("transition_key") == transition_key for x in reservation.transition_history) else _transition(reservation, command, actor_id, transition_key, RESERVATION_GRAPH)
            balance = StockBalance.objects.for_tenant(tenant).select_for_update().get(
                item=reservation.item, warehouse=reservation.warehouse, location=reservation.location,
                batch=reservation.batch, serial_number=reservation.serial_number,
            )
            balance.quantity_allocated -= reservation.quantity
            balance.quantity_available = balance.quantity_on_hand - balance.quantity_allocated
            balance.save()
            if reservation.serial_number_id and command != "consume":
                serial = SerialNumber.objects.for_tenant(tenant).select_for_update().get(pk=reservation.serial_number_id)
                _transition(serial, "release", actor_id, transition_key + f":serial:{serial.id}", {})
            result = _transition(reservation, command, actor_id, transition_key, RESERVATION_GRAPH)
            _emit(tenant, "reservation", reservation.id, "inventory.reservation.changed/v1", {"status": result.status})
            return result

    release = classmethod(lambda cls, tenant_id, reservation_id, actor_id, transition_key: cls._finish(tenant_id, reservation_id, actor_id, "release", transition_key))
    consume = classmethod(lambda cls, tenant_id, reservation_id, actor_id, transition_key: cls._finish(tenant_id, reservation_id, actor_id, "consume", transition_key))
    cancel = classmethod(lambda cls, tenant_id, reservation_id, actor_id, transition_key: cls._finish(tenant_id, reservation_id, actor_id, "cancel", transition_key))

    @classmethod
    def update(cls, tenant_id: UUID | str, reservation_id: UUID | str, expected_version: int, actor_id: UUID | str, command: Mapping[str, Any]) -> StockReservation:
        """Update the expiry/reference metadata of an active reservation."""
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            reservation = StockReservation.objects.for_tenant(tenant).select_for_update().get(pk=reservation_id)
            _assert_version(reservation, expected_version)
            if reservation.status != "active":
                raise InventoryConflict("Only active reservations can be updated.")
            _apply_command(reservation, command, {"expires_at", "reference_module", "reference_type", "reference_id"})
            reservation.version += 1
            _validate(reservation)
            reservation.save()
            return reservation

    @classmethod
    def expire_due(cls, tenant_id: UUID | str, actor_id: UUID | str, *, queue_threshold: int = 100) -> int | Any:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant):
            due = StockReservation.objects.for_tenant(tenant).filter(status="active", expires_at__lte=timezone.now()).order_by("expires_at", "id")
            count = due.count()
            if count > queue_threshold:
                return enqueue(tenant, actor_id, "inventory.expire_reservations", {"tenant_id": str(tenant)}, f"expire:{timezone.now().date().isoformat()}")
            for reservation in due:
                cls._finish(tenant, reservation.id, actor_id, "expire", f"expire:{reservation.id}")
            return count


class CycleCountService:
    @classmethod
    def create(cls, tenant_id: UUID | str, actor_id: UUID | str, command: Mapping[str, Any], idempotency_key: str) -> CycleCount:
        tenant = _uuid(tenant_id, "tenant_id")
        _required_text(idempotency_key, "idempotency_key", 255)
        with tenant_context(tenant), transaction.atomic():
            warehouse = _tenant_object(Warehouse, tenant, command.get("warehouse_id"), "warehouse_id")
            count = CycleCount(tenant_id=tenant, warehouse=warehouse)
            _apply_command(count, {k: v for k, v in command.items() if k != "lines"}, {"count_number", "location_id", "count_type", "scheduled_for", "assigned_to_id"})
            _validate(count)
            count.save()
            for index, line_data in enumerate(command.get("lines", []), 1):
                item = _tenant_object(Item, tenant, line_data.get("item_id"), f"lines.{index}.item_id")
                location = _tenant_object(StorageLocation, tenant, line_data.get("location_id"), f"lines.{index}.location_id")
                line = CycleCountLine(tenant_id=tenant, cycle_count=count, line_number=line_data.get("line_number", index), item=item, location=location, batch_id=line_data.get("batch_id"), serial_number_id=line_data.get("serial_number_id"), system_quantity=QTY_ZERO)
                _validate(line)
                line.save()
            return count

    @classmethod
    def update_scheduled(cls, tenant_id: UUID | str, count_id: UUID | str, expected_version: int, actor_id: UUID | str, command: Mapping[str, Any]) -> CycleCount:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            count = CycleCount.objects.for_tenant(tenant).select_for_update().get(pk=count_id)
            _assert_version(count, expected_version)
            if count.status != "scheduled":
                raise InventoryConflict("Only scheduled counts can be edited.")
            _apply_command(count, command, {"scheduled_for", "assigned_to_id", "location_id"})
            count.version += 1
            _validate(count)
            count.save()
            return count

    @classmethod
    def start(cls, tenant_id: UUID | str, count_id: UUID | str, actor_id: UUID | str, transition_key: str) -> CycleCount:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            count = CycleCount.objects.for_tenant(tenant).select_for_update().get(pk=count_id)
            for line in count.lines.select_for_update().all():
                total = StockBalance.objects.for_tenant(tenant).filter(item=line.item, warehouse=count.warehouse, location=line.location, batch=line.batch, serial_number=line.serial_number).aggregate(value=Sum("quantity_on_hand"))["value"] or QTY_ZERO
                line.system_quantity = total
                line.save()
            _transition(count, "start", actor_id, transition_key, CYCLE_GRAPH)
            count.started_at = timezone.now()
            count.save()
            return count

    @classmethod
    def record_counts(cls, tenant_id: UUID | str, count_id: UUID | str, actor_id: UUID | str, lines: Iterable[Mapping[str, Any]]) -> CycleCount:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            count = CycleCount.objects.for_tenant(tenant).select_for_update().get(pk=count_id)
            if count.status != "in_progress":
                raise InventoryConflict("Counts can only be recorded while in progress.")
            for command in lines:
                line = count.lines.select_for_update().get(pk=command.get("id"))
                counted = Decimal(str(command.get("counted_quantity")))
                if counted < 0:
                    raise InventoryError({"counted_quantity": "Must be nonnegative."})
                line.counted_quantity, line.variance_quantity = counted, counted - line.system_quantity
                line.counted_by_id, line.counted_at = _uuid(actor_id, "actor_id"), timezone.now()
                line.save()
            return count

    @classmethod
    def _command(cls, tenant_id: UUID | str, count_id: UUID | str, actor_id: UUID | str, command: str, transition_key: str) -> CycleCount:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            count = CycleCount.objects.for_tenant(tenant).select_for_update().get(pk=count_id)
            result = _transition(count, command, actor_id, transition_key, CYCLE_GRAPH)
            setattr(result, {"submit": "submitted_at", "approve": "approved_at"}.get(command, "updated_at"), timezone.now())
            result.save()
            return result

    submit = classmethod(lambda cls, tenant_id, count_id, actor_id, transition_key: cls._command(tenant_id, count_id, actor_id, "submit", transition_key))
    approve = classmethod(lambda cls, tenant_id, count_id, actor_id, transition_key: cls._command(tenant_id, count_id, actor_id, "approve", transition_key))
    reject = classmethod(lambda cls, tenant_id, count_id, actor_id, transition_key: cls._command(tenant_id, count_id, actor_id, "reject", transition_key))
    cancel = classmethod(lambda cls, tenant_id, count_id, actor_id, transition_key: cls._command(tenant_id, count_id, actor_id, "cancel", transition_key))

    @classmethod
    def post_adjustment(cls, tenant_id: UUID | str, count_id: UUID | str, actor_id: UUID | str, transition_key: str) -> CycleCount:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            count = CycleCount.objects.for_tenant(tenant).select_for_update().get(pk=count_id)
            if count.status == "posted":
                return count
            if count.status != "approved":
                raise InventoryConflict("Cycle count must be approved before posting.")
            lines = []
            for line in count.lines.exclude(variance_quantity=0).order_by("line_number", "id"):
                lines.append({
                    "item_id": line.item_id, "source_location_id": line.location_id if line.variance_quantity < 0 else None,
                    "destination_location_id": line.location_id if line.variance_quantity > 0 else None,
                    "batch_id": line.batch_id, "serial_number_id": line.serial_number_id, "quantity": abs(line.variance_quantity), "uom": line.item.base_uom,
                })
            if lines:
                entry = StockEntryService.create_draft(tenant, actor_id, {
                    "entry_number": f"CC-{count.count_number}"[:50], "entry_type": "adjustment", "posting_at": timezone.now(),
                    "source_warehouse_id": count.warehouse_id, "destination_warehouse_id": count.warehouse_id,
                    "reference_module": "inventory_management", "reference_type": "cycle_count", "reference_id": count.id,
                    "reason": "Approved cycle count variance", "lines": lines,
                }, transition_key)
                entry.status = "approved"
                entry.save()
                InventoryPostingService.post(tenant, entry.id, actor_id, transition_key + ":post")
            _transition(count, "post", actor_id, transition_key + ":count", CYCLE_GRAPH)
            count.posted_at = timezone.now()
            count.save()
            _emit(tenant, "cycle_count", count.id, "inventory.cycle_count.posted/v1", {"adjusted_lines": len(lines)})
            return count


class InventoryQueryService:
    @staticmethod
    def get_balance(tenant_id: UUID | str, balance_id: UUID | str) -> StockBalance:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant):
            return _tenant_object(StockBalance, tenant, balance_id)

    @staticmethod
    def list_balances(tenant_id: UUID | str, **filters: Any):
        from .selectors import balances_for_tenant
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant):
            return balances_for_tenant(tenant).filter(**filters)

    @staticmethod
    def list_ledger(tenant_id: UUID | str, **filters: Any):
        from .selectors import ledger_for_tenant
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant):
            return ledger_for_tenant(tenant).filter(**filters)

    @staticmethod
    def trace_batch(tenant_id: UUID | str, batch_id: UUID | str):
        from .selectors import batch_trace
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant):
            return batch_trace(tenant, _uuid(batch_id, "batch_id"))

    @staticmethod
    def trace_serial(tenant_id: UUID | str, serial_id: UUID | str):
        from .selectors import serial_trace
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant):
            return serial_trace(tenant, _uuid(serial_id, "serial_id"))

    @classmethod
    def stock_summary(cls, tenant_id: UUID | str) -> dict[str, Any]:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant):
            totals = StockBalance.objects.for_tenant(tenant).aggregate(on_hand=Sum("quantity_on_hand"), allocated=Sum("quantity_allocated"), available=Sum("quantity_available"), stock_value=Sum("stock_value"))
            return {key: value or (MONEY_ZERO if key == "stock_value" else QTY_ZERO) for key, value in totals.items()}

    @classmethod
    def dashboard(cls, tenant_id: UUID | str) -> dict[str, Any]:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant):
            return {
                "stock": cls.stock_summary(tenant),
                "active_reservations": StockReservation.objects.for_tenant(tenant).filter(status="active").count(),
                "open_entries": StockEntry.objects.for_tenant(tenant).filter(status__in=("draft", "submitted", "approved")).count(),
                "overdue_cycle_counts": CycleCount.objects.for_tenant(tenant).filter(status="scheduled", scheduled_for__lt=timezone.localdate()).count(),
            }


class InventoryConfigurationService:
    @staticmethod
    def _defaults() -> dict[str, Any]:
        return {
            "default_valuation_method": "fifo", "allow_negative_stock": False, "require_stock_entry_approval": True,
            "enforce_creator_approver_separation": True, "max_lines_per_entry": 500, "reservation_ttl_minutes": 1440,
            "expiry_warning_days": 30, "auto_expire_batches": True, "enabled_capabilities": {}, "rollout_rules": {},
        }

    @classmethod
    def _validate_snapshot(cls, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        unknown = set(snapshot) - set(CONFIG_FIELDS)
        if unknown:
            raise InventoryError({key: "Unknown configuration setting." for key in sorted(unknown)})
        data = {**cls._defaults(), **dict(snapshot)}
        if data["default_valuation_method"] not in ("fifo", "lifo", "weighted_average", "standard_cost"):
            raise InventoryError({"default_valuation_method": "Unsupported valuation method."})
        for field, low, high in (("max_lines_per_entry", 1, 5000), ("reservation_ttl_minutes", 5, 10080), ("expiry_warning_days", 1, 3650)):
            value = data[field]
            if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
                raise InventoryError({field: f"Must be between {low} and {high}."})
        for field in ("enabled_capabilities", "rollout_rules"):
            if not isinstance(data[field], dict):
                raise InventoryError({field: "Must be a JSON object without executable expressions."})
        return data

    @classmethod
    def get_effective(cls, tenant_id: UUID | str, environment: str = "development") -> InventoryConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant), transaction.atomic():
            config = InventoryConfiguration.objects.for_tenant(tenant).filter(environment=environment).first()
            if config:
                return config
            defaults = cls._defaults()
            config = InventoryConfiguration.objects.create(tenant_id=tenant, environment=environment, status="active", **defaults)
            return config

    @classmethod
    def preview(cls, tenant_id: UUID | str, environment: str, document: Mapping[str, Any]) -> dict[str, Any]:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant):
            current = cls.get_effective(tenant, environment)
            proposed = cls._validate_snapshot(document)
            changes = [{"field": field, "before": getattr(current, field), "after": proposed[field]} for field in CONFIG_FIELDS if getattr(current, field) != proposed[field]]
            effects = sorted({"posting" if c["field"] in ("allow_negative_stock", "require_stock_entry_approval", "max_lines_per_entry", "default_valuation_method") else "reservations" if c["field"] == "reservation_ttl_minutes" else "batch_monitoring" if c["field"] in ("expiry_warning_days", "auto_expire_batches") else "capability_rollout" for c in changes})
            return {"changes": changes, "affected_behaviors": effects, "valid": True}

    @classmethod
    def create_revision(cls, tenant_id: UUID | str, environment: str, actor_id: UUID | str, document: Mapping[str, Any], change_reason: str, correlation_id: str | None = None) -> InventoryConfigurationRevision:
        tenant = _uuid(tenant_id, "tenant_id")
        snapshot = cls._validate_snapshot(document)
        with tenant_context(tenant), transaction.atomic():
            config = InventoryConfiguration.objects.for_tenant(tenant).select_for_update().filter(environment=environment).first()
            if config is None:
                config = InventoryConfiguration.objects.create(tenant_id=tenant, environment=environment, status="draft", **cls._defaults())
            revision_number = (
                config.revisions.aggregate(last=Max("revision"))["last"] or 0
            ) + 1
            revision = InventoryConfigurationRevision.objects.create(
                tenant_id=tenant, configuration=config, revision=revision_number, snapshot=snapshot,
                change_reason=_required_text(change_reason, "change_reason", 5000), changed_by_id=_uuid(actor_id, "actor_id"),
                correlation_id=correlation_id or _correlation(),
            )
            return revision

    @classmethod
    def activate(cls, tenant_id: UUID | str, environment: str, revision: int, actor_id: UUID | str, transition_key: str) -> InventoryConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        _required_text(transition_key, "transition_key", 255)
        with tenant_context(tenant), transaction.atomic():
            config = InventoryConfiguration.objects.for_tenant(tenant).select_for_update().get(environment=environment)
            target = config.revisions.get(revision=revision)
            data = cls._validate_snapshot(target.snapshot)
            for field, value in data.items():
                setattr(config, field, value)
            config.status, config.active_revision, config.version = "active", revision, config.version + 1
            _validate(config)
            config.save()
            return config

    @classmethod
    def rollback(cls, tenant_id: UUID | str, environment: str, revision: int, actor_id: UUID | str, reason: str, idempotency_key: str) -> InventoryConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        _required_text(idempotency_key, "idempotency_key", 255)
        with tenant_context(tenant), transaction.atomic():
            config = InventoryConfiguration.objects.for_tenant(tenant).get(environment=environment)
            target = config.revisions.get(revision=revision)
            new_revision = cls.create_revision(tenant, environment, actor_id, target.snapshot, reason)
            return cls.activate(tenant, environment, new_revision.revision, actor_id, idempotency_key)

    @classmethod
    def export_document(cls, tenant_id: UUID | str, environment: str) -> dict[str, Any]:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant):
            config = cls.get_effective(tenant, environment)
            payload = {field: getattr(config, field) for field in CONFIG_FIELDS}
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
            return {"schema_version": CONFIG_SCHEMA_VERSION, "environment": environment, "configuration": payload, "checksum": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()}

    @classmethod
    def import_document(cls, tenant_id: UUID | str, environment: str, actor_id: UUID | str, document: Mapping[str, Any], reason: str, idempotency_key: str) -> InventoryConfigurationRevision:
        _required_text(idempotency_key, "idempotency_key", 255)
        if document.get("schema_version") != CONFIG_SCHEMA_VERSION or document.get("environment") != environment:
            raise InventoryError("Configuration schema version or environment does not match.")
        payload = document.get("configuration")
        if not isinstance(payload, dict):
            raise InventoryError({"configuration": "Must be an object."})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        expected = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
        if not hmac.compare_digest(str(document.get("checksum", "")), expected):
            raise InventoryError({"checksum": "Checksum validation failed."})
        return cls.create_revision(tenant_id, environment, actor_id, payload, reason)


class InventoryBulkService:
    @classmethod
    def enqueue_import(cls, tenant_id: UUID | str, actor_id: UUID | str, resource_type: str, document_ref: str, idempotency_key: str):
        tenant = _uuid(tenant_id, "tenant_id")
        resource = _required_text(resource_type, "resource_type", 64)
        if resource not in {"warehouses", "locations", "items", "batches", "serial_numbers", "stock_entries", "reservations", "cycle_counts"}:
            raise InventoryError({"resource_type": "Unsupported import resource."})
        reference = _required_text(document_ref, "document_ref", 512)
        with tenant_context(tenant), transaction.atomic():
            return enqueue(tenant, actor_id, "inventory.import", {"resource_type": resource, "document_ref": reference}, idempotency_key)


class StockService:
    """Legacy facade retained without preserving its unsafe mutation contract."""

    @staticmethod
    def process_stock_entry(stock_entry: StockEntry, actor_id: UUID | str | None = None) -> StockEntry:
        actor = actor_id or stock_entry.created_by_id
        return InventoryPostingService.post(stock_entry.tenant_id, stock_entry.id, actor, stock_entry.idempotency_key + ":legacy-post")
