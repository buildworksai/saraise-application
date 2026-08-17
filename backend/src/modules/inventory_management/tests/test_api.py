"""Governed v2 inventory API contract tests."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.modules.inventory_management import api as inventory_api
from src.modules.inventory_management.models import StockBalance, Warehouse
from src.modules.inventory_management.services import ItemService, StorageLocationService

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db

BASE = "/api/v2/inventory-management"


@pytest.fixture(autouse=True)
def allow_declared_inventory_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provision the explicit policy projection; production still fails closed."""

    def allow(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, kwargs
        assert required_permission.startswith("inventory.")
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="inventory test projection",
            tenant_id=UUID(str(tenant_id)),
            remaining_quota=100,
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", allow)


def warehouse(tenant_id, code="WH-01") -> Warehouse:
    return Warehouse.objects.create(
        tenant_id=tenant_id,
        warehouse_code=code,
        warehouse_name=f"Warehouse {code}",
        warehouse_type="distribution_center",
        country_code="US",
        timezone="UTC",
    )


def item(tenant_id, actor_id, code="SKU-API", **overrides):
    payload = {
        "item_code": code,
        "item_name": f"Item {code}",
        "base_uom": "EA",
        "tracking_mode": "none",
        "valuation_method": "weighted_average",
    }
    payload.update(overrides)
    return ItemService.create(tenant_id, actor_id, payload, f"item-{code}")


def test_missing_authentication_returns_401(api_client) -> None:
    response = api_client.get(f"{BASE}/warehouses/")
    assert response.status_code == 401
    problem = response.json()["error"]
    assert problem["code"]
    assert problem["correlation_id"]


def test_permission_mapping_skips_request_validation_for_openapi_schema_generation() -> None:
    view = inventory_api.ImportViewSet()
    view.swagger_fake_view = True
    view.action = "create"
    view.request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False), data={})

    assert view.get_permissions() == []


def test_list_uses_governed_envelope_and_pagination(authenticated_tenant_a_client, tenant_a) -> None:
    own = warehouse(tenant_a.id)
    response = authenticated_tenant_a_client.get(f"{BASE}/warehouses/?page_size=1&ordering=warehouse_code")
    assert response.status_code == 200
    payload = response.json()
    assert [row["id"] for row in payload["data"]] == [str(own.id)]
    assert payload["meta"]["correlation_id"]
    assert payload["meta"]["pagination"]["page_size"] == 1


def test_dashboard_returns_frontend_contract(authenticated_tenant_a_client, tenant_a) -> None:
    warehouse(tenant_a.id)
    response = authenticated_tenant_a_client.get(f"{BASE}/dashboard/")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert set(payload) == {"metrics", "alerts", "recent_entries", "low_stock_items", "onboarding"}
    assert {metric["label"] for metric in payload["metrics"]} == {
        "On hand",
        "Available",
        "Active reservations",
        "Open entries",
    }
    assert payload["alerts"] == []
    assert payload["onboarding"]["warehouse_created"] is True


def test_create_delegates_and_never_accepts_tenant_id(authenticated_tenant_a_client, tenant_a, tenant_b) -> None:
    payload = {
        "warehouse_code": "WH-02",
        "warehouse_name": "Secondary warehouse",
        "warehouse_type": "retail_store",
        "country_code": "GB",
        "timezone": "Europe/London",
    }
    response = authenticated_tenant_a_client.post(
        f"{BASE}/warehouses/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="warehouse-create-02",
    )
    assert response.status_code == 201, response.content
    created = Warehouse.objects.get(pk=response.json()["data"]["id"])
    assert created.tenant_id == tenant_a.id
    assert created.tenant_id != tenant_b.id

    spoof = authenticated_tenant_a_client.post(
        f"{BASE}/warehouses/",
        {**payload, "warehouse_code": "WH-SPOOF", "tenant_id": str(tenant_b.id)},
        format="json",
        HTTP_IDEMPOTENCY_KEY="warehouse-spoof",
    )
    assert spoof.status_code == 400
    assert not Warehouse.objects.filter(warehouse_code="WH-SPOOF").exists()


def test_unsupported_put_is_rejected(authenticated_tenant_a_client, tenant_a) -> None:
    own = warehouse(tenant_a.id, "WH-PUT")
    response = authenticated_tenant_a_client.put(f"{BASE}/warehouses/{own.id}/", {}, format="json")
    assert response.status_code in (403, 405)


