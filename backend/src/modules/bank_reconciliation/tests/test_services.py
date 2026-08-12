from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from src.core.async_jobs.models import AsyncJob, JobStatus, OutboxEvent

from ..models import BankAccount, BankTransaction, ReconciliationMatch
from ..services import (
    BankAccountService,
    BankReconciliationError,
    MatchingRuleService,
    ReconciliationService,
    StatementImportService,
    StatementService,
    register_ledger_gateway,
)
from .factories import (
    BankAccountFactory,
    BankStatementFactory,
    BankStatementImportFactory,
    BankTransactionFactory,
    MatchingRuleFactory,
    ReconciliationSessionFactory,
)

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


def test_account_archive_is_blocked_by_active_reconciliation() -> None:
    session = ReconciliationSessionFactory(status="in_progress")

    with pytest.raises(BankReconciliationError) as exc:
        BankAccountService.archive(session.tenant_id, session.bank_account_id, session.started_by_id)

    assert exc.value.error_code == "ACTIVE_RECONCILIATION"
    session.bank_account.refresh_from_db()
    assert session.bank_account.is_active


def test_account_update_rejects_identity_change_after_statement_exists() -> None:
    statement = BankStatementFactory()

    with pytest.raises(BankReconciliationError) as exc:
        BankAccountService.update(
            statement.tenant_id,
            statement.bank_account_id,
            statement.created_by_id,
            {"account_number": "NEW-ACCOUNT"},
        )

    assert exc.value.error_code == "ACCOUNT_LOCKED"
    statement.bank_account.refresh_from_db()
    assert statement.bank_account.account_number != "NEW-ACCOUNT"


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


def test_zero_amount_manual_transaction_is_rejected_before_recalculation() -> None:
    statement = BankStatementFactory()

    with pytest.raises(BankReconciliationError) as exc:
        StatementService.add_manual_transaction(
            statement.tenant_id,
            statement.id,
            statement.created_by_id,
            {"transaction_date": statement.period_end, "description": "No movement", "amount": "0.0000"},
        )

    assert exc.value.error_code == "VALIDATION_ERROR"
    statement.refresh_from_db()
    assert statement.transaction_total == Decimal("25.0000")


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


def csv_upload(name: str = "statement.csv", amount: str = "25.0000") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name,
        ("date,description,amount,reference,counterparty\n" f"2026-01-05,Deposit,{amount},DEP-1,Acme Corp\n").encode(
            "utf-8"
        ),
        content_type="text/csv",
    )


class FailingStorage:
    def __init__(self) -> None:
        self.saved: set[str] = set()
        self.deleted: list[str] = []

    def exists(self, name: str) -> bool:
        return name in self.saved

    def delete(self, name: str) -> None:
        self.saved.discard(name)
        self.deleted.append(name)

    def save(self, name: str, content) -> str:
        self.saved.add(name)
        return f"{name}.unexpected"


class FakeLedgerGateway:
    key = "fake"
    version = "1.0"

    def __init__(self, *, fail_validate: bool = False) -> None:
        self.fail_validate = fail_validate
        self.ledger_entry_id = uuid.uuid4()

    def validate_account(self, tenant_id, ledger_account_id) -> None:
        if self.fail_validate:
            raise RuntimeError("ledger offline")

    def get_balance(self, tenant_id, ledger_account_id, as_of_date):
        return Decimal("125.0000")

    def list_unreconciled(self, tenant_id, ledger_account_id, date_range):
        return [
            {
                "entry_id": self.ledger_entry_id,
                "entry_type": "payment",
                "transaction_date": date(2026, 1, 5),
                "amount": "25.0000",
                "currency": "USD",
                "reference": "DEP-1",
                "counterparty_name": "Acme Corp",
            }
        ]

    def health(self):
        return {"status": "available"}


