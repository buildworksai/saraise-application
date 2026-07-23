from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from src.core.access import AccessDecision, AccessDecisionPipeline, AccessReasonCode
from src.modules.sales_management.models import Customer, SalesOrder, SalesOrderLine

pytest_plugins = ["src.core.testing"]

API = "/api/v2/sales-management"


@pytest.fixture(autouse=True)
def authorize_through_access_contract(monkeypatch):
    """Replace external policy/entitlement dependencies, not RequiresAccess."""

    def decide(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        tenant = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
        return AccessDecision(True, AccessReasonCode.ALLOW, "test policy allow", tenant_id=tenant)

    monkeypatch.setattr(AccessDecisionPipeline, "decide", decide)


@pytest.fixture
def actor_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def correlation_id() -> uuid.UUID:
    return uuid.uuid4()


def customer(tenant_id, *, code="CUST-001", actor=None, **values):
    actor = actor or uuid.uuid4()
    return Customer.objects.create(
        tenant_id=tenant_id,
        customer_code=code,
        customer_name=values.pop("customer_name", f"Customer {code}"),
        created_by=actor,
        updated_by=actor,
        **values,
    )


def order_with_line(tenant_id, *, code="SO-001", customer_obj=None, actor=None, status="draft"):
    actor = actor or uuid.uuid4()
    customer_obj = customer_obj or customer(tenant_id, actor=actor)
    order = SalesOrder.objects.create(
        tenant_id=tenant_id,
        order_number=code,
        order_date=date(2026, 1, 1),
        customer=customer_obj,
        currency="USD",
        subtotal_amount=Decimal("20.00"),
        total_amount=Decimal("20.00"),
        status=status,
        created_by=actor,
        updated_by=actor,
    )
    line = SalesOrderLine.objects.create(
        tenant_id=tenant_id,
        sales_order=order,
        line_number=1,
        item_code="ITEM-1",
        item_name="Item one",
        quantity=Decimal("2"),
        unit_price=Decimal("10"),
        gross_amount=Decimal("20"),
        total_price=Decimal("20"),
        created_by=actor,
        updated_by=actor,
    )
    return order, line


def quote_payload(customer_id):
    return {
        "quotation_date": "2026-01-01",
        "valid_until": "2026-01-31",
        "customer": str(customer_id),
        "currency": "USD",
        "lines": [
            {
                "line_number": 1,
                "item_code": "ITEM-1",
                "item_name": "Item one",
                "quantity": "2.0000",
                "unit_price": "10.0000",
                "discount_percent": "10.00",
                "tax_amount": "1.80",
            }
        ],
    }


def service_quote_payload(customer_id):
    payload = quote_payload(customer_id)
    payload["customer_id"] = uuid.UUID(payload.pop("customer"))
    payload["quotation_date"] = date.fromisoformat(payload["quotation_date"])
    payload["valid_until"] = date.fromisoformat(payload["valid_until"])
    return payload


def unwrap(response):
    payload = response.json()
    return payload["data"]
