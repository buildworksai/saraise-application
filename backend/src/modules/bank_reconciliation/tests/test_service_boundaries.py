from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from ..services import (
    BankReconciliationError,
    ReconciliationService,
    StatementImportService,
    StatementService,
    _decimal,
    _pdf_document,
    _text,
    _uuid,
)
from .factories import BankStatementFactory, BankStatementImportFactory, BankTransactionFactory

pytestmark = pytest.mark.django_db


def test_service_value_guards_reject_invalid_uuid_text_and_decimal_inputs() -> None:
    assert _uuid(uuid.UUID(int=1), "tenant_id") == uuid.UUID(int=1)
    with pytest.raises(BankReconciliationError) as bad_uuid:
        _uuid("not-a-uuid", "tenant_id")
    assert bad_uuid.value.error_code == "INVALID_UUID"

    assert _text("  ok  ", "name", 8) == "ok"
    with pytest.raises(BankReconciliationError):
        _text("", "name", 8)
    with pytest.raises(BankReconciliationError):
        _text("too-long", "name", 3)

    assert _decimal("1.23456", "amount") == Decimal("1.2346")
    with pytest.raises(BankReconciliationError):
        _decimal("not-money", "amount")
    with pytest.raises(BankReconciliationError):
        _decimal("-0.01", "amount", nonnegative=True)


def test_pdf_report_builder_escapes_untrusted_text_and_returns_pdf_bytes() -> None:
    document = _pdf_document(["Opening (balance)", r"Path \\server", "x" * 300])

    assert document.startswith(b"%PDF-1.4")
    assert b"Opening \\(balance\\)" in document
    assert b"Path \\\\\\\\server" in document
    assert b"%%EOF" in document


def test_import_request_idempotency_fails_closed_when_durable_job_is_missing() -> None:
    value = BankStatementImportFactory(idempotency_key="import-once", async_job_id=uuid.uuid4())

    with pytest.raises(BankReconciliationError) as exc:
        StatementImportService.request_import(
            value.tenant_id,
            value.requested_by_id,
            {"bank_account": value.bank_account_id, "file_format": "csv", "file": object()},
            "import-once",
        )

    assert exc.value.error_code == "IMPORT_INCOMPLETE"
    assert exc.value.status_code == 503


def test_statement_void_and_transaction_restore_are_idempotent_and_tenant_bound() -> None:
    transaction = BankTransactionFactory(match_status="excluded")
    statement = transaction.bank_statement

    restored = StatementService.restore_transaction(transaction.tenant_id, transaction.id, uuid.uuid4())
    assert restored.match_status == "unmatched"
    assert (
        StatementService.restore_transaction(transaction.tenant_id, transaction.id, uuid.uuid4()).id == transaction.id
    )
    with pytest.raises(BankReconciliationError):
        StatementService.restore_transaction(uuid.uuid4(), transaction.id, uuid.uuid4())

    voided = StatementService.void_statement(
        statement.tenant_id,
        statement.id,
        uuid.uuid4(),
        "Approved void",
        idempotency_key="void-once",
    )
    assert voided.status == "void"
    assert (
        StatementService.void_statement(
            statement.tenant_id,
            statement.id,
            uuid.uuid4(),
            "Approved void",
            idempotency_key="void-once",
        ).id
        == statement.id
    )
    with pytest.raises(BankReconciliationError):
        StatementService.restore_transaction(statement.tenant_id, transaction.id, uuid.uuid4())


def test_reconciliation_candidate_generation_fails_closed_without_ledger_source() -> None:
    statement = BankStatementFactory()
    reconciliation = ReconciliationService.create(
        statement.tenant_id,
        uuid.uuid4(),
        {
            "bank_statement_id": statement.id,
            "reconciliation_date": statement.period_end,
            "ledger_balance": statement.closing_balance,
            "tolerance": "0.0000",
        },
        "candidate-recon",
    )

    with pytest.raises(BankReconciliationError) as exc:
        ReconciliationService.generate_candidates(
            reconciliation.tenant_id,
            reconciliation.id,
            uuid.uuid4(),
            "candidate-run",
        )

    assert exc.value.error_code == "LEDGER_UNAVAILABLE"
    assert exc.value.status_code == 503