def test_ledger_validation_fails_closed_and_wraps_gateway_outage() -> None:
    tenant, ledger_account = uuid.uuid4(), uuid.uuid4()
    register_ledger_gateway(None)

    with pytest.raises(BankReconciliationError) as missing:
        BankAccountService.validate_ledger_account(tenant, ledger_account)
    assert missing.value.error_code == "LEDGER_UNAVAILABLE"
    assert missing.value.status_code == 503

    register_ledger_gateway(FakeLedgerGateway(fail_validate=True))
    try:
        with pytest.raises(BankReconciliationError) as outage:
            BankAccountService.validate_ledger_account(tenant, ledger_account)
        assert outage.value.error_code == "LEDGER_UNAVAILABLE"
        assert outage.value.status_code == 503
    finally:
        register_ledger_gateway(None)


def test_matching_rule_validation_update_active_delete_and_in_use_guardrails() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()

    with pytest.raises(BankReconciliationError) as unsupported:
        MatchingRuleService.create(
            tenant,
            actor,
            {
                "name": "Bad config",
                "rule_type": "exact",
                "priority": 10,
                "configuration": {"unsafe": True},
                "minimum_score": "1.0000",
            },
        )
    assert unsupported.value.error_code == "INVALID_RULE"

    with pytest.raises(BankReconciliationError) as bad_regex:
        MatchingRuleService.create(
            tenant,
            actor,
            {
                "name": "Bad regex",
                "rule_type": "counterparty",
                "priority": 11,
                "configuration": {"counterparty_pattern": "["},
                "minimum_score": "0.9000",
            },
        )
    assert bad_regex.value.error_code == "INVALID_RULE"

    rule = MatchingRuleService.create(
        tenant,
        actor,
        {
            "name": "Exact reference",
            "rule_type": "exact",
            "priority": 1,
            "configuration": {"reference_normalization": "upper"},
            "auto_confirm": True,
            "minimum_score": "1.0000",
        },
    )
    updated = MatchingRuleService.update(
        tenant,
        rule.id,
        actor,
        {
            "priority": 2,
            "configuration": {"amount_tolerance": "2.5000"},
            "auto_confirm": False,
            "minimum_score": "0.9500",
        },
    )
    deactivated = MatchingRuleService.deactivate(tenant, updated.id, actor)
    activated = MatchingRuleService.activate(tenant, updated.id, actor)

    assert updated.priority == 2
    assert deactivated.is_active is False
    assert activated.is_active is True

    reconciliation = ReconciliationSessionFactory(tenant_id=tenant)
    ReconciliationMatch.objects.create(
        tenant_id=tenant,
        reconciliation=reconciliation,
        rule=activated,
        match_type="auto",
        status="proposed",
        score=Decimal("1.0000"),
    )
    with pytest.raises(BankReconciliationError) as in_use:
        MatchingRuleService.delete(tenant, activated.id, actor)
    assert in_use.value.error_code == "RULE_IN_USE"

    unused = MatchingRuleFactory(tenant_id=tenant, priority=99)
    MatchingRuleService.delete(tenant, unused.id, actor)
    with pytest.raises(BankReconciliationError) as deleted:
        MatchingRuleService.get(tenant, unused.id)
    assert deleted.value.error_code == "NOT_FOUND"


def test_statement_import_request_is_idempotent_and_rejects_storage_identity(monkeypatch) -> None:
    account = BankAccountFactory()
    actor = uuid.uuid4()
    key = "statement-import-jan"

    accepted = StatementImportService.request_import(
        account.tenant_id,
        actor,
        {
            "bank_account_id": account.id,
            "file_format": "csv",
            "file": csv_upload(),
            "mapping": {
                "statement_reference": "JAN-IMPORT",
                "opening_balance": "100.0000",
                "closing_balance": "125.0000",
            },
        },
        key,
    )
    replay = StatementImportService.request_import(
        account.tenant_id,
        actor,
        {
            "bank_account_id": account.id,
            "file_format": "csv",
            "file": csv_upload(),
            "mapping": {
                "statement_reference": "JAN-IMPORT",
                "opening_balance": "100.0000",
                "closing_balance": "125.0000",
            },
        },
        key,
    )

    assert replay.statement_import.id == accepted.statement_import.id
    assert replay.job.id == accepted.job.id
    assert accepted.job.command == "bank_reconciliation.import_statement"

    storage = FailingStorage()
    monkeypatch.setattr("src.modules.bank_reconciliation.services.default_storage", storage)
    with pytest.raises(BankReconciliationError) as conflict:
        StatementImportService.request_import(
            account.tenant_id,
            actor,
            {"bank_account_id": account.id, "file_format": "csv", "file": csv_upload("conflict.csv", "30.0000")},
            "statement-import-storage-conflict",
        )
    assert conflict.value.error_code == "STORAGE_CONFLICT"
    assert storage.deleted


