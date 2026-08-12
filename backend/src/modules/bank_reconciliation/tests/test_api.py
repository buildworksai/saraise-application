from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated

from .. import api
from .factories import (
    BankAccountFactory,
    BankStatementFactory,
    BankStatementImportFactory,
    BankTransactionFactory,
    MatchingRuleFactory,
    ReconciliationMatchFactory,
    ReconciliationSessionFactory,
)

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db
BASE = "/api/v2/bank-reconciliation"


@pytest.fixture(autouse=True)
def isolate_access_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api.ActionAccessMixin, "get_permissions", lambda self: [IsAuthenticated()])


def response_data(response: object) -> dict[str, object]:
    body = response.json()
    return body.get("data", body)


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


def test_statement_and_transaction_actions_use_tenant_filters_and_services(tenant_a: object, tenant_a_client: object):
    account = BankAccountFactory(tenant_id=tenant_a.id)
    statement = BankStatementFactory(
        tenant_id=tenant_a.id,
        bank_account=account,
        statement_reference="JAN-API",
        opening_balance=Decimal("100.0000"),
        closing_balance=Decimal("100.0000"),
        transaction_total=Decimal("0.0000"),
        calculated_closing_balance=Decimal("100.0000"),
    )

    listed = tenant_a_client.get(f"{BASE}/statements/?account={account.id}&has_variance=false")
    invalid = tenant_a_client.get(f"{BASE}/statements/?account=not-a-uuid")
    created = tenant_a_client.post(
        f"{BASE}/statements/{statement.id}/transactions/",
        {
            "transaction_date": "2026-01-10",
            "description": "Deposit API",
            "amount": "15.0000",
            "reference_number": "DEP-API",
        },
        format="json",
    )

    assert listed.status_code == 200
    assert listed.json()["meta"]["pagination"]["count"] == 1
    assert invalid.status_code == 400
    assert created.status_code == 201

    transaction_id = response_data(created)["id"]
    filtered = tenant_a_client.get(f"{BASE}/transactions/?statement={statement.id}&search=Deposit&ordering=amount")
    updated = tenant_a_client.patch(
        f"{BASE}/transactions/{transaction_id}/",
        {"description": "Deposit API updated"},
        format="json",
    )
    excluded = tenant_a_client.post(
        f"{BASE}/transactions/{transaction_id}/exclude/",
        {"reason": "not ledger activity"},
        format="json",
    )
    restored = tenant_a_client.post(f"{BASE}/transactions/{transaction_id}/restore/", {}, format="json")

    assert filtered.status_code == 200
    assert filtered.json()["meta"]["pagination"]["count"] == 1
    assert updated.status_code == 200
    assert response_data(updated)["description"] == "Deposit API updated"
    assert excluded.status_code == 200
    assert response_data(excluded)["match_status"] == "excluded"
    assert restored.status_code == 200
    assert response_data(restored)["match_status"] == "unmatched"


def test_import_and_matching_rule_api_actions(tenant_a: object, tenant_a_client: object):
    account = BankAccountFactory(tenant_id=tenant_a.id)
    statement_import = BankStatementImportFactory(tenant_id=tenant_a.id, bank_account=account, status="failed")
    imports = tenant_a_client.get(f"{BASE}/imports/?account={account.id}&file_format=csv&status=failed")
    retry = tenant_a_client.post(
        f"{BASE}/imports/{statement_import.id}/retry/",
        {"idempotency_key": "api-retry-import"},
        format="json",
    )
    cancel = tenant_a_client.post(
        f"{BASE}/imports/{statement_import.id}/cancel/",
        {"reason": "operator cancelled"},
        format="json",
    )

    assert imports.status_code == 200
    assert imports.json()["meta"]["pagination"]["count"] == 1
    assert retry.status_code == 202
    retry_body = response_data(retry)
    assert retry_body["import"]["status"] == "pending"
    assert cancel.status_code == 200
    assert response_data(cancel)["status"] == "cancelled"

    create_rule = tenant_a_client.post(
        f"{BASE}/rules/",
        {
            "name": "API exact",
            "rule_type": "exact",
            "priority": 44,
            "configuration": {"date_window_days": 2},
            "minimum_score": "1.0000",
        },
        format="json",
    )
    assert create_rule.status_code == 201
    rule_id = response_data(create_rule)["id"]

    patched = tenant_a_client.patch(
        f"{BASE}/rules/{rule_id}/",
        {"description": "updated by api", "minimum_score": "0.9500"},
        format="json",
    )
    deactivated = tenant_a_client.post(f"{BASE}/rules/{rule_id}/deactivate/", {}, format="json")
    activated = tenant_a_client.post(f"{BASE}/rules/{rule_id}/activate/", {}, format="json")
    deleted = tenant_a_client.delete(f"{BASE}/rules/{rule_id}/")

    assert patched.status_code == 200
    assert response_data(patched)["description"] == "updated by api"
    assert deactivated.status_code == 200
    assert response_data(deactivated)["is_active"] is False
    assert activated.status_code == 200
    assert response_data(activated)["is_active"] is True
    assert deleted.status_code == 204


