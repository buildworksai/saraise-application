from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from src.core.async_jobs.models import OutboxEvent

from ..models import BankAccount, BankTransaction
from ..services import BankAccountService, BankReconciliationError, ReconciliationService, StatementService
from .factories import BankAccountFactory, BankStatementFactory, BankTransactionFactory

pytestmark = pytest.mark.django_db


def account_payload(number: str = "ACC-001") -> dict[str, object]:
    return {
        "account_number": number,
        "bank_name": "Test Bank",
        "account_name": "Operating",
        "account_type": "checking",
        "currency": "usd",
        "opening_balance": Decimal("0.0000"),
    }


def test_account_service_is_tenant_first_masks_and_emits_outbox() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    value = BankAccountService.create(tenant, actor, account_payload())
    assert value.tenant_id == tenant
    assert value.currency == "USD"
    assert (
        OutboxEvent.objects.for_tenant(tenant)
        .filter(aggregate_id=value.id, event_type="bank_reconciliation.account.created")
        .exists()
    )
    with pytest.raises(BankReconciliationError):
        BankAccountService.get(uuid.uuid4(), value.id)


def test_account_archive_is_non_destructive_and_idempotent() -> None:
    account = BankAccountFactory()
    BankAccountService.archive(account.tenant_id, account.id, account.created_by_id)
    BankAccountService.archive(account.tenant_id, account.id, account.created_by_id)
    account.refresh_from_db()
    assert not account.is_active and account.archived_at is not None
    assert BankAccount.objects.filter(pk=account.pk).exists()


def test_manual_statement_and_transactions_have_authoritative_arithmetic() -> None:
    account = BankAccountFactory()
    actor = uuid.uuid4()
    statement = StatementService.create_manual_statement(
        account.tenant_id,
        actor,
        {
            "bank_account_id": account.id,
            "statement_reference": "JAN",
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "opening_balance": "100.0000",
            "closing_balance": "125.0000",
            "transactions": [{"transaction_date": date(2026, 1, 5), "description": "Deposit", "amount": "25.0000"}],
        },
    )
    assert statement.transaction_total == Decimal("25.0000")
    assert statement.calculated_closing_balance == Decimal("125.0000")
    assert statement.balance_variance == Decimal("0.0000")


def test_failed_cross_tenant_transaction_update_leaves_row_unchanged() -> None:
    value = BankTransactionFactory()
    before = BankTransaction.objects.values().get(pk=value.pk)
    with pytest.raises(BankReconciliationError):
        StatementService.update_manual_transaction(uuid.uuid4(), value.id, uuid.uuid4(), {"amount": "999.0000"})
    assert BankTransaction.objects.values().get(pk=value.pk) == before


def test_reconciliation_creation_is_idempotent_and_tenant_bound() -> None:
    statement = BankStatementFactory()
    actor, key = uuid.uuid4(), "reconcile-january"
    payload = {
        "bank_statement_id": statement.id,
        "reconciliation_date": statement.period_end,
        "ledger_balance": statement.closing_balance,
        "tolerance": "0.0000",
    }
    first = ReconciliationService.create(statement.tenant_id, actor, payload, key)
    second = ReconciliationService.create(statement.tenant_id, actor, payload, key)
    assert first.id == second.id
    with pytest.raises(BankReconciliationError):
        ReconciliationService.get(uuid.uuid4(), first.id)