def test_execute_import_success_replay_failure_and_retry_paths() -> None:
    account = BankAccountFactory()
    actor = uuid.uuid4()
    accepted = StatementImportService.request_import(
        account.tenant_id,
        actor,
        {
            "bank_account_id": account.id,
            "file_format": "csv",
            "file": csv_upload(),
            "mapping": {
                "statement_reference": "JAN-EXEC",
                "opening_balance": "100.0000",
                "closing_balance": "125.0000",
            },
        },
        "statement-import-execute",
    )

    statement = StatementImportService.execute_import(account.tenant_id, accepted.statement_import.id)
    replay = StatementImportService.execute_import(account.tenant_id, accepted.statement_import.id)
    accepted.statement_import.refresh_from_db()
    assert replay.id == statement.id
    assert accepted.statement_import.status == "succeeded"
    assert accepted.statement_import.rows_imported == 1
    assert statement.balance_variance == Decimal("0.0000")

    failed = StatementImportService.request_import(
        account.tenant_id,
        actor,
        {
            "bank_account_id": account.id,
            "file_format": "csv",
            "file": csv_upload("bad.csv", "26.0000"),
            "mapping": {
                "statement_reference": "JAN-BAD",
                "opening_balance": "100.0000",
                "closing_balance": "125.0000",
            },
        },
        "statement-import-failure",
    )
    with pytest.raises(BankReconciliationError) as mismatch:
        StatementImportService.execute_import(account.tenant_id, failed.statement_import.id)
    failed.statement_import.refresh_from_db()
    assert mismatch.value.error_code == "STATEMENT_BALANCE_MISMATCH"
    assert failed.statement_import.status == "failed"
    assert failed.statement_import.error_code == "STATEMENT_BALANCE_MISMATCH"

    retry = StatementImportService.retry_import(
        account.tenant_id,
        failed.statement_import.id,
        actor,
        "retry-after-mismatch",
    )
    failed.statement_import.refresh_from_db()
    assert retry.statement_import.status == "pending"
    assert failed.statement_import.error_code == ""

    cancelled = StatementImportService.cancel_import(
        account.tenant_id,
        failed.statement_import.id,
        actor,
    )
    assert cancelled.status == "cancelled"