def test_transport_helpers_validate_identity_idempotency_versions_and_domain_errors() -> None:
    actor = inventory_api._actor(SimpleNamespace(user=SimpleNamespace(id=42)))
    assert actor == inventory_api.uuid.uuid5(inventory_api.uuid.NAMESPACE_URL, "saraise-user:42")

    with pytest.raises(PermissionDenied):
        inventory_api._tenant(SimpleNamespace(tenant_id="not-a-uuid", user=SimpleNamespace()))
    with pytest.raises(PermissionDenied):
        inventory_api._actor(SimpleNamespace(user=SimpleNamespace(id=None)))

    request = SimpleNamespace(headers={"If-Match": 'W/"7"'})
    values: dict[str, object] = {}
    assert inventory_api._expected_version(request, values) == 7
    assert values == {}
    with pytest.raises(ValidationError):
        inventory_api._expected_version(SimpleNamespace(headers={}), {})
    with pytest.raises(ValidationError):
        inventory_api._expected_version(SimpleNamespace(headers={}), {"expected_version": 0})

    with pytest.raises(ValidationError):
        inventory_api._idempotency_key(SimpleNamespace(headers={"Idempotency-Key": ""}))
    assert inventory_api._idempotency_key(SimpleNamespace(headers={"Idempotency-Key": " command-1 "})) == "command-1"

    assert inventory_api._call(lambda: "ok") == "ok"
    with pytest.raises(inventory_api.Conflict):
        inventory_api._call(lambda: (_ for _ in ()).throw(IntegrityError("duplicate")))
    with pytest.raises(ValidationError):
        inventory_api._call(lambda: (_ for _ in ()).throw(DjangoValidationError({"field": ["bad"]})))
    with pytest.raises(PermissionDenied):
        inventory_api._call(lambda: (_ for _ in ()).throw(PermissionError("denied")))
    with pytest.raises(ValidationError):
        inventory_api._call(lambda: (_ for _ in ()).throw(KeyError("missing")))
    with pytest.raises(NotFound):
        inventory_api._call(lambda: (_ for _ in ()).throw(LookupError("missing")))
    with pytest.raises(inventory_api.Unprocessable):
        inventory_api._call(lambda: (_ for _ in ()).throw(ValueError("rule failed")))

    assert inventory_api._required_environment("development") == "development"
    with pytest.raises(NotFound):
        inventory_api._required_environment("")


