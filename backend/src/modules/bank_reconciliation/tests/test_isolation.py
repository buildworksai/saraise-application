"""Explicit unchanged-state evidence for every bank-reconciliation aggregate."""

from __future__ import annotations

import uuid

import pytest
from rest_framework.permissions import IsAuthenticated

from .. import api
from ..models import (
    BankAccount,
    BankStatement,
    BankStatementImport,
    BankTransaction,
    MatchingRule,
    ReconciliationMatch,
    ReconciliationMatchLine,
    ReconciliationSession,
)
from .factories import (
    BankAccountFactory,
    BankStatementFactory,
    BankStatementImportFactory,
    BankTransactionFactory,
    MatchingRuleFactory,
    ReconciliationMatchFactory,
    ReconciliationMatchLineFactory,
    ReconciliationSessionFactory,
)

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db


def _tenant_record(factory: object, tenant_id: uuid.UUID) -> object:
    if factory is BankAccountFactory or factory is MatchingRuleFactory:
        return factory(tenant_id=tenant_id)
    if factory is BankStatementFactory or factory is BankStatementImportFactory:
        return factory(bank_account__tenant_id=tenant_id)
    if factory is BankTransactionFactory:
        return factory(bank_statement__bank_account__tenant_id=tenant_id)
    if factory is ReconciliationSessionFactory:
        return factory(bank_statement__bank_account__tenant_id=tenant_id)
    if factory is ReconciliationMatchFactory:
        return factory(reconciliation__bank_statement__bank_account__tenant_id=tenant_id)
    raise AssertionError("Unsupported isolation factory")


@pytest.fixture(autouse=True)
def isolate_access_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api.ActionAccessMixin, "get_permissions", lambda self: [IsAuthenticated()])


@pytest.mark.parametrize(
    ("factory", "model", "endpoint"),
    [
        (BankAccountFactory, BankAccount, "accounts"),
        (BankStatementFactory, BankStatement, "statements"),
        (BankTransactionFactory, BankTransaction, "transactions"),
        (BankStatementImportFactory, BankStatementImport, "imports"),
        (MatchingRuleFactory, MatchingRule, "rules"),
        (ReconciliationSessionFactory, ReconciliationSession, "reconciliations"),
        (ReconciliationMatchFactory, ReconciliationMatch, "matches"),
    ],
)
def test_cross_tenant_lists_and_details_never_disclose_rows(
    factory: object, model: object, endpoint: str, tenant_a_client: object, tenant_a: object, tenant_b: object
) -> None:
    own = _tenant_record(factory, tenant_a.id)
    foreign = _tenant_record(factory, tenant_b.id)
    response = tenant_a_client.get(f"/api/v2/bank-reconciliation/{endpoint}/")
    assert response.status_code in (200, 405)
    if response.status_code == 200:
        rendered = response.content.decode()
        assert str(foreign.id) not in rendered
        assert str(own.id) in rendered
    assert tenant_a_client.get(f"/api/v2/bank-reconciliation/{endpoint}/{foreign.id}/").status_code in (404, 405)


def test_related_identifier_attack_is_rejected_without_mutation(
    tenant_a_client: object, tenant_a: object, tenant_b: object
) -> None:
    foreign = BankAccountFactory(tenant_id=tenant_b.id)
    before = list(BankStatement.objects.values())
    response = tenant_a_client.post(
        "/api/v2/bank-reconciliation/statements/",
        {
            "bank_account_id": str(foreign.id),
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "opening_balance": "0.0000",
            "closing_balance": "0.0000",
        },
        format="json",
    )
    assert response.status_code == 404
    assert list(BankStatement.objects.values()) == before


def test_match_line_manager_retains_tenant_boundary() -> None:
    line = ReconciliationMatchLineFactory()
    assert ReconciliationMatchLine.objects.for_tenant(line.tenant_id).get(pk=line.pk) == line
    assert not ReconciliationMatchLine.objects.for_tenant(uuid.uuid4()).filter(pk=line.pk).exists()
