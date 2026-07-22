"""Deterministically normalize the inventory 0001 legacy data."""

from datetime import datetime, time, timezone
from decimal import Decimal

from django.db import migrations

LEGACY_LOCATION_CODE = "__legacy_default__"


def _ids(queryset):
    return ", ".join(str(value) for value in queryset.values_list("id", flat=True)[:20])


def backfill_legacy(apps, schema_editor):
    Warehouse = apps.get_model("inventory_management", "Warehouse")
    Location = apps.get_model("inventory_management", "StorageLocation")
    Item = apps.get_model("inventory_management", "Item")
    Batch = apps.get_model("inventory_management", "Batch")
    Serial = apps.get_model("inventory_management", "SerialNumber")
    Entry = apps.get_model("inventory_management", "StockEntry")
    Line = apps.get_model("inventory_management", "StockEntryLine")
    Balance = apps.get_model("inventory_management", "StockBalance")

    ambiguous_items = Item.objects.filter(has_batch_no=True, has_serial_no=True)
    if ambiguous_items.exists():
        raise RuntimeError(
            "inventory 0003 cannot infer tracking mode for items declaring both batch and serial: "
            + _ids(ambiguous_items)
        )
    transfer_entries = Entry.objects.filter(entry_type="transfer", warehouse_id__isnull=False)
    if transfer_entries.exists():
        raise RuntimeError(
            "inventory 0003 cannot infer the missing transfer endpoint for legacy entries: "
            + _ids(transfer_entries)
        )
    invalid_entries = Entry.objects.exclude(status__in=("draft", "submitted", "approved", "posted", "rejected", "cancelled", "reversed"))
    if invalid_entries.exists():
        raise RuntimeError("inventory 0003 found unsupported legacy stock-entry statuses: " + _ids(invalid_entries))
    invalid_lines = Line.objects.filter(quantity__lte=0)
    if invalid_lines.exists():
        raise RuntimeError("inventory 0003 found non-positive stock-entry quantities: " + _ids(invalid_lines))

    locations = {}
    for warehouse in Warehouse.objects.order_by("tenant_id", "id"):
        if warehouse.address and not warehouse.address_line1:
            warehouse.address_line1 = warehouse.address[:255]
        warehouse.save(update_fields=("address_line1",))
        location = Location.objects.create(
            tenant_id=warehouse.tenant_id,
            warehouse_id=warehouse.id,
            location_code=LEGACY_LOCATION_CODE,
            location_name="Legacy default location",
            zone_type="storage",
            location_type="floor",
            is_default=True,
            is_active=warehouse.is_active,
        )
        locations[warehouse.id] = location

    for item in Item.objects.order_by("tenant_id", "id"):
        item.tracking_mode = "batch" if item.has_batch_no else "serial" if item.has_serial_no else "none"
        item.reorder_quantity = item.reorder_qty
        if item.valuation_method == "weighted_avg":
            item.valuation_method = "weighted_average"
        item.save(update_fields=("tracking_mode", "reorder_quantity", "valuation_method"))

    for entry in Entry.objects.order_by("tenant_id", "id"):
        entry.idempotency_key = f"legacy:{entry.id}"
        if entry.posting_date is not None:
            entry.posting_at = datetime.combine(entry.posting_date, time.min, tzinfo=timezone.utc)
        if entry.warehouse_id is not None:
            if entry.entry_type in ("issue", "scrap"):
                entry.source_warehouse_id = entry.warehouse_id
            elif entry.entry_type in ("receipt", "return", "adjustment", "manufacturing"):
                entry.destination_warehouse_id = entry.warehouse_id
        entry.reference_type = "legacy_document" if entry.reference_document else ""
        entry.save(
            update_fields=(
                "idempotency_key",
                "posting_at",
                "source_warehouse",
                "destination_warehouse",
                "reference_type",
            )
        )

    for entry in Entry.objects.order_by("tenant_id", "id"):
        for number, line in enumerate(entry.lines.order_by("created_at", "id"), start=1):
            if line.tenant_id != entry.tenant_id or line.item.tenant_id != entry.tenant_id:
                raise RuntimeError(f"inventory 0003 found cross-tenant legacy line {line.id}")
            item = line.item
            if line.batch_no and item.tracking_mode != "batch":
                raise RuntimeError(f"inventory 0003 cannot attach batch {line.batch_no!r} to non-batch item on line {line.id}")
            if line.serial_no and item.tracking_mode != "serial":
                raise RuntimeError(f"inventory 0003 cannot attach serial {line.serial_no!r} to non-serial item on line {line.id}")
            line.line_number = number
            line.uom = item.base_uom
            line.unit_cost = line.cost
            line.line_value = (line.cost or Decimal("0")) * line.quantity
            if entry.source_warehouse_id:
                line.source_location_id = locations[entry.source_warehouse_id].id
            if entry.destination_warehouse_id:
                line.destination_location_id = locations[entry.destination_warehouse_id].id
            if line.batch_no:
                batch, _ = Batch.objects.get_or_create(
                    tenant_id=line.tenant_id,
                    item_id=line.item_id,
                    batch_number=line.batch_no,
                    defaults={"status": "planned"},
                )
                line.batch_id = batch.id
            if line.serial_no:
                existing = Serial.objects.filter(tenant_id=line.tenant_id, serial_number=line.serial_no).first()
                if existing is not None and existing.item_id != line.item_id:
                    raise RuntimeError(
                        f"inventory 0003 serial {line.serial_no!r} belongs to multiple items; conflicting line {line.id}"
                    )
                serial = existing or Serial.objects.create(
                    tenant_id=line.tenant_id,
                    item_id=line.item_id,
                    serial_number=line.serial_no,
                    status="registered",
                )
                line.serial_number_id = serial.id
            line.save(
                update_fields=(
                    "line_number",
                    "uom",
                    "unit_cost",
                    "line_value",
                    "source_location",
                    "destination_location",
                    "batch",
                    "serial_number",
                )
            )

    for balance in Balance.objects.order_by("tenant_id", "id"):
        if balance.item.tenant_id != balance.tenant_id or balance.warehouse.tenant_id != balance.tenant_id:
            raise RuntimeError(f"inventory 0003 found cross-tenant legacy balance {balance.id}")
        balance.location_id = locations[balance.warehouse_id].id
        balance.quantity_available = balance.quantity_on_hand - balance.quantity_allocated
        if balance.valuation_rate is None:
            balance.valuation_rate = Decimal("0")
        balance.save(update_fields=("location", "quantity_available", "valuation_rate"))


