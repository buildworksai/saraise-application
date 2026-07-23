from __future__ import annotations

import uuid

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
from src.modules.sales_management.tests.conftest import API, customer, quote_payload, unwrap

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
