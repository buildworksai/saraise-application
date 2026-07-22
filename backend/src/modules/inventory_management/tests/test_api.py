"""Governed v2 inventory API contract tests."""

from __future__ import annotations

from uuid import UUID

import pytest

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.modules.inventory_management.models import Warehouse

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


def test_missing_authentication_returns_401(api_client) -> None:
    response = api_client.get(f"{BASE}/warehouses/")
    assert response.status_code == 401
    problem = response.json()["error"]
    assert problem["code"]
    assert problem["correlation_id"]


def test_list_uses_governed_envelope_and_pagination(authenticated_tenant_a_client, tenant_a) -> None:
    own = warehouse(tenant_a.id)
    response = authenticated_tenant_a_client.get(f"{BASE}/warehouses/?page_size=1&ordering=warehouse_code")
    assert response.status_code == 200
    payload = response.json()
    assert [row["id"] for row in payload["data"]] == [str(own.id)]
    assert payload["meta"]["correlation_id"]
    assert payload["meta"]["pagination"]["page_size"] == 1


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