def test_location_item_batch_and_serial_api_commands(authenticated_tenant_a_client, tenant_a) -> None:
    actor_id = uuid4()
    own_warehouse = warehouse(tenant_a.id, "WH-API")

    created_location = authenticated_tenant_a_client.post(
        f"{BASE}/locations/",
        {
            "warehouse_id": str(own_warehouse.id),
            "location_code": "BIN-01",
            "location_name": "Primary bin",
            "zone_type": "storage",
            "location_type": "bin",
            "pick_sequence": 10,
            "is_default": True,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="location-create-bin-01",
    )
    assert created_location.status_code == 201, created_location.content
    location_payload = created_location.json()["data"]

    patched_location = authenticated_tenant_a_client.patch(
        f"{BASE}/locations/{location_payload['id']}/",
        {"expected_version": location_payload["version"], "location_name": "Primary bin updated"},
        format="json",
    )
    assert patched_location.status_code == 200, patched_location.content
    assert patched_location.json()["data"]["location_name"] == "Primary bin updated"

    created_item = authenticated_tenant_a_client.post(
        f"{BASE}/items/",
        {
            "item_code": "BATCH-API",
            "item_name": "Batch API item",
            "base_uom": "EA",
            "tracking_mode": "batch",
            "valuation_method": "fifo",
            "reorder_point": "5.000000",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="item-create-batch-api",
    )
    assert created_item.status_code == 201, created_item.content
    item_payload = created_item.json()["data"]

    listed_items = authenticated_tenant_a_client.get(f"{BASE}/items/?tracking_mode=batch&search=batch")
    assert listed_items.status_code == 200
    assert [row["item_code"] for row in listed_items.json()["data"]] == ["BATCH-API"]

    patched_item = authenticated_tenant_a_client.patch(
        f"{BASE}/items/{item_payload['id']}/",
        {"expected_version": item_payload["version"], "brand": "BuildWorks"},
        format="json",
    )
    assert patched_item.status_code == 200, patched_item.content
    assert patched_item.json()["data"]["brand"] == "BuildWorks"

    StockBalance.objects.create(
        tenant_id=tenant_a.id,
        item_id=item_payload["id"],
        warehouse=own_warehouse,
        location_id=location_payload["id"],
        quantity_on_hand=Decimal("1.000000"),
        quantity_available=Decimal("1.000000"),
    )
    below_reorder = authenticated_tenant_a_client.get(f"{BASE}/items/?below_reorder=true")
    assert below_reorder.status_code == 200
    assert [row["item_code"] for row in below_reorder.json()["data"]] == ["BATCH-API"]

    batch = authenticated_tenant_a_client.post(
        f"{BASE}/batches/",
        {"item_id": item_payload["id"], "batch_number": "LOT-API", "supplier_batch_number": "SUP-1"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="batch-create-lot-api",
    )
    assert batch.status_code == 201, batch.content
    batch_id = batch.json()["data"]["id"]

    for command in ("activate", "quarantine", "release", "recall"):
        response = authenticated_tenant_a_client.post(
            f"{BASE}/batches/{batch_id}/{command}/",
            (
                {"expected_version": 1, "reason": "Recall verification"}
                if command == "recall"
                else {"expected_version": 1}
            ),
            format="json",
            HTTP_IDEMPOTENCY_KEY=f"batch-{command}-lot-api",
        )
        assert response.status_code == 200, response.content

    serial_item = item(
        tenant_a.id,
        actor_id,
        "SER-API",
        tracking_mode="serial",
        valuation_method="standard_cost",
        standard_cost="9.0000",
    )
    serial = authenticated_tenant_a_client.post(
        f"{BASE}/serial-numbers/",
        {"item_id": str(serial_item.id), "serial_number": "SERIAL-API", "manufacturer": "BuildWorks"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="serial-create-api",
    )
    assert serial.status_code == 201, serial.content
    serial_payload = serial.json()["data"]
    updated_serial = authenticated_tenant_a_client.patch(
        f"{BASE}/serial-numbers/{serial_payload['id']}/",
        {"expected_version": serial_payload["version"], "model_number": "M2"},
        format="json",
    )
    assert updated_serial.status_code == 200, updated_serial.content
    assert updated_serial.json()["data"]["model_number"] == "M2"
    traced_serial = authenticated_tenant_a_client.get(f"{BASE}/serial-numbers/{serial_payload['id']}/trace/")
    assert traced_serial.status_code == 200
    assert traced_serial.json()["data"] == []


def test_stock_entry_reservation_cycle_configuration_and_import_api(authenticated_tenant_a_client, tenant_a) -> None:
    actor_id = uuid4()
    own_warehouse = warehouse(tenant_a.id, "WH-FLOW")
    own_location = StorageLocationService.ensure_default_location(tenant_a.id, own_warehouse.id)
    own_item = item(tenant_a.id, actor_id, "SKU-FLOW")

    created_entry = authenticated_tenant_a_client.post(
        f"{BASE}/stock-entries/",
        {
            "entry_number": "REC-API",
            "entry_type": "receipt",
            "posting_at": timezone.now().isoformat(),
            "destination_warehouse_id": str(own_warehouse.id),
            "lines": [
                {
                    "line_number": 1,
                    "item_id": str(own_item.id),
                    "destination_location_id": str(own_location.id),
                    "quantity": "2.000000",
                    "uom": "EA",
                    "unit_cost": "3.0000",
                }
            ],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="stock-entry-create-api",
    )
    assert created_entry.status_code == 201, created_entry.content
    entry_payload = created_entry.json()["data"]

    listed_entries = authenticated_tenant_a_client.get(
        f"{BASE}/stock-entries/?warehouse_id={own_warehouse.id}&from=2024-01-01T00:00:00Z"
    )
    assert listed_entries.status_code == 200
    assert listed_entries.json()["data"][0]["entry_number"] == "REC-API"

    submitted = authenticated_tenant_a_client.post(
        f"{BASE}/stock-entries/{entry_payload['id']}/submit/",
        {"expected_version": entry_payload["version"]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="stock-entry-submit-api",
    )
    assert submitted.status_code == 200, submitted.content

    reservation = authenticated_tenant_a_client.post(
        f"{BASE}/reservations/",
        {
            "reservation_number": "RSV-API",
            "reference_module": "sales",
            "reference_type": "order",
            "reference_id": str(uuid4()),
            "item_id": str(own_item.id),
            "warehouse_id": str(own_warehouse.id),
            "location_id": str(own_location.id),
            "quantity": "1.000000",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="reservation-create-api",
    )
    assert reservation.status_code == 400, reservation.content
    assert reservation.json()["error"]["detail"]["non_field_errors"] == ["Reservation exceeds available stock."]

    cycle = authenticated_tenant_a_client.post(
        f"{BASE}/cycle-counts/",
        {
            "count_number": "CC-API",
            "warehouse_id": str(own_warehouse.id),
            "location_id": str(own_location.id),
            "count_type": "location",
            "scheduled_for": timezone.localdate().isoformat(),
            "lines": [{"line_number": 1, "item_id": str(own_item.id), "location_id": str(own_location.id)}],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="cycle-count-create-api",
    )
    assert cycle.status_code == 201, cycle.content
    cycle_payload = cycle.json()["data"]

    patched_cycle = authenticated_tenant_a_client.patch(
        f"{BASE}/cycle-counts/{cycle_payload['id']}/",
        {"expected_version": cycle_payload["version"], "assigned_to_id": str(uuid4())},
        format="json",
    )
    assert patched_cycle.status_code == 200, patched_cycle.content

    configuration = authenticated_tenant_a_client.get(f"{BASE}/configurations/development/")
    assert configuration.status_code == 200
    preview = authenticated_tenant_a_client.post(
        f"{BASE}/configurations/development/preview/",
        {"document": {"max_lines_per_entry": 25, "allow_negative_stock": True}},
        format="json",
    )
    assert preview.status_code == 200
    assert preview.json()["data"]["valid"] is True

    import_job = authenticated_tenant_a_client.post(
        f"{BASE}/imports/",
        {"resource_type": "items", "document_ref": "doc://inventory/items.csv", "row_count": 7},
        format="json",
        HTTP_IDEMPOTENCY_KEY="inventory-import-api",
    )
    assert import_job.status_code == 202, import_job.content
