"""Production-faithful inventory tenant-isolation contracts."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping
from uuid import UUID, uuid4

import pytest

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.core.testing import TenantIsolationContract
from django.utils import timezone

from src.modules.inventory_management.models import (
    Batch,
    CycleCount,
    InventoryConfiguration,
    Item,
    SerialNumber,
    StockEntry,
    StockReservation,
    StorageLocation,
    Warehouse,
)

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db

BASE = "/api/v2/inventory-management"


@pytest.fixture(autouse=True)
def allow_declared_inventory_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def allow(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="inventory isolation projection",
            tenant_id=UUID(str(tenant_id)),
            remaining_quota=100,
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", allow)


class V2InventoryIsolationContract(TenantIsolationContract):
    """Extract rows from the governed envelope and require non-disclosing 404s."""

    read_denial_statuses = frozenset({404})

    def get_list_items(self, response: Any) -> list[Mapping[str, Any]]:
        payload = response.json()
        assert set(payload) == {"data", "meta"}
        assert payload["meta"]["correlation_id"]
        return payload["data"]


def make_warehouse(tenant_id, code: str) -> Warehouse:
    return Warehouse.objects.create(
        tenant_id=tenant_id,
        warehouse_code=code,
        warehouse_name=f"Warehouse {code}",
        warehouse_type="distribution_center",
        country_code="US",
        timezone="UTC",
    )


def make_item(tenant_id, code: str) -> Item:
    return Item.objects.create(
        tenant_id=tenant_id,
        item_code=code,
        item_name=f"Item {code}",
        base_uom="EA",
        tracking_mode="none",
        valuation_method="fifo",
    )


class TestWarehouseIsolation(V2InventoryIsolationContract):
    model = Warehouse
    list_url = f"{BASE}/warehouses/"
    detail_url_template = f"{BASE}/warehouses/{{pk}}/"
    create_payload = {
        "warehouse_code": "WH-SPOOF",
        "warehouse_name": "Spoof attempt",
        "warehouse_type": "distribution_center",
        "country_code": "US",
        "timezone": "UTC",
    }
    update_payload = {"warehouse_name": "Cross-tenant overwrite", "expected_version": 1}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = make_warehouse(tenant_a.id, "WH-A")
        self.tenant_b_row = make_warehouse(tenant_b.id, "WH-B")


class TestItemIsolation(V2InventoryIsolationContract):
    model = Item
    list_url = f"{BASE}/items/"
    detail_url_template = f"{BASE}/items/{{pk}}/"
    create_payload = {
        "item_code": "ITEM-SPOOF",
        "item_name": "Spoof attempt",
        "base_uom": "EA",
        "tracking_mode": "none",
        "valuation_method": "fifo",
    }
    update_payload = {"item_name": "Cross-tenant overwrite", "expected_version": 1}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = make_item(tenant_a.id, "ITEM-A")
        self.tenant_b_row = make_item(tenant_b.id, "ITEM-B")


class CommandOwnedIsolationContract(V2InventoryIsolationContract):
    """Resources without generic DELETE may fail closed before object lookup."""

    read_denial_statuses = frozenset({403, 404, 405})


class TestStorageLocationIsolation(V2InventoryIsolationContract):
    model = StorageLocation
    list_url = f"{BASE}/locations/"
    detail_url_template = f"{BASE}/locations/{{pk}}/"
    update_payload = {"location_name": "Cross-tenant overwrite", "expected_version": 1}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        warehouse_a = make_warehouse(tenant_a.id, "LOC-WH-A")
        warehouse_b = make_warehouse(tenant_b.id, "LOC-WH-B")
        self.tenant_a_row = StorageLocation.objects.create(
            tenant_id=tenant_a.id, warehouse=warehouse_a, location_code="BIN-A",
            location_name="Bin A", zone_type="storage", location_type="bin",
        )
        self.tenant_b_row = StorageLocation.objects.create(
            tenant_id=tenant_b.id, warehouse=warehouse_b, location_code="BIN-B",
            location_name="Bin B", zone_type="storage", location_type="bin",
        )
        self.create_payload = {
            "warehouse_id": str(warehouse_a.id), "location_code": "BIN-SPOOF",
            "location_name": "Spoof bin", "zone_type": "storage", "location_type": "bin",
        }


class TestBatchIsolation(CommandOwnedIsolationContract):
    model = Batch
    list_url = f"{BASE}/batches/"
    detail_url_template = f"{BASE}/batches/{{pk}}/"
    update_payload = {"supplier_batch_number": "CROSS-TENANT", "expected_version": 1}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        item_a = make_item(tenant_a.id, "BATCH-ITEM-A")
        item_b = make_item(tenant_b.id, "BATCH-ITEM-B")
        item_a.tracking_mode = item_b.tracking_mode = "batch"
        item_a.save(update_fields=("tracking_mode",))
        item_b.save(update_fields=("tracking_mode",))
        self.tenant_a_row = Batch.objects.create(tenant_id=tenant_a.id, item=item_a, batch_number="LOT-A")
        self.tenant_b_row = Batch.objects.create(tenant_id=tenant_b.id, item=item_b, batch_number="LOT-B")
        self.create_payload = {"item_id": str(item_a.id), "batch_number": "LOT-SPOOF"}


class TestSerialNumberIsolation(CommandOwnedIsolationContract):
    model = SerialNumber
    list_url = f"{BASE}/serial-numbers/"
    detail_url_template = f"{BASE}/serial-numbers/{{pk}}/"
    update_payload = {"manufacturer": "Cross-tenant overwrite", "expected_version": 1}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        item_a = make_item(tenant_a.id, "SERIAL-ITEM-A")
        item_b = make_item(tenant_b.id, "SERIAL-ITEM-B")
        item_a.tracking_mode = item_b.tracking_mode = "serial"
        item_a.save(update_fields=("tracking_mode",))
        item_b.save(update_fields=("tracking_mode",))
        self.tenant_a_row = SerialNumber.objects.create(tenant_id=tenant_a.id, item=item_a, serial_number="SER-A")
        self.tenant_b_row = SerialNumber.objects.create(tenant_id=tenant_b.id, item=item_b, serial_number="SER-B")
        self.create_payload = {"item_id": str(item_a.id), "serial_number": "SER-SPOOF"}


class TestStockEntryIsolation(V2InventoryIsolationContract):
    model = StockEntry
    list_url = f"{BASE}/stock-entries/"
    detail_url_template = f"{BASE}/stock-entries/{{pk}}/"
    update_payload = {"reason": "Cross-tenant overwrite", "expected_version": 1}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        warehouse_a = make_warehouse(tenant_a.id, "ENTRY-WH-A")
        warehouse_b = make_warehouse(tenant_b.id, "ENTRY-WH-B")
        self.tenant_a_row = StockEntry.objects.create(
            tenant_id=tenant_a.id, entry_number="ENT-A", entry_type="receipt",
            posting_at=timezone.now(), destination_warehouse=warehouse_a,
            idempotency_key="entry-a", created_by_id=uuid4(),
        )
        self.tenant_b_row = StockEntry.objects.create(
            tenant_id=tenant_b.id, entry_number="ENT-B", entry_type="receipt",
            posting_at=timezone.now(), destination_warehouse=warehouse_b,
            idempotency_key="entry-b", created_by_id=uuid4(),
        )
        self.create_payload = {
            "entry_number": "ENT-SPOOF", "entry_type": "receipt",
            "posting_at": timezone.now().isoformat(), "destination_warehouse_id": str(warehouse_a.id),
            "lines": [],
        }


class TestReservationIsolation(CommandOwnedIsolationContract):
    model = StockReservation
    list_url = f"{BASE}/reservations/"
    detail_url_template = f"{BASE}/reservations/{{pk}}/"
    update_payload = {"expires_at": None, "expected_version": 1}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        warehouse_a, warehouse_b = make_warehouse(tenant_a.id, "RES-WH-A"), make_warehouse(tenant_b.id, "RES-WH-B")
        item_a, item_b = make_item(tenant_a.id, "RES-ITEM-A"), make_item(tenant_b.id, "RES-ITEM-B")
        base = {"reference_module": "sales", "reference_type": "order", "reference_id": uuid4(), "quantity": "1", "status": "active"}
        self.tenant_a_row = StockReservation.objects.create(tenant_id=tenant_a.id, reservation_number="RES-A", item=item_a, warehouse=warehouse_a, idempotency_key="res-a", **base)
        self.tenant_b_row = StockReservation.objects.create(tenant_id=tenant_b.id, reservation_number="RES-B", item=item_b, warehouse=warehouse_b, idempotency_key="res-b", **{**base, "reference_id": uuid4()})
        self.create_payload = {"reservation_number": "RES-SPOOF", "reference_module": "sales", "reference_type": "order", "reference_id": str(uuid4()), "item_id": str(item_a.id), "warehouse_id": str(warehouse_a.id), "quantity": "1"}


class TestCycleCountIsolation(CommandOwnedIsolationContract):
    model = CycleCount
    list_url = f"{BASE}/cycle-counts/"
    detail_url_template = f"{BASE}/cycle-counts/{{pk}}/"
    update_payload = {"scheduled_for": "2030-02-01", "expected_version": 1}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        warehouse_a, warehouse_b = make_warehouse(tenant_a.id, "COUNT-WH-A"), make_warehouse(tenant_b.id, "COUNT-WH-B")
        self.tenant_a_row = CycleCount.objects.create(tenant_id=tenant_a.id, count_number="COUNT-A", warehouse=warehouse_a, count_type="full", scheduled_for=date(2030, 1, 1))
        self.tenant_b_row = CycleCount.objects.create(tenant_id=tenant_b.id, count_number="COUNT-B", warehouse=warehouse_b, count_type="full", scheduled_for=date(2030, 1, 1))
        self.create_payload = {"count_number": "COUNT-SPOOF", "warehouse_id": str(warehouse_a.id), "count_type": "full", "scheduled_for": "2030-01-01", "lines": []}


class TestConfigurationIsolation(CommandOwnedIsolationContract):
    model = InventoryConfiguration
    list_url = f"{BASE}/configurations/"
    detail_url_template = f"{BASE}/configurations/{{pk}}/"
    row_identity_attribute = "environment"
    response_identity_field = "environment"
    update_payload = {"change_reason": "Cross-tenant overwrite", "allow_negative_stock": True}
    create_payload = {"environment": "production"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = InventoryConfiguration.objects.create(tenant_id=tenant_a.id, environment="development", status="active")
        self.tenant_b_row = InventoryConfiguration.objects.create(tenant_id=tenant_b.id, environment="staging", status="active")
