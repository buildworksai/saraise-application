"""End-to-end service invariants for core inventory operations."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from django.utils import timezone

from src.modules.inventory_management.models import (
    ImmutableRecordError,
    StockBalance,
    StockLedgerEntry,
)
from src.modules.inventory_management.services import (
    InventoryConfigurationService,
    InventoryError,
    InventoryPostingService,
    ItemService,
    ReservationService,
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
            "lines": [{
                "item_id": item.id,
                "destination_location_id": location.id,
                "quantity": "10.000000",
                "uom": "EA",
                "unit_cost": "5.0000",
            }],
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
            "lines": [{
                "item_id": item.id,
                "source_location_id": location.id,
                "quantity": "3.000000",
                "uom": "EA",
            }],
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
    current = InventoryConfigurationService.get_effective(tenant_id, "development")
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