def test_manual_match_conflict_rolls_back_and_confirm_reverse_are_idempotent() -> None:
    statement = BankStatementFactory()
    transaction = BankTransactionFactory(bank_statement=statement, tenant_id=statement.tenant_id)
    actor = uuid.uuid4()
    reconciliation = ReconciliationService.create(
        statement.tenant_id,
        actor,
        {
            "bank_statement_id": statement.id,
            "reconciliation_date": statement.period_end,
            "ledger_balance": statement.closing_balance,
            "tolerance": "0.0000",
        },
        "reconcile-match-conflict",
    )
    ReconciliationService.start(statement.tenant_id, reconciliation.id, actor, "start-match-conflict")

    with pytest.raises(BankReconciliationError) as conflict:
        ReconciliationService.create_manual_match(
            statement.tenant_id,
            reconciliation.id,
            actor,
            {
                "lines": [
                    {
                        "side": "bank",
                        "bank_transaction_id": transaction.id,
                        "allocated_amount": "25.0000",
                    },
                    {
                        "side": "bank",
                        "bank_transaction_id": transaction.id,
                        "allocated_amount": "25.0000",
                    },
                    {"side": "ledger", "ledger_entry_id": uuid.uuid4(), "allocated_amount": "50.0000"},
                ]
            },
        )
    assert conflict.value.error_code == "ALLOCATION_CONFLICT"
    assert ReconciliationMatch.objects.for_tenant(statement.tenant_id).count() == 0

    match = ReconciliationService.create_manual_match(
        statement.tenant_id,
        reconciliation.id,
        actor,
        {
            "lines": [
                {"side": "bank", "bank_transaction_id": transaction.id, "allocated_amount": "25.0000"},
                {
                    "side": "ledger",
                    "ledger_entry_id": uuid.uuid4(),
                    "ledger_entry_type": "payment",
                    "allocated_amount": "25.0000",
                },
            ]
        },
    )
    confirmed = ReconciliationService.confirm_match(statement.tenant_id, match.id, actor, "confirm-match")
    replayed_confirm = ReconciliationService.confirm_match(statement.tenant_id, match.id, actor, "confirm-match")
    transaction.refresh_from_db()
    assert confirmed.id == replayed_confirm.id
    assert transaction.match_status == "matched"
    assert transaction.is_reconciled is True

    reversed_match = ReconciliationService.reverse_match(
        statement.tenant_id,
        match.id,
        actor,
        "wrong ledger line",
        "reverse-match",
    )
    replayed_reverse = ReconciliationService.reverse_match(
        statement.tenant_id,
        match.id,
        actor,
        "wrong ledger line",
        "reverse-match",
    )
    transaction.refresh_from_db()
    assert replayed_reverse.id == reversed_match.id
    assert transaction.match_status == "unmatched"
    assert transaction.is_reconciled is False


def test_reconciliation_blockers_reject_and_void_restore_statement_status() -> None:
    statement = BankStatementFactory()
    transaction = BankTransactionFactory(bank_statement=statement, tenant_id=statement.tenant_id)
    actor, reviewer = uuid.uuid4(), uuid.uuid4()
    reconciliation = ReconciliationService.create(
        statement.tenant_id,
        actor,
        {
            "bank_statement_id": statement.id,
            "reconciliation_date": statement.period_end,
            "ledger_balance": statement.closing_balance,
            "tolerance": "0.0000",
        },
        "reconcile-blockers",
    )
    ReconciliationService.start(statement.tenant_id, reconciliation.id, actor, "start-blockers")
    match = ReconciliationService.create_manual_match(
        statement.tenant_id,
        reconciliation.id,
        actor,
        {
            "lines": [
                {"side": "bank", "bank_transaction_id": transaction.id, "allocated_amount": "25.0000"},
                {"side": "ledger", "ledger_entry_id": uuid.uuid4(), "allocated_amount": "25.0000"},
            ]
        },
    )

    summary = ReconciliationService.summary(statement.tenant_id, reconciliation.id)
    assert "Resolve proposed matches." in summary.blockers
    with pytest.raises(BankReconciliationError) as review_blocked:
        ReconciliationService.submit_review(statement.tenant_id, reconciliation.id, reviewer, "submit-with-proposal")
    assert review_blocked.value.error_code == "REVIEW_BLOCKED"

    rejected = ReconciliationService.reject_match(statement.tenant_id, match.id, actor, "not a ledger match")
    with pytest.raises(BankReconciliationError) as reject_again:
        ReconciliationService.reject_match(statement.tenant_id, rejected.id, actor, "again")
    assert reject_again.value.error_code == "MATCH_LOCKED"

    excluded = StatementService.exclude_transaction(statement.tenant_id, transaction.id, actor, "bank fee")
    assert excluded.match_status == "excluded"
    reviewed = ReconciliationService.submit_review(statement.tenant_id, reconciliation.id, reviewer, "submit-clean")
    returned = ReconciliationService.return_to_work(
        statement.tenant_id, reconciliation.id, actor, "needs another pass", "return-clean"
    )
    voided = ReconciliationService.void(statement.tenant_id, reconciliation.id, actor, "duplicate", "void-clean")
    statement.refresh_from_db()

    assert reviewed.reviewed_by_id == reviewer
    assert returned.status == "in_progress"
    assert voided.status == "void"
    assert statement.status == "imported"


