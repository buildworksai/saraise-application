from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from ..models import account_number_digest, normalize_account_number
from .factories import (
    BankAccountFactory,
    BankStatementFactory,
    BankStatementImportFactory,
    BankTransactionFactory,
    ReconciliationSessionFactory,
)

pytestmark = pytest.mark.django_db


def test_account_normalizes_hashes_and_never_renders_raw_identifier() -> None:
    tenant = uuid.uuid4()
    account = BankAccountFactory(tenant_id=tenant, account_number=" gb00-1234 5678 ")
    assert normalize_account_number(account.account_number) == "GB0012345678"
    assert account.account_number_hash == account_number_digest(tenant, account.account_number)
    assert account.account_number_last4 == "5678"
    assert account.masked_account_number == "••••5678"
    assert "GB00" not in str(account)


def test_same_account_allowed_across_tenants_but_not_within_tenant() -> None:
    first = BankAccountFactory(account_number="ABCD-1234")
    BankAccountFactory(tenant_id=uuid.uuid4(), account_number="ABCD 1234")
    with pytest.raises((IntegrityError, ValidationError)):
        BankAccountFactory(tenant_id=first.tenant_id, account_number="ABCD 1234")


def test_related_models_reject_cross_tenant_relationships() -> None:
    account = BankAccountFactory()
    statement = BankStatementFactory.build(tenant_id=uuid.uuid4(), bank_account=account)
    with pytest.raises(ValidationError):
        statement.full_clean()
    statement = BankStatementFactory()
    value = BankTransactionFactory.build(tenant_id=uuid.uuid4(), bank_statement=statement)
    with pytest.raises(ValidationError):
        value.full_clean()


def test_statement_period_and_reconciliation_evidence_are_guarded() -> None:
    statement = BankStatementFactory.build(
        period_start=date(2026, 2, 1), period_end=date(2026, 1, 1), statement_date=date(2026, 1, 1)
    )
    with pytest.raises(ValidationError):
        statement.full_clean()
    session = ReconciliationSessionFactory.build(status="finalized", finalized_by_id=None, finalized_at=None)
    with pytest.raises(ValidationError):
        session.full_clean()


def test_import_row_counts_are_bounded() -> None:
    value = BankStatementImportFactory.build(rows_received=1, rows_imported=1, rows_rejected=1)
    with pytest.raises(ValidationError):
        value.full_clean()


def test_transaction_type_is_derived_from_signed_amount() -> None:
    value = BankTransactionFactory(amount=Decimal("-10.0000"), transaction_type="credit")
    assert value.transaction_type == "debit"