def test_reconciliation_and_match_api_actions(tenant_a: object, tenant_a_client: object):
    account = BankAccountFactory(tenant_id=tenant_a.id)
    statement = BankStatementFactory(tenant_id=tenant_a.id, bank_account=account, closing_balance=Decimal("125.0000"))
    transaction = BankTransactionFactory(tenant_id=tenant_a.id, bank_statement=statement, amount=Decimal("25.0000"))

    created = tenant_a_client.post(
        f"{BASE}/reconciliations/",
        {
            "bank_statement": str(statement.id),
            "reconciliation_date": "2026-01-31",
            "ledger_balance": "125.0000",
            "tolerance": "0.0000",
            "idempotency_key": "api-reconciliation-create",
        },
        format="json",
    )
    assert created.status_code == 201
    reconciliation_id = response_data(created)["id"]

    started = tenant_a_client.post(
        f"{BASE}/reconciliations/{reconciliation_id}/start/",
        {"idempotency_key": "api-reconciliation-start"},
        format="json",
    )
    match = tenant_a_client.post(
        f"{BASE}/reconciliations/{reconciliation_id}/matches/",
        {
            "lines": [
                {"side": "bank", "bank_transaction_id": str(transaction.id), "allocated_amount": "25.0000"},
                {
                    "side": "ledger",
                    "ledger_entry_id": str(uuid.uuid4()),
                    "ledger_entry_type": "payment",
                    "allocated_amount": "25.0000",
                },
            ]
        },
        format="json",
    )

    assert started.status_code == 200
    assert match.status_code == 201
    match_id = response_data(match)["id"]

    confirmed = tenant_a_client.post(
        f"{BASE}/matches/{match_id}/confirm/",
        {"idempotency_key": "api-match-confirm"},
        format="json",
    )
    report_not_ready = tenant_a_client.get(f"{BASE}/reconciliations/{reconciliation_id}/report/?report_format=xlsx")

    assert confirmed.status_code == 200
    assert response_data(confirmed)["status"] == "confirmed"
    assert report_not_ready.status_code == 400


def test_reconciliation_report_streams_finalized_csv(tenant_a: object, tenant_a_client: object):
    account = BankAccountFactory(tenant_id=tenant_a.id)
    statement = BankStatementFactory(tenant_id=tenant_a.id, bank_account=account)
    reconciliation = ReconciliationSessionFactory(
        tenant_id=tenant_a.id,
        bank_account=account,
        bank_statement=statement,
        status="finalized",
        reviewed_by_id=uuid.uuid4(),
        finalized_by_id=uuid.uuid4(),
        finalized_at=timezone.now(),
    )
    match = ReconciliationMatchFactory(tenant_id=tenant_a.id, reconciliation=reconciliation, status="rejected")
    MatchingRuleFactory(tenant_id=tenant_a.id, priority=77)

    response = tenant_a_client.get(f"{BASE}/reconciliations/{reconciliation.id}/report/?report_format=csv")
    assert response.status_code == 200
    content = b"".join(response.streaming_content)
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert response["Content-Disposition"].endswith(f'{reconciliation.id}.csv"')
    assert str(match.id).encode("utf-8") not in content
    assert b"reconciliation_id,status,statement_balance" in content