def test_finalize_requires_tolerance_and_full_allocation() -> None:
    statement = BankStatementFactory()
    BankTransactionFactory(bank_statement=statement, tenant_id=statement.tenant_id)
    actor = uuid.uuid4()
    reconciliation = ReconciliationSessionFactory(
        bank_statement=statement,
        bank_account=statement.bank_account,
        tenant_id=statement.tenant_id,
        status="review",
        ledger_balance=Decimal("120.0000"),
        statement_balance=Decimal("125.0000"),
        difference=Decimal("5.0000"),
        tolerance=Decimal("1.0000"),
        reviewed_by_id=uuid.uuid4(),
    )

    with pytest.raises(BankReconciliationError) as variance:
        ReconciliationService.finalize(statement.tenant_id, reconciliation.id, actor, "finalize-variance")
    assert variance.value.error_code == "VARIANCE_EXCEEDS_TOLERANCE"

    reconciliation.ledger_balance = Decimal("125.0000")
    reconciliation.difference = Decimal("0.0000")
    reconciliation.save(update_fields=["ledger_balance", "difference", "updated_at"])
    with pytest.raises(BankReconciliationError) as unmatched:
        ReconciliationService.finalize(statement.tenant_id, reconciliation.id, actor, "finalize-unmatched")
    assert unmatched.value.error_code == "UNMATCHED_TRANSACTIONS"


def test_export_report_requires_finalized_session() -> None:
    reconciliation = ReconciliationSessionFactory(status="in_progress")

    with pytest.raises(BankReconciliationError) as exc:
        list(
            ReconciliationService.export_report(
                reconciliation.tenant_id,
                reconciliation.id,
                uuid.uuid4(),
                report_format="csv",
            )
        )

    assert exc.value.error_code == "REPORT_NOT_READY"


def test_candidate_generation_is_idempotent_and_requires_ledger_gateway() -> None:
    ledger_account_id = uuid.uuid4()
    account = BankAccountFactory(ledger_account_id=ledger_account_id)
    statement = BankStatementFactory(bank_account=account, tenant_id=account.tenant_id)
    BankTransactionFactory(
        bank_statement=statement,
        tenant_id=account.tenant_id,
        amount=Decimal("25.0000"),
        transaction_date=date(2026, 1, 5),
        reference_number="DEP-1",
        counterparty_name="Acme Corp",
    )
    actor = uuid.uuid4()
    reconciliation = ReconciliationSessionFactory(
        bank_account=account,
        bank_statement=statement,
        tenant_id=account.tenant_id,
        status="in_progress",
    )

    register_ledger_gateway(None)
    with pytest.raises(BankReconciliationError) as unavailable:
        ReconciliationService.generate_candidates(account.tenant_id, reconciliation.id, actor, "candidates-missing")
    assert unavailable.value.error_code == "LEDGER_UNAVAILABLE"

    register_ledger_gateway(FakeLedgerGateway())
    try:
        MatchingRuleService.create(
            account.tenant_id,
            actor,
            {
                "name": "Exact candidate",
                "rule_type": "exact",
                "priority": 10,
                "configuration": {"date_window_days": 5},
                "minimum_score": "0.9000",
            },
        )
        first = ReconciliationService.generate_candidates(account.tenant_id, reconciliation.id, actor, "candidates")
        second = ReconciliationService.generate_candidates(account.tenant_id, reconciliation.id, actor, "candidates")
    finally:
        register_ledger_gateway(None)

    assert len(first.proposals) == 1
    assert len(second.proposals) == 0
    assert first.evaluated_transactions == 1
    assert ReconciliationMatch.objects.for_tenant(account.tenant_id).count() == 1


