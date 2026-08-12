"""End-to-end service invariants for core inventory operations."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent
from src.modules.inventory_management.events import emit_event, publish_domain_event
from src.modules.inventory_management.models import (
    ImmutableRecordError,
    StockBalance,
    StockLedgerEntry,
    StockReservation,
)
from src.modules.inventory_management.services import (
    BatchService,
    CycleCountService,
    InventoryBulkService,
    InventoryConfigurationService,
    InventoryConflict,
    InventoryError,
    InventoryPostingService,
    InventoryQueryService,
    ItemService,
    ReservationService,
    SerialNumberService,
    StockEntryService,
    StorageLocationService,
    WarehouseService,
)

pytestmark = pytest.mark.django_db


def setup_masters(tenant_id, actor_id):
    warehouse = WarehouseService.create(
        tenant_id,
        actor_id,
        {
            "warehouse_code": "MAIN",
            "warehouse_name": "Main warehouse",
            "warehouse_type": "distribution_center",
            "country_code": "IN",
            "timezone": "Asia/Kolkata",
            "is_default": True,
        },
        "warehouse-main",
    )
    location = StorageLocationService.ensure_default_location(tenant_id, warehouse.id)
    item = ItemService.create(
        tenant_id,
        actor_id,
        {
            "item_code": "SKU-001",
            "item_name": "Test component",
            "base_uom": "EA",
            "tracking_mode": "none",
            "valuation_method": "weighted_average",
        },
        "item-sku-001",
    )
    return warehouse, location, item


def approve_and_post(tenant_id, actor_id, approver_id, entry):
    StockEntryService.submit(tenant_id, entry.id, actor_id, f"{entry.entry_number}:submit")
    StockEntryService.approve(tenant_id, entry.id, approver_id, f"{entry.entry_number}:approve")
    return InventoryPostingService.post(tenant_id, entry.id, approver_id, f"{entry.entry_number}:post")


def test_inventory_domain_event_contract_normalizes_payload_and_rejects_unsafe_inputs() -> None:
    tenant_id, aggregate_id, actor_id = uuid4(), uuid4(), uuid4()
    occurred_at = timezone.now()

    event = publish_domain_event(
        tenant_id,
        "inventory.reservation.changed/v1",
        "InventoryReservation",
        aggregate_id,
        correlation_id="inventory:event:1",
        actor_id=actor_id,
        occurred_at=occurred_at,
        payload={
            "reservation_number": "RSV-001",
            "item_id": aggregate_id,
            "quantity": Decimal("1.250000"),
            "from_status": "open",
            "to_status": "released",
        },
    )

    payload = OutboxEvent.objects.get(pk=event.id).payload
    assert payload["schema_version"] == 1
    assert payload["module"] == "inventory_management"
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["aggregate_id"] == str(aggregate_id)
    assert payload["actor_id"] == str(actor_id)
    assert payload["correlation_id"] == "inventory:event:1"
    assert payload["payload"]["item_id"] == str(aggregate_id)
    assert payload["payload"]["quantity"] == "1.250000"
    assert payload["occurred_at"] == occurred_at.isoformat()
    assert emit_event is publish_domain_event

    with pytest.raises(ValueError, match="unsupported"):
        publish_domain_event(tenant_id, "inventory.unknown/v1", "InventoryReservation", aggregate_id)
    with pytest.raises(ValueError, match="non-allowlisted"):
        publish_domain_event(
            tenant_id,
            "inventory.reservation.changed/v1",
            "InventoryReservation",
            aggregate_id,
            payload={"reservation_number": "RSV-001", "secret": "leak"},  # pragma: allowlist secret
        )
    with pytest.raises(ValueError, match="aggregate_type"):
        publish_domain_event(tenant_id, "inventory.stock.posted/v1", "bad aggregate", aggregate_id)
    with pytest.raises(ValueError, match="tenant_id"):
        publish_domain_event("not-a-uuid", "inventory.stock.posted/v1", "StockEntry", aggregate_id)
    with pytest.raises(ValueError, match="timezone-aware"):
        publish_domain_event(
            tenant_id,
            "inventory.stock.posted/v1",
            "StockEntry",
            aggregate_id,
            occurred_at=datetime.utcnow(),
        )
    with pytest.raises(ValueError, match="finite"):
        publish_domain_event(
            tenant_id,
            "inventory.reservation.changed/v1",
            "InventoryReservation",
            aggregate_id,
            payload={"reservation_number": "RSV-001", "quantity": Decimal("NaN")},
        )
    with pytest.raises(TypeError, match="not JSON serializable"):
        publish_domain_event(
            tenant_id,
            "inventory.reservation.changed/v1",
            "InventoryReservation",
            aggregate_id,
            payload={"reservation_number": "RSV-001", "quantity": object()},
        )


def test_receipt_reservation_issue_and_immutable_ledger() -> None:
    tenant_id, creator_id, approver_id = uuid4(), uuid4(), uuid4()
    warehouse, location, item = setup_masters(tenant_id, creator_id)
    receipt = StockEntryService.create_draft(
        tenant_id,
        creator_id,
        {
            "entry_number": "REC-001",
            "entry_type": "receipt",
            "posting_at": timezone.now(),
            "destination_warehouse_id": warehouse.id,
            "lines": [
                {
                    "item_id": item.id,
                    "destination_location_id": location.id,
                    "quantity": "10.000000",
                    "uom": "EA",
                    "unit_cost": "5.0000",
                }
            ],
        },
        "receipt-001",
    )
    posted = approve_and_post(tenant_id, creator_id, approver_id, receipt)
    assert posted.status == "posted"
    balance = StockBalance.objects.for_tenant(tenant_id).get(item=item, warehouse=warehouse, location=location)
    assert balance.quantity_on_hand == Decimal("10.000000")
    assert balance.quantity_available == Decimal("10.000000")
    assert balance.stock_value == Decimal("50.0000")

    reservation = ReservationService.reserve(
        tenant_id,
        creator_id,
        {
            "reservation_number": "RSV-001",
            "reference_module": "sales",
            "reference_type": "order",
            "reference_id": uuid4(),
            "item_id": item.id,
            "warehouse_id": warehouse.id,
            "location_id": location.id,
            "quantity": "3.000000",
        },
        "reservation-001",
    )
    balance.refresh_from_db()
    assert balance.quantity_allocated == Decimal("3.000000")
    assert balance.quantity_available == Decimal("7.000000")

    issue = StockEntryService.create_draft(
        tenant_id,
        creator_id,
        {
            "entry_number": "ISS-001",
            "entry_type": "issue",
            "posting_at": timezone.now(),
            "source_warehouse_id": warehouse.id,
            "lines": [
                {
                    "item_id": item.id,
                    "source_location_id": location.id,
                    "quantity": "3.000000",
                    "uom": "EA",
                }
            ],
        },
        "issue-001",
    )
    approve_and_post(tenant_id, creator_id, approver_id, issue)
    reservation.refresh_from_db()
    balance.refresh_from_db()
    assert reservation.status == "consumed"
    assert balance.quantity_on_hand == Decimal("7.000000")
    assert balance.quantity_allocated == Decimal("0.000000")
    assert balance.quantity_available == Decimal("7.000000")

    ledger = StockLedgerEntry.objects.for_tenant(tenant_id).first()
    with pytest.raises(ImmutableRecordError):
        ledger.delete()
    with pytest.raises(ImmutableRecordError):
        StockLedgerEntry.objects.for_tenant(tenant_id).update(value_after=0)


def test_configuration_bounds_preview_export_import_and_rollback() -> None:
    tenant_id, actor_id = uuid4(), uuid4()
    InventoryConfigurationService.get_effective(tenant_id, "development")
    proposed = {
        "default_valuation_method": "fifo",
        "allow_negative_stock": True,
        "require_stock_entry_approval": True,
        "enforce_creator_approver_separation": True,
        "max_lines_per_entry": 750,
        "reservation_ttl_minutes": 60,
        "expiry_warning_days": 45,
        "auto_expire_batches": True,
        "enabled_capabilities": {"barcode_scanning": True},
        "rollout_rules": {"enabled": True, "percentage": 25},
    }
    preview = InventoryConfigurationService.preview(tenant_id, "development", proposed)
    assert preview["valid"] is True
    assert "posting" in preview["affected_behaviors"]
    revision = InventoryConfigurationService.create_revision(
        tenant_id, "development", actor_id, proposed, "Enable controlled negative stock"
    )
    active = InventoryConfigurationService.activate(
        tenant_id, "development", revision.revision, actor_id, "config-activate-1"
    )
    assert active.allow_negative_stock is True
    document = InventoryConfigurationService.export_document(tenant_id, "development")
    imported = InventoryConfigurationService.import_document(
        tenant_id, "development", actor_id, document, "Portability verification", "config-import-1"
    )
    rolled_back = InventoryConfigurationService.rollback(
        tenant_id, "development", revision.revision, actor_id, "Rollback verification", "config-rollback-1"
    )
    assert imported.revision > revision.revision
    assert rolled_back.active_revision > imported.revision
    with pytest.raises(InventoryError):
        InventoryConfigurationService.preview(tenant_id, "development", {**proposed, "max_lines_per_entry": 5001})


def test_warehouse_service_legacy_update_archive_and_default_guardrails() -> None:
    tenant_id, actor_id = uuid4(), uuid4()
    warehouse = WarehouseService.create_warehouse(
        tenant_id,
        "LEGACY",
        "Legacy warehouse",
        actor_id=actor_id,
        idempotency_key="legacy-create",
        country_code="US",
    )

    updated = WarehouseService.update(
        tenant_id,
        warehouse.id,
        warehouse.version,
        actor_id,
        {"warehouse_name": "Updated legacy warehouse", "city": "Austin"},
    )
    assert updated.warehouse_name == "Updated legacy warehouse"
    assert updated.city == "Austin"
    assert updated.version == warehouse.version + 1

    with pytest.raises(InventoryError):
        WarehouseService.update(tenant_id, warehouse.id, 0, actor_id, {"warehouse_name": "Rejected"})

    archived = WarehouseService.archive(tenant_id, warehouse.id, updated.version, actor_id)
    assert archived.is_active is False
    assert archived.is_default is False
    assert archived.archived_at is not None

    with pytest.raises(InventoryError):
        WarehouseService.set_default(tenant_id, archived.id, actor_id, "archived-default")


def test_tracking_resources_validate_item_modes_and_lifecycle_commands() -> None:
    tenant_id, actor_id = uuid4(), uuid4()
    warehouse = WarehouseService.create(
        tenant_id,
        actor_id,
        {
            "warehouse_code": "TRACK",
            "warehouse_name": "Tracking warehouse",
            "warehouse_type": "distribution_center",
            "country_code": "US",
            "timezone": "UTC",
        },
        "warehouse-track",
    )
    batch_item = ItemService.create(
        tenant_id,
        actor_id,
        {
            "item_code": "BATCH-SKU",
            "item_name": "Batch SKU",
            "base_uom": "EA",
            "tracking_mode": "batch",
            "valuation_method": "fifo",
        },
        "item-batch",
    )
    serial_item = ItemService.create(
        tenant_id,
        actor_id,
        {
            "item_code": "SER-SKU",
            "item_name": "Serial SKU",
            "base_uom": "EA",
            "tracking_mode": "serial",
            "valuation_method": "standard_cost",
            "standard_cost": "12.5000",
        },
        "item-serial",
    )
    plain_item = ItemService.create(
        tenant_id,
        actor_id,
        {
            "item_code": "PLAIN-SKU",
            "item_name": "Plain SKU",
            "base_uom": "EA",
            "tracking_mode": "none",
            "valuation_method": "weighted_average",
        },
        "item-plain",
    )

    with pytest.raises(InventoryError):
        BatchService.register(
            tenant_id,
            actor_id,
            {"item_id": plain_item.id, "batch_number": "B-001"},
            "batch-wrong-mode",
        )
    batch = BatchService.register(
        tenant_id,
        actor_id,
        {
            "item_id": batch_item.id,
            "batch_number": "B-001",
            "supplier_batch_number": "SUP-001",
            "manufactured_on": timezone.localdate(),
        },
        "batch-001",
    )
    batch = BatchService.activate(tenant_id, batch.id, actor_id, "batch-activate")
    assert batch.status == "active"
    batch = BatchService.quarantine(tenant_id, batch.id, actor_id, "batch-quarantine")
    assert batch.status == "quarantined"
    batch = BatchService.release(tenant_id, batch.id, actor_id, "batch-release")
    assert batch.status == "active"
    batch = BatchService.recall(tenant_id, batch.id, actor_id, "batch-recall")
    assert batch.status == "recalled"

    with pytest.raises(InventoryError):
        SerialNumberService.register(
            tenant_id,
            actor_id,
            {"item_id": plain_item.id, "serial_number": "S-001"},
            "serial-wrong-mode",
        )
    serial = SerialNumberService.register(
        tenant_id,
        actor_id,
        {
            "item_id": serial_item.id,
            "serial_number": "S-001",
            "manufacturer": "BuildWorks",
            "model_number": "M1",
        },
        "serial-001",
    )
    serial = SerialNumberService.update_metadata(
        tenant_id,
        serial.id,
        serial.version,
        actor_id,
        {"manufacturer": "BuildWorks Labs", "model_number": "M2"},
    )
    assert serial.manufacturer == "BuildWorks Labs"
    serial = SerialNumberService.scrap(tenant_id, serial.id, actor_id, "serial-scrap")
    assert serial.status == "scrapped"
    assert serial.current_warehouse is None
    assert warehouse.is_active is True


def test_cycle_count_adjustment_and_query_dashboard_paths() -> None:
    tenant_id, creator_id, approver_id = uuid4(), uuid4(), uuid4()
    warehouse, location, item = setup_masters(tenant_id, creator_id)
    receipt = StockEntryService.create_draft(
        tenant_id,
        creator_id,
        {
            "entry_number": "REC-CC",
            "entry_type": "receipt",
            "posting_at": timezone.now(),
            "destination_warehouse_id": warehouse.id,
            "lines": [
                {
                    "item_id": item.id,
                    "destination_location_id": location.id,
                    "quantity": "4.000000",
                    "uom": "EA",
                    "unit_cost": "2.0000",
                }
            ],
        },
        "receipt-cycle-count",
    )
    approve_and_post(tenant_id, creator_id, approver_id, receipt)

    count = CycleCountService.create(
        tenant_id,
        creator_id,
        {
            "count_number": "CC-001",
            "warehouse_id": warehouse.id,
            "location_id": location.id,
            "count_type": "location",
            "scheduled_for": timezone.localdate(),
            "lines": [{"item_id": item.id, "location_id": location.id}],
        },
        "cycle-count-001",
    )
    count = CycleCountService.update_scheduled(
        tenant_id,
        count.id,
        count.version,
        creator_id,
        {"assigned_to_id": approver_id, "scheduled_for": timezone.localdate()},
    )
    count = CycleCountService.start(tenant_id, count.id, creator_id, "cc-start")
    assert count.status == "in_progress"
    line = count.lines.get()
    assert line.system_quantity == Decimal("4.000000")

    with pytest.raises(InventoryError):
        CycleCountService.record_counts(
            tenant_id,
            count.id,
            creator_id,
            [{"id": line.id, "counted_quantity": "-1.000000"}],
        )
    CycleCountService.record_counts(
        tenant_id,
        count.id,
        creator_id,
        [{"id": line.id, "counted_quantity": "6.000000"}],
    )
    count = CycleCountService.submit(tenant_id, count.id, creator_id, "cc-submit")
    count = CycleCountService.approve(tenant_id, count.id, approver_id, "cc-approve")
    count = CycleCountService.post_adjustment(tenant_id, count.id, approver_id, "cc-post")
    assert count.status == "posted"
    assert StockBalance.objects.for_tenant(tenant_id).get(item=item, location=location).quantity_on_hand == Decimal(
        "6.000000"
    )

    assert InventoryQueryService.get_balance(
        tenant_id, StockBalance.objects.for_tenant(tenant_id).get(item=item, location=location).id
    )
    assert InventoryQueryService.list_balances(tenant_id, item=item).count() == 1
    assert InventoryQueryService.list_ledger(tenant_id, item=item).count() >= 2
    summary = InventoryQueryService.stock_summary(tenant_id)
    assert summary["on_hand"] == Decimal("6.000000")
    dashboard = InventoryQueryService.dashboard(tenant_id)
    assert dashboard["onboarding"]["warehouse_created"] is True
    assert dashboard["onboarding"]["first_receipt_posted"] is True


def test_bulk_import_and_configuration_import_fail_closed_paths() -> None:
    tenant_id, actor_id = uuid4(), uuid4()
    with pytest.raises(InventoryError):
        InventoryBulkService.enqueue_import(
            tenant_id,
            actor_id,
            "unsupported",
            "doc://inventory.csv",
            "bulk-import-bad",
        )
    with pytest.raises(InventoryError):
        InventoryBulkService.enqueue_import(tenant_id, actor_id, "items", "", "bulk-import-empty-doc")

    document = InventoryConfigurationService.export_document(tenant_id, "development")
    with pytest.raises(InventoryError):
        InventoryConfigurationService.import_document(
            tenant_id,
            "production",
            actor_id,
            document,
            "Wrong environment",
            "config-import-wrong-env",
        )
    with pytest.raises(InventoryError):
        InventoryConfigurationService.import_document(
            tenant_id,
            "development",
            actor_id,
            {**document, "checksum": "sha256:not-the-checksum"},
            "Tampered checksum",
            "config-import-bad-checksum",
        )
    with pytest.raises(InventoryError):
        InventoryConfigurationService.import_document(
            tenant_id,
            "development",
            actor_id,
            {**document, "configuration": "not-an-object"},
            "Malformed payload",
            "config-import-not-object",
        )


def test_location_defaulting_hierarchy_and_archive_conflicts() -> None:
    tenant_id, actor_id = uuid4(), uuid4()
    primary = WarehouseService.create(
        tenant_id,
        actor_id,
        {
            "warehouse_code": "LOC-A",
            "warehouse_name": "Location warehouse A",
            "warehouse_type": "distribution_center",
            "country_code": "US",
            "timezone": "UTC",
        },
        "warehouse-loc-a",
    )
    secondary = WarehouseService.create(
        tenant_id,
        actor_id,
        {
            "warehouse_code": "LOC-B",
            "warehouse_name": "Location warehouse B",
            "warehouse_type": "distribution_center",
            "country_code": "US",
            "timezone": "UTC",
        },
        "warehouse-loc-b",
    )
    first_default = StorageLocationService.ensure_default_location(tenant_id, primary.id)
    assert StorageLocationService.ensure_default_location(tenant_id, primary.id).id == first_default.id

    override_default = StorageLocationService.create(
        tenant_id,
        actor_id,
        {
            "warehouse_id": primary.id,
            "location_code": "FAST",
            "location_name": "Fast pick",
            "zone_type": "picking",
            "location_type": "bin",
            "is_default": True,
        },
        "location-fast-default",
    )
    first_default.refresh_from_db()
    assert override_default.is_default is True
    assert first_default.is_default is False

    other_default = StorageLocationService.ensure_default_location(tenant_id, secondary.id)
    with pytest.raises(InventoryError) as wrong_parent:
        StorageLocationService.validate_hierarchy(tenant_id, primary.id, other_default.id)
    assert wrong_parent.value.message_dict == {"parent_id": ["Parent must belong to the selected warehouse."]}

    child = StorageLocationService.create(
        tenant_id,
        actor_id,
        {
            "warehouse_id": primary.id,
            "parent_id": override_default.id,
            "location_code": "FAST-01",
            "location_name": "Fast pick child",
            "zone_type": "picking",
            "location_type": "bin",
        },
        "location-fast-child",
    )
    with pytest.raises(InventoryError) as cycle:
        StorageLocationService.update(
            tenant_id,
            override_default.id,
            override_default.version,
            actor_id,
            {"parent_id": child.id},
        )
    assert cycle.value.message_dict == {"parent_id": ["Location hierarchy cannot contain a cycle."]}

    item_record = ItemService.create(
        tenant_id,
        actor_id,
        {
            "item_code": "LOC-STOCK",
            "item_name": "Location stock",
            "base_uom": "EA",
            "tracking_mode": "none",
            "valuation_method": "weighted_average",
        },
        "item-loc-stock",
    )
    StockBalance.objects.create(
        tenant_id=tenant_id,
        item=item_record,
        warehouse=primary,
        location=override_default,
        quantity_on_hand="1.000000",
        quantity_available="1.000000",
    )
    with pytest.raises(InventoryConflict):
        StorageLocationService.archive(tenant_id, override_default.id, override_default.version, actor_id)


def test_item_archive_and_tracking_changes_fail_when_history_exists() -> None:
    tenant_id, actor_id, approver_id = uuid4(), uuid4(), uuid4()
    warehouse, location, item_record = setup_masters(tenant_id, actor_id)
    receipt = StockEntryService.create_draft(
        tenant_id,
        actor_id,
        {
            "entry_number": "REC-HISTORY",
            "entry_type": "receipt",
            "posting_at": timezone.now(),
            "destination_warehouse_id": warehouse.id,
            "lines": [
                {
                    "item_id": item_record.id,
                    "destination_location_id": location.id,
                    "quantity": "1.000000",
                    "uom": "EA",
                    "unit_cost": "2.0000",
                }
            ],
        },
        "receipt-history",
    )
    approve_and_post(tenant_id, actor_id, approver_id, receipt)

    with pytest.raises(InventoryConflict):
        ItemService.update(
            tenant_id,
            item_record.id,
            item_record.version,
            actor_id,
            {"tracking_mode": "batch"},
        )
    with pytest.raises(InventoryConflict):
        ItemService.archive(tenant_id, item_record.id, item_record.version, actor_id)


def test_stock_entry_idempotency_limits_and_delete_conflicts() -> None:
    tenant_id, actor_id = uuid4(), uuid4()
    warehouse, location, item_record = setup_masters(tenant_id, actor_id)
    config = InventoryConfigurationService.get_effective(tenant_id, "development")
    config.max_lines_per_entry = 1
    config.save()

    command = {
        "entry_number": "REC-IDEM",
        "entry_type": "receipt",
        "posting_at": timezone.now(),
        "destination_warehouse_id": warehouse.id,
        "lines": [
            {
                "item_id": item_record.id,
                "destination_location_id": location.id,
                "quantity": "1.000000",
                "uom": "EA",
                "unit_cost": "1.0000",
            },
            {
                "item_id": item_record.id,
                "destination_location_id": location.id,
                "quantity": "1.000000",
                "uom": "EA",
                "unit_cost": "1.0000",
            },
        ],
    }
    with pytest.raises(InventoryError) as too_many_lines:
        StockEntryService.create_draft(tenant_id, actor_id, command, "receipt-too-many-lines")
    assert too_many_lines.value.message_dict == {"lines": ["At most 1 lines are permitted."]}

    config.max_lines_per_entry = 500
    config.save()
    entry = StockEntryService.create_draft(
        tenant_id,
        actor_id,
        {**command, "entry_number": "REC-IDEM-OK", "lines": command["lines"][:1]},
        "receipt-idempotent",
    )
    assert (
        StockEntryService.create_draft(
            tenant_id,
            actor_id,
            {**command, "entry_number": "REC-IDEM-DIFFERENT", "lines": []},
            "receipt-idempotent",
        ).id
        == entry.id
    )

    submitted = StockEntryService.submit(tenant_id, entry.id, actor_id, "entry-submit-idem")
    with pytest.raises(InventoryConflict):
        StockEntryService.update_draft(
            tenant_id,
            submitted.id,
            submitted.version,
            actor_id,
            {"reason": "Cannot update submitted entries"},
        )
    with pytest.raises(InventoryConflict):
        StockEntryService.delete_draft(tenant_id, submitted.id, submitted.version, actor_id)


def test_reservation_update_release_cancel_and_active_warehouse_archive_guard() -> None:
    tenant_id, actor_id = uuid4(), uuid4()
    warehouse, location, item_record = setup_masters(tenant_id, actor_id)
    StockBalance.objects.create(
        tenant_id=tenant_id,
        item=item_record,
        warehouse=warehouse,
        location=location,
        quantity_on_hand="5.000000",
        quantity_available="5.000000",
    )
    reservation = ReservationService.reserve(
        tenant_id,
        actor_id,
        {
            "reservation_number": "RSV-GUARD",
            "reference_module": "sales",
            "reference_type": "order",
            "reference_id": uuid4(),
            "item_id": item_record.id,
            "warehouse_id": warehouse.id,
            "location_id": location.id,
            "quantity": "2.000000",
        },
        "reservation-guard",
    )

    with pytest.raises(InventoryConflict):
        WarehouseService.archive(tenant_id, warehouse.id, warehouse.version, actor_id)

    updated = ReservationService.update(
        tenant_id,
        reservation.id,
        reservation.version,
        actor_id,
        {"expires_at": timezone.now() + timedelta(hours=2)},
    )
    assert updated.expires_at is not None
    released = ReservationService.release(tenant_id, updated.id, actor_id, "reservation-release")
    assert released.status == "released"

    second = ReservationService.reserve(
        tenant_id,
        actor_id,
        {
            "reservation_number": "RSV-CANCEL",
            "reference_module": "sales",
            "reference_type": "order",
            "reference_id": uuid4(),
            "item_id": item_record.id,
            "warehouse_id": warehouse.id,
            "location_id": location.id,
            "quantity": "1.000000",
        },
        "reservation-cancel",
    )
    cancelled = ReservationService.cancel(tenant_id, second.id, actor_id, "reservation-cancel-command")
    assert cancelled.status == "cancelled"
    assert StockReservation.objects.for_tenant(tenant_id).filter(status="active").count() == 0


def test_batch_expire_exhaust_and_serial_scrap_replay_paths() -> None:
    tenant_id, actor_id = uuid4(), uuid4()
    batch_item = ItemService.create(
        tenant_id,
        actor_id,
        {
            "item_code": "BATCH-CMDS",
            "item_name": "Batch commands",
            "base_uom": "EA",
            "tracking_mode": "batch",
            "valuation_method": "fifo",
        },
        "item-batch-cmds",
    )
    serial_item = ItemService.create(
        tenant_id,
        actor_id,
        {
            "item_code": "SER-CMDS",
            "item_name": "Serial commands",
            "base_uom": "EA",
            "tracking_mode": "serial",
            "valuation_method": "standard_cost",
            "standard_cost": "4.0000",
        },
        "item-serial-cmds",
    )
    expiring = BatchService.register(
        tenant_id,
        actor_id,
        {"item_id": batch_item.id, "batch_number": "BATCH-EXPIRE"},
        "batch-expire",
    )
    BatchService.activate(tenant_id, expiring.id, actor_id, "batch-expire-activate")
    assert BatchService.expire(tenant_id, expiring.id, actor_id, "batch-expire-command").status == "expired"

    exhausted = BatchService.register(
        tenant_id,
        actor_id,
        {"item_id": batch_item.id, "batch_number": "BATCH-EXHAUST"},
        "batch-exhaust",
    )
    BatchService.activate(tenant_id, exhausted.id, actor_id, "batch-exhaust-activate")
    assert BatchService.exhaust(tenant_id, exhausted.id, actor_id, "batch-exhaust-command").status == "exhausted"

    serial = SerialNumberService.register(
        tenant_id,
        actor_id,
        {"item_id": serial_item.id, "serial_number": "SER-CMDS-001"},
        "serial-cmds",
    )
    scrapped = SerialNumberService.scrap(tenant_id, serial.id, actor_id, "serial-scrap-idem")
    replayed = SerialNumberService.scrap(tenant_id, serial.id, actor_id, "serial-scrap-idem")
    assert replayed.id == scrapped.id
    assert replayed.status == "scrapped"


def test_stock_entry_update_delete_approval_and_reversal_replay_paths() -> None:
    tenant_id, creator_id, approver_id = uuid4(), uuid4(), uuid4()
    warehouse, location, item_record = setup_masters(tenant_id, creator_id)
    draft = StockEntryService.create_draft(
        tenant_id,
        creator_id,
        {
            "entry_number": "REC-LIFECYCLE",
            "entry_type": "receipt",
            "posting_at": timezone.now(),
            "destination_warehouse_id": warehouse.id,
            "reason": "Initial receipt",
            "lines": [
                {
                    "item_id": item_record.id,
                    "destination_location_id": location.id,
                    "quantity": "2.000000",
                    "uom": "EA",
                    "unit_cost": "3.0000",
                }
            ],
        },
        "receipt-lifecycle",
    )
    updated = StockEntryService.update_draft(
        tenant_id,
        draft.id,
        draft.version,
        creator_id,
        {
            "reason": "Updated receipt",
            "lines": [
                {
                    "item_id": item_record.id,
                    "destination_location_id": location.id,
                    "quantity": "3.000000",
                    "uom": "EA",
                    "unit_cost": "3.0000",
                }
            ],
        },
    )
    assert updated.reason == "Updated receipt"
    assert updated.lines.get().quantity == Decimal("3.000000")

    deleted = StockEntryService.create_draft(
        tenant_id,
        creator_id,
        {
            "entry_number": "REC-DELETE",
            "entry_type": "receipt",
            "posting_at": timezone.now(),
            "destination_warehouse_id": warehouse.id,
            "lines": [],
        },
        "receipt-delete",
    )
    assert StockEntryService.delete_draft(tenant_id, deleted.id, deleted.version, creator_id).status == "cancelled"

    submitted = StockEntryService.submit(tenant_id, updated.id, creator_id, "receipt-lifecycle-submit")
    with pytest.raises(InventoryConflict):
        StockEntryService.approve(tenant_id, submitted.id, creator_id, "receipt-lifecycle-self-approve")
    with pytest.raises(InventoryConflict):
        InventoryPostingService.post(tenant_id, submitted.id, approver_id, "receipt-lifecycle-post-too-early")

    StockEntryService.approve(tenant_id, submitted.id, approver_id, "receipt-lifecycle-approve")
    posted = InventoryPostingService.post(tenant_id, submitted.id, approver_id, "receipt-lifecycle-post")
    reversal = StockEntryService.reverse(tenant_id, posted.id, approver_id, "Reverse receipt", "receipt-lifecycle-rev")
    replayed = StockEntryService.reverse(tenant_id, posted.id, approver_id, "Ignored", "receipt-lifecycle-rev")
    assert reversal.status == "posted"
    assert replayed.id == reversal.id
    posted.refresh_from_db()
    assert posted.status == "reversed"


def test_duplicate_dimensions_and_negative_stock_are_rejected_on_posting() -> None:
    tenant_id, creator_id, approver_id = uuid4(), uuid4(), uuid4()
    warehouse, location, item_record = setup_masters(tenant_id, creator_id)
    duplicate = StockEntryService.create_draft(
        tenant_id,
        creator_id,
        {
            "entry_number": "REC-DUP-DIM",
            "entry_type": "receipt",
            "posting_at": timezone.now(),
            "destination_warehouse_id": warehouse.id,
            "lines": [
                {
                    "item_id": item_record.id,
                    "destination_location_id": location.id,
                    "quantity": "1.000000",
                    "uom": "EA",
                    "unit_cost": "1.0000",
                },
                {
                    "item_id": item_record.id,
                    "destination_location_id": location.id,
                    "quantity": "1.000000",
                    "uom": "EA",
                    "unit_cost": "1.0000",
                },
            ],
        },
        "receipt-duplicate-dimensions",
    )
    StockEntryService.submit(tenant_id, duplicate.id, creator_id, "receipt-duplicate-submit")
    StockEntryService.approve(tenant_id, duplicate.id, approver_id, "receipt-duplicate-approve")
    with pytest.raises(InventoryError) as duplicate_exc:
        InventoryPostingService.post(tenant_id, duplicate.id, approver_id, "receipt-duplicate-post")
    assert duplicate_exc.value.message_dict == {"lines": ["Duplicate stock dimensions are not permitted."]}

    issue = StockEntryService.create_draft(
        tenant_id,
        creator_id,
        {
            "entry_number": "ISS-NEGATIVE",
            "entry_type": "issue",
            "posting_at": timezone.now(),
            "source_warehouse_id": warehouse.id,
            "lines": [
                {
                    "item_id": item_record.id,
                    "source_location_id": location.id,
                    "quantity": "1.000000",
                    "uom": "EA",
                }
            ],
        },
        "issue-negative-stock",
    )
    StockEntryService.submit(tenant_id, issue.id, creator_id, "issue-negative-submit")
    StockEntryService.approve(tenant_id, issue.id, approver_id, "issue-negative-approve")
    with pytest.raises(InventoryError) as stock_exc:
        InventoryPostingService.post(tenant_id, issue.id, approver_id, "issue-negative-post")
    assert "Insufficient stock" in stock_exc.value.message_dict["quantity"][0]


def test_reservation_expiry_count_and_queue_paths() -> None:
    tenant_id, actor_id = uuid4(), uuid4()
    warehouse, location, item_record = setup_masters(tenant_id, actor_id)
    StockBalance.objects.create(
        tenant_id=tenant_id,
        item=item_record,
        warehouse=warehouse,
        location=location,
        quantity_on_hand="10.000000",
        quantity_available="10.000000",
    )
    due = ReservationService.reserve(
        tenant_id,
        actor_id,
        {
            "reservation_number": "RSV-DUE",
            "reference_module": "sales",
            "reference_type": "order",
            "reference_id": uuid4(),
            "item_id": item_record.id,
            "warehouse_id": warehouse.id,
            "location_id": location.id,
            "quantity": "1.000000",
            "expires_at": timezone.now() - timedelta(minutes=1),
        },
        "reservation-due",
    )
    assert ReservationService.expire_due(tenant_id, actor_id) == 1
    due.refresh_from_db()
    assert due.status == "expired"

    for index in range(2):
        ReservationService.reserve(
            tenant_id,
            actor_id,
            {
                "reservation_number": f"RSV-QUEUE-{index}",
                "reference_module": "sales",
                "reference_type": "order",
                "reference_id": uuid4(),
                "item_id": item_record.id,
                "warehouse_id": warehouse.id,
                "location_id": location.id,
                "quantity": "1.000000",
                "expires_at": timezone.now() - timedelta(minutes=1),
            },
            f"reservation-queue-{index}",
        )
    job = ReservationService.expire_due(tenant_id, actor_id, queue_threshold=1)
    assert job.command == "inventory.expire_reservations"


def test_cycle_count_no_variance_cancel_reject_and_replay_paths() -> None:
    tenant_id, creator_id, approver_id = uuid4(), uuid4(), uuid4()
    warehouse, location, item_record = setup_masters(tenant_id, creator_id)
    count = CycleCountService.create(
        tenant_id,
        creator_id,
        {
            "count_number": "CC-NO-VAR",
            "warehouse_id": warehouse.id,
            "location_id": location.id,
            "count_type": "location",
            "scheduled_for": timezone.localdate(),
            "lines": [{"item_id": item_record.id, "location_id": location.id}],
        },
        "cycle-count-no-var",
    )
    editable = CycleCountService.update_scheduled(
        tenant_id,
        count.id,
        count.version,
        creator_id,
        {"assigned_to_id": approver_id},
    )
    assert editable.assigned_to_id == approver_id

    cancelled = CycleCountService.create(
        tenant_id,
        creator_id,
        {
            "count_number": "CC-CANCEL",
            "warehouse_id": warehouse.id,
            "location_id": location.id,
            "count_type": "location",
            "scheduled_for": timezone.localdate(),
            "lines": [{"item_id": item_record.id, "location_id": location.id}],
        },
        "cycle-count-cancel",
    )
    assert CycleCountService.cancel(tenant_id, cancelled.id, creator_id, "cycle-count-cancel").status == "cancelled"

    CycleCountService.start(tenant_id, count.id, creator_id, "cycle-count-no-var-start")
    line = count.lines.get()
    CycleCountService.record_counts(
        tenant_id,
        count.id,
        creator_id,
        [{"id": line.id, "counted_quantity": "0.000000"}],
    )
    CycleCountService.submit(tenant_id, count.id, creator_id, "cycle-count-no-var-submit")
    rejected = CycleCountService.reject(tenant_id, count.id, approver_id, "cycle-count-no-var-reject")
    assert rejected.status == "in_progress"
    CycleCountService.submit(tenant_id, count.id, creator_id, "cycle-count-no-var-resubmit")
    CycleCountService.approve(tenant_id, count.id, approver_id, "cycle-count-no-var-approve")
    posted = CycleCountService.post_adjustment(tenant_id, count.id, approver_id, "cycle-count-no-var-post")
    replayed = CycleCountService.post_adjustment(tenant_id, count.id, approver_id, "cycle-count-no-var-post")
    assert posted.status == "posted"
    assert replayed.id == posted.id