def reverse_backfill(apps, schema_editor):
    Warehouse = apps.get_model("inventory_management", "Warehouse")
    Location = apps.get_model("inventory_management", "StorageLocation")
    Batch = apps.get_model("inventory_management", "Batch")
    Serial = apps.get_model("inventory_management", "SerialNumber")
    Item = apps.get_model("inventory_management", "Item")
    Entry = apps.get_model("inventory_management", "StockEntry")
    Line = apps.get_model("inventory_management", "StockEntryLine")
    Balance = apps.get_model("inventory_management", "StockBalance")

    if apps.get_model("inventory_management", "StockLedgerEntry").objects.exists():
        raise RuntimeError("inventory 0003 reversal would discard posted ledger evidence")
    if apps.get_model("inventory_management", "StockReservation").objects.exists():
        raise RuntimeError("inventory 0003 reversal would discard reservations")
    if apps.get_model("inventory_management", "CycleCount").objects.exists():
        raise RuntimeError("inventory 0003 reversal would discard cycle counts")
    if apps.get_model("inventory_management", "InventoryConfiguration").objects.exists():
        raise RuntimeError("inventory 0003 reversal would discard configuration history")

    unsupported_locations = Location.objects.exclude(location_code=LEGACY_LOCATION_CODE)
    if unsupported_locations.exists():
        raise RuntimeError(
            "inventory 0003 reversal cannot represent non-legacy storage locations: "
            + _ids(unsupported_locations)
        )
    for batch in Batch.objects.all():
        if not Line.objects.filter(batch_id=batch.id, batch_no=batch.batch_number).exists():
            raise RuntimeError(f"inventory 0003 reversal cannot represent standalone batch {batch.id}")
    for serial in Serial.objects.all():
        if not Line.objects.filter(serial_number_id=serial.id, serial_no=serial.serial_number).exists():
            raise RuntimeError(f"inventory 0003 reversal cannot represent standalone serial {serial.id}")
    for warehouse in Warehouse.objects.all():
        expected_address = (warehouse.address or "")[:255]
        unrepresentable = (
            warehouse.address_line1 != expected_address
            or bool(warehouse.address_line2 or warehouse.city or warehouse.state_region or warehouse.postal_code)
            or bool(warehouse.contact_name or warehouse.contact_email or warehouse.contact_phone)
            or warehouse.country_code != "ZZ"
            or warehouse.timezone != "UTC"
            or warehouse.is_default
            or warehouse.archived_at is not None
            or warehouse.version != 1
        )
        if unrepresentable:
            raise RuntimeError(f"inventory 0003 reversal cannot losslessly represent warehouse {warehouse.id}")
    for item in Item.objects.all():
        if (
            item.base_uom != "unit"
            or item.brand
            or item.standard_cost is not None
            or item.safety_stock is not None
            or item.default_warehouse_id is not None
            or item.abc_classification
            or item.archived_at is not None
            or item.version != 1
        ):
            raise RuntimeError(f"inventory 0003 reversal cannot losslessly represent item {item.id}")
    for entry in Entry.objects.all():
        expected_posting = (
            datetime.combine(entry.posting_date, time.min, tzinfo=timezone.utc)
            if entry.posting_date is not None
            else entry.posting_at
        )
        if (
            entry.idempotency_key != f"legacy:{entry.id}"
            or entry.posting_at != expected_posting
            or entry.reference_module
            or entry.reference_id is not None
            or entry.reason
            or entry.created_by_id is not None
            or entry.approved_by_id is not None
            or entry.posted_by_id is not None
            or entry.approved_at is not None
            or entry.posted_at is not None
            or entry.reversed_at is not None
            or entry.reversal_of_id is not None
            or entry.transition_history
            or entry.version != 1
            or entry.archived_at is not None
        ):
            raise RuntimeError(f"inventory 0003 reversal cannot losslessly represent stock entry {entry.id}")
    for line in Line.objects.all():
        expected_value = (line.cost or Decimal("0")) * line.quantity
        if line.uom != "unit" or line.notes or line.unit_cost != line.cost or line.line_value != expected_value:
            raise RuntimeError(f"inventory 0003 reversal cannot losslessly represent stock-entry line {line.id}")

    for item in Item.objects.all():
        item.has_batch_no = item.tracking_mode == "batch"
        item.has_serial_no = item.tracking_mode == "serial"
        item.reorder_qty = item.reorder_quantity
        item.save(update_fields=("has_batch_no", "has_serial_no", "reorder_qty"))
    for entry in Entry.objects.all():
        entry.warehouse_id = entry.source_warehouse_id or entry.destination_warehouse_id
        entry.save(update_fields=("warehouse",))
    for line in Line.objects.select_related("batch", "serial_number"):
        line.batch_no = line.batch.batch_number if line.batch_id else ""
        line.serial_no = line.serial_number.serial_number if line.serial_number_id else ""
        line.batch_id = None
        line.serial_number_id = None
        line.source_location_id = None
        line.destination_location_id = None
        line.save(update_fields=("batch_no", "serial_no", "batch", "serial_number", "source_location", "destination_location"))
    Balance.objects.update(location_id=None, batch_id=None, serial_number_id=None, last_ledger_entry_id=None)
    Batch.objects.all().delete()
    Serial.objects.all().delete()
    Location.objects.filter(location_code=LEGACY_LOCATION_CODE).delete()


class Migration(migrations.Migration):
    dependencies = [("inventory_management", "0002_domain_foundation")]
    operations = [migrations.RunPython(backfill_legacy, reverse_backfill)]