def test_reconciliation_review_finalize_summary_and_export_evidence() -> None:
    account = BankAccountFactory()
    actor = uuid.uuid4()
    reviewer = uuid.uuid4()
    finalizer = uuid.uuid4()
    statement = StatementService.create_manual_statement(
        account.tenant_id,
        actor,
        {
            "bank_account_id": account.id,
            "statement_reference": "JAN-FINAL",
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 1, 31),
            "opening_balance": "100.0000",
            "closing_balance": "125.0000",
            "transactions": [
                {
                    "transaction_date": date(2026, 1, 5),
                    "description": "Deposit",
                    "amount": "25.0000",
                    "reference_number": "DEP-1",
                }
            ],
        },
    )
    transaction = statement.transactions.get()
    reconciliation = ReconciliationService.create(
        account.tenant_id,
        actor,
        {
            "bank_statement_id": statement.id,
            "reconciliation_date": statement.period_end,
            "ledger_balance": "125.0000",
            "tolerance": "0.0000",
        },
        "reconcile-final",
    )
    ReconciliationService.start(account.tenant_id, reconciliation.id, actor, "start-final")
    match = ReconciliationService.create_manual_match(
        account.tenant_id,
        reconciliation.id,
        actor,
        {
            "lines": [
                {"side": "bank", "bank_transaction_id": transaction.id, "allocated_amount": "25.0000"},
                {"side": "ledger", "ledger_entry_id": uuid.uuid4(), "allocated_amount": "25.0000"},
            ]
        },
    )
    ReconciliationService.confirm_match(account.tenant_id, match.id, actor, "confirm-final")
    summary = ReconciliationService.summary(account.tenant_id, reconciliation.id)
    assert summary.can_submit_review is True
    assert summary.can_finalize is False

    reviewed = ReconciliationService.submit_review(account.tenant_id, reconciliation.id, reviewer, "submit-review")
    ready = ReconciliationService.summary(account.tenant_id, reconciliation.id)
    assert ready.can_finalize is True

    with pytest.raises(BankReconciliationError) as sod:
        ReconciliationService.finalize(account.tenant_id, reconciliation.id, reviewer, "finalize-same-reviewer")
    assert sod.value.error_code == "SEPARATION_OF_DUTIES"

    finalized = ReconciliationService.finalize(account.tenant_id, reviewed.id, finalizer, "finalize-different-user")
    statement.refresh_from_db()
    csv_report = b"".join(
        ReconciliationService.export_report(account.tenant_id, reconciliation.id, actor, report_format="csv")
    )
    pdf_report = b"".join(
        ReconciliationService.export_report(account.tenant_id, reconciliation.id, actor, report_format="pdf")
    )

    assert finalized.status == "finalized"
    assert statement.status == "reconciled"
    assert b"reconciliation_id,status,statement_balance" in csv_report
    assert str(match.id).encode("utf-8") in csv_report
    assert pdf_report.startswith(b"%PDF-1.4")

    with pytest.raises(BankReconciliationError) as unsupported:
        list(ReconciliationService.export_report(account.tenant_id, reconciliation.id, actor, report_format="xlsx"))
    assert unsupported.value.error_code == "UNSUPPORTED_REPORT_FORMAT"


def test_void_statement_is_idempotent_and_cancel_import_transitions_running_job() -> None:
    statement = BankStatementFactory()
    actor = uuid.uuid4()

    voided = StatementService.void_statement(
        statement.tenant_id,
        statement.id,
        actor,
        "duplicate file",
        idempotency_key="void-statement",
    )
    replay = StatementService.void_statement(
        statement.tenant_id,
        statement.id,
        actor,
        "duplicate file",
        idempotency_key="void-statement",
    )
    assert replay.id == voided.id
    assert replay.status == "void"

    job = AsyncJob.objects.create(
        tenant_id=statement.tenant_id,
        actor_id=str(actor),
        command="bank_reconciliation.import_statement",
        idempotency_key="cancel-job",
        payload={},
        correlation_id=str(uuid.uuid4()),
        status=JobStatus.RUNNING,
    )
    statement_import = BankStatementImportFactory(
        bank_account=statement.bank_account,
        tenant_id=statement.tenant_id,
        async_job_id=job.id,
        status="running",
    )
    cancelled = StatementImportService.cancel_import(statement.tenant_id, statement_import.id, actor)
    job.refresh_from_db()
    assert cancelled.status == "cancelled"
    assert job.status == JobStatus.CANCELLED

    with pytest.raises(BankReconciliationError) as legacy:
        ReconciliationService.reconcile_statement(statement)
    assert legacy.value.error_code == "RECONCILIATION_REQUIRED"
