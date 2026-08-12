from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from rest_framework import status

from src.core.access import AccessDecision, AccessDecisionPipeline, AccessReasonCode
from src.modules.sales_management.api import (
    ConfigurationViewSet,
    CustomerViewSet,
    DeliveryNoteViewSet,
    QuotationViewSet,
    SalesOrderViewSet,
)
from src.modules.sales_management.models import Customer
from src.modules.sales_management.services import DeliveryNoteService
from src.modules.sales_management.tests.conftest import API, customer, order_with_line, quote_payload, unwrap

pytestmark = pytest.mark.django_db


def test_unauthenticated_request_returns_401(api_client):
    response = api_client.get(f"{API}/customers/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_policy_denial_returns_403(authenticated_tenant_a_client, monkeypatch):
    def deny(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision.deny(AccessReasonCode.POLICY_DENIED, "denied", tenant_id=uuid.UUID(str(tenant_id)))

    monkeypatch.setattr(AccessDecisionPipeline, "decide", deny)
    response = authenticated_tenant_a_client.get(f"{API}/customers/")
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_customer_v2_crud_envelopes_idempotency_and_concurrency(authenticated_tenant_a_client, tenant_a):
    client = authenticated_tenant_a_client
    missing_key = client.post(f"{API}/customers/", {"customer_code": "C-1", "customer_name": "Buyer"}, format="json")
    assert missing_key.status_code == 400
    created = client.post(
        f"{API}/customers/",
        {"tenant_id": str(uuid.uuid4()), "customer_code": "C-1", "customer_name": "Buyer"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-customer-1",
        HTTP_X_CORRELATION_ID=str(uuid.uuid4()),
    )
    assert created.status_code == 201
    body = created.json()
    assert set(body) == {"data", "meta"}
    assert body["data"]["tenant_id"] == str(tenant_a.id)
    assert body["meta"]["correlation_id"]
    pk = body["data"]["id"]
    listed = client.get(f"{API}/customers/?search=Buyer&page_size=1")
    assert listed.status_code == 200 and unwrap(listed)[0]["id"] == pk
    assert listed.json()["meta"]["pagination"]["page_size"] == 1
    active_list = client.get(f"{API}/customers/?is_active=true&page_size=100")
    assert active_list.status_code == 200 and unwrap(active_list)[0]["id"] == pk
    stale = client.patch(f"{API}/customers/{pk}/", {"customer_name": "Stale", "expected_version": 99}, format="json")
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "CONCURRENT_MODIFICATION"
    updated = client.patch(f"{API}/customers/{pk}/", {"customer_name": "Updated", "expected_version": 1}, format="json")
    assert updated.status_code == 200 and unwrap(updated)["lock_version"] == 2
    deleted = client.delete(f"{API}/customers/{pk}/", HTTP_IF_MATCH='W/"2"')
    assert deleted.status_code == 200 and unwrap(deleted)["deleted_at"]
    assert Customer.objects.get(pk=pk).deleted_at is not None


def test_quotation_preview_create_and_commands(authenticated_tenant_a_client, tenant_a):
    buyer = customer(tenant_a.id)
    payload = quote_payload(buyer.pk)
    preview = authenticated_tenant_a_client.post(f"{API}/quotations/preview/", payload, format="json")
    assert preview.status_code == 200 and unwrap(preview)["total_amount"] == "19.80"
    created = authenticated_tenant_a_client.post(
        f"{API}/quotations/", payload, format="json", HTTP_IDEMPOTENCY_KEY="api-q-create"
    )
    assert created.status_code == 201
    quote_id = unwrap(created)["id"]
    sent = authenticated_tenant_a_client.post(
        f"{API}/quotations/{quote_id}/commands/send/", {}, format="json", HTTP_IDEMPOTENCY_KEY="api-q-send"
    )
    assert sent.status_code == 200 and unwrap(sent)["status"] == "sent"


def test_configuration_api_preview_apply_versions_export(authenticated_tenant_a_client):
    current = authenticated_tenant_a_client.get(f"{API}/configuration/")
    assert current.status_code == 200
    version = unwrap(current)["lock_version"]
    preview = authenticated_tenant_a_client.post(
        f"{API}/configuration/preview/", {"quotation_validity_days": 60}, format="json"
    )
    assert preview.status_code == 200 and unwrap(preview)["valid"]
    changed = authenticated_tenant_a_client.put(
        f"{API}/configuration/",
        {"quotation_validity_days": 60, "expected_version": version, "reason": "commercial policy"},
        format="json",
    )
    assert changed.status_code == 200 and unwrap(changed)["quotation_validity_days"] == 60
    versions = authenticated_tenant_a_client.get(f"{API}/configuration/versions/")
    assert versions.status_code == 200 and len(unwrap(versions)) == 2
    exported = authenticated_tenant_a_client.get(f"{API}/configuration/export/")
    assert exported.status_code == 200 and unwrap(exported)["schema_version"] == 1


def test_unapproved_put_and_missing_action_metadata_fail_closed(authenticated_tenant_a_client, tenant_a):
    row = customer(tenant_a.id)
    assert authenticated_tenant_a_client.put(f"{API}/customers/{row.pk}/", {}, format="json").status_code == 405
    assert "update" not in CustomerViewSet.action_permissions
    for viewset in (CustomerViewSet, QuotationViewSet, SalesOrderViewSet, DeliveryNoteViewSet, ConfigurationViewSet):
        assert viewset.required_entitlement == "sales_management"
        assert all(permission.startswith("sales.") for permission in viewset.action_permissions.values())


def test_sales_order_api_create_update_filters_and_command_errors(authenticated_tenant_a_client, tenant_a):
    buyer = customer(tenant_a.id, code="CUST-API-ORDER", customer_name="Order API Buyer")
    payload = {
        "order_date": "2026-02-01",
        "delivery_date": "2026-02-03",
        "customer": str(buyer.pk),
        "currency": "USD",
        "lines": [
            {
                "line_number": 1,
                "item_code": "API-ITEM",
                "item_name": "API item",
                "quantity": "2.0000",
                "unit_price": "15.0000",
                "discount_percent": "0.00",
                "tax_amount": "0.00",
            }
        ],
    }

    created = authenticated_tenant_a_client.post(
        f"{API}/sales-orders/", payload, format="json", HTTP_IDEMPOTENCY_KEY="api-order-create"
    )
    assert created.status_code == status.HTTP_201_CREATED
    order_id = unwrap(created)["id"]

    listed = authenticated_tenant_a_client.get(
        f"{API}/sales-orders/?search=Order API Buyer&status=draft&date_from=2026-02-01&date_to=2026-02-28"
    )
    assert listed.status_code == status.HTTP_200_OK
    assert [row["id"] for row in unwrap(listed)] == [order_id]

    updated_payload = {
        **payload,
        "notes": "priority",
        "expected_version": unwrap(created)["lock_version"],
        "lines": [{**payload["lines"][0], "quantity": "3.0000"}],
    }
    updated = authenticated_tenant_a_client.patch(f"{API}/sales-orders/{order_id}/", updated_payload, format="json")
    assert updated.status_code == status.HTTP_200_OK
    assert unwrap(updated)["total_amount"] == "45.00"

    missing_reason = authenticated_tenant_a_client.post(
        f"{API}/sales-orders/{order_id}/commands/cancel/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-order-cancel-missing-reason",
    )
    assert missing_reason.status_code == status.HTTP_400_BAD_REQUEST
    assert "reason" in missing_reason.json()["error"]["detail"]

    cancelled = authenticated_tenant_a_client.post(
        f"{API}/sales-orders/{order_id}/commands/cancel/",
        {"reason": "customer requested"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-order-cancel",
    )
    assert cancelled.status_code == status.HTTP_200_OK
    assert unwrap(cancelled)["status"] == "cancelled"


def test_delivery_note_api_crud_commands_and_summary(authenticated_tenant_a_client, tenant_a):
    order, line = order_with_line(tenant_a.id, status="confirmed")
    create_payload = {
        "delivery_date": "2026-03-01",
        "sales_order": str(order.pk),
        "carrier_name": "Carrier",
        "tracking_number": "DEL-TRACK-1",
        "lines": [
            {
                "line_number": 1,
                "sales_order_line": str(line.pk),
                "quantity_delivered": "1.0000",
            }
        ],
    }

    created = authenticated_tenant_a_client.post(
        f"{API}/delivery-notes/",
        create_payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-delivery-create",
        HTTP_X_CORRELATION_ID=str(uuid.uuid4()),
    )
    assert created.status_code == status.HTTP_201_CREATED
    note_id = unwrap(created)["id"]

    listed = authenticated_tenant_a_client.get(
        f"{API}/delivery-notes/?search=DEL-TRACK-1&status=draft&date_from=2026-03-01&date_to=2026-03-31"
    )
    assert listed.status_code == status.HTTP_200_OK
    assert [row["id"] for row in unwrap(listed)] == [note_id]

    patched = authenticated_tenant_a_client.patch(
        f"{API}/delivery-notes/{note_id}/",
        {
            **create_payload,
            "delivery_date": "2026-03-02",
            "tracking_number": "DEL-TRACK-2",
            "expected_version": unwrap(created)["lock_version"],
        },
        format="json",
    )
    assert patched.status_code == status.HTTP_200_OK
    assert unwrap(patched)["tracking_number"] == "DEL-TRACK-2"

    completed = authenticated_tenant_a_client.post(
        f"{API}/delivery-notes/{note_id}/commands/complete/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-delivery-complete",
    )
    assert completed.status_code == status.HTTP_200_OK
    assert unwrap(completed)["status"] == "completed"

    summary = authenticated_tenant_a_client.get(f"{API}/summary/")
    assert summary.status_code == status.HTTP_200_OK
    assert unwrap(summary)["confirmed_orders"] == 1
    assert unwrap(summary)["recent_deliveries"][0]["status"] == "completed"

    second_order, second_line = order_with_line(
        tenant_a.id, code="SO-API-DEL-CANCEL", customer_obj=order.customer, status="confirmed"
    )
    second_note = DeliveryNoteService.create_delivery_note(
        tenant_a.id,
        uuid.uuid4(),
        uuid.uuid4(),
        "api-delivery-second",
        {
            "delivery_date": date(2026, 3, 3),
            "sales_order_id": second_order.pk,
            "lines": [{"line_number": 1, "sales_order_line_id": second_line.pk, "quantity_delivered": Decimal("1")}],
        },
    )
    cancelled = authenticated_tenant_a_client.post(
        f"{API}/delivery-notes/{second_note.pk}/commands/cancel/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-delivery-cancel",
    )
    assert cancelled.status_code == status.HTTP_200_OK
    assert unwrap(cancelled)["status"] == "cancelled"


def test_configuration_api_version_detail_rollback_import_and_capabilities(authenticated_tenant_a_client, monkeypatch):
    current = authenticated_tenant_a_client.get(f"{API}/configuration/")
    changed = authenticated_tenant_a_client.put(
        f"{API}/configuration/",
        {
            "proposed_values": {"quotation_validity_days": 75},
            "expected_version": unwrap(current)["lock_version"],
            "reason": "seasonal terms",
        },
        format="json",
    )
    assert changed.status_code == status.HTTP_200_OK
    assert unwrap(changed)["version"] == 2

    version_detail = authenticated_tenant_a_client.get(f"{API}/configuration/versions/1/")
    assert version_detail.status_code == status.HTTP_200_OK
    assert unwrap(version_detail)["version"] == 1

    rollback = authenticated_tenant_a_client.post(
        f"{API}/configuration/rollback/",
        {"target_version": 1, "expected_version": unwrap(changed)["lock_version"], "reason": "restore"},
        format="json",
    )
    assert rollback.status_code == status.HTTP_200_OK
    assert unwrap(rollback)["quotation_validity_days"] == 30

    exported = authenticated_tenant_a_client.get(f"{API}/configuration/export/")
    imported = authenticated_tenant_a_client.post(
        f"{API}/configuration/import/",
        {
            "document": unwrap(exported),
            "expected_version": unwrap(rollback)["lock_version"],
            "dry_run": True,
            "reason": "validate portable configuration",
        },
        format="json",
    )
    assert imported.status_code == status.HTTP_200_OK
    assert unwrap(imported)["valid"] is True

    class Registry:
        def capabilities(self, tenant_id):
            return []

    monkeypatch.setattr("src.modules.sales_management.services.get_integration_registry", lambda: Registry())
    capabilities = authenticated_tenant_a_client.get(f"{API}/capabilities/")
    assert capabilities.status_code == status.HTTP_200_OK
    assert unwrap(capabilities) == []
