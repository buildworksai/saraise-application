from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework.permissions import IsAuthenticated

from .. import api
from .factories import BankAccountFactory

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db
BASE = "/api/v2/bank-reconciliation"


@pytest.fixture(autouse=True)
def isolate_access_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api.ActionAccessMixin, "get_permissions", lambda self: [IsAuthenticated()])


def test_accounts_are_paginated_enveloped_and_masked(
    tenant_a: object, tenant_a_user: object, tenant_a_client: object
) -> None:
    account = BankAccountFactory(tenant_id=tenant_a.id, account_number="SENSITIVE-1234")
    response = tenant_a_client.get(f"{BASE}/accounts/")
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["pagination"]["count"] == 1
    assert body["data"][0]["masked_account_number"].endswith("1234")
    assert "SENSITIVE" not in response.content.decode()
    assert body["data"][0]["id"] == str(account.id)


def test_account_mutations_delegate_to_services(tenant_a_client: object) -> None:
    payload = {
        "account_number": "ACC-1000",
        "bank_name": "Bank",
        "account_name": "Operating",
        "account_type": "checking",
        "currency": "USD",
        "opening_balance": "0.0000",
    }
    with patch.object(api.BankAccountService, "create", wraps=api.BankAccountService.create) as service:
        response = tenant_a_client.post(f"{BASE}/accounts/", payload, format="json")
    assert response.status_code == 201
    service.assert_called_once()


def test_put_and_unauthenticated_requests_fail_closed(
    api_client: object, tenant_a_client: object, tenant_a: object
) -> None:
    account = BankAccountFactory(tenant_id=tenant_a.id)
    assert api_client.get(f"{BASE}/accounts/").status_code == 401
    assert tenant_a_client.put(f"{BASE}/accounts/{account.id}/", {}, format="json").status_code == 405


def test_cross_tenant_detail_is_not_found(tenant_a_client: object, tenant_b: object) -> None:
    foreign = BankAccountFactory(tenant_id=tenant_b.id)
    assert tenant_a_client.get(f"{BASE}/accounts/{foreign.id}/").status_code == 404
