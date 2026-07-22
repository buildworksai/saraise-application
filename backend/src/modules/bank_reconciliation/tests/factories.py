"""Factory Boy builders for complete bank-reconciliation aggregate graphs."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import factory

from src.core.async_jobs.models import AsyncJob

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


class BankAccountFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BankAccount

    tenant_id = factory.LazyFunction(uuid.uuid4)
    account_number = factory.Sequence(lambda n: f"GB00 TEST 0000 {n:08d}")
    bank_name = "Example Bank"
    account_name = factory.Sequence(lambda n: f"Operating account {n}")
    account_type = "checking"
    currency = "USD"
    created_by_id = factory.LazyFunction(uuid.uuid4)


class BankStatementImportFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BankStatementImport

    tenant_id = factory.SelfAttribute("bank_account.tenant_id")
    bank_account = factory.SubFactory(BankAccountFactory)
    source = "file"
    file_format = "csv"
    source_document_id = factory.LazyFunction(uuid.uuid4)
    source_filename = "statement.csv"
    content_sha256 = factory.Sequence(lambda n: f"{n:064x}")
    idempotency_key = factory.Sequence(lambda n: f"import-{n}")
    requested_by_id = factory.LazyFunction(uuid.uuid4)


class BankStatementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BankStatement

    tenant_id = factory.SelfAttribute("bank_account.tenant_id")
    bank_account = factory.SubFactory(BankAccountFactory)
    statement_reference = factory.Sequence(lambda n: f"STMT-{n}")
    period_start = date(2026, 1, 1)
    period_end = date(2026, 1, 31)
    statement_date = date(2026, 1, 31)
    opening_balance = Decimal("100.0000")
    closing_balance = Decimal("125.0000")
    transaction_total = Decimal("25.0000")
    calculated_closing_balance = Decimal("125.0000")
    balance_variance = Decimal("0.0000")
    created_by_id = factory.LazyFunction(uuid.uuid4)


class BankTransactionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BankTransaction

    tenant_id = factory.SelfAttribute("bank_statement.tenant_id")
    bank_statement = factory.SubFactory(BankStatementFactory)
    sequence_number = factory.Sequence(lambda n: n + 1)
    transaction_date = date(2026, 1, 15)
    description = factory.Sequence(lambda n: f"Bank transaction {n}")
    amount = Decimal("25.0000")
    transaction_type = "credit"
    created_by_id = factory.LazyFunction(uuid.uuid4)


class MatchingRuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MatchingRule

    tenant_id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Exact match {n}")
    rule_type = "exact"
    priority = factory.Sequence(lambda n: n + 1)
    configuration = {}
    minimum_score = Decimal("1.0000")
    created_by_id = factory.LazyFunction(uuid.uuid4)
    updated_by_id = factory.LazyFunction(uuid.uuid4)


class ReconciliationSessionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ReconciliationSession

    tenant_id = factory.SelfAttribute("bank_statement.tenant_id")
    bank_statement = factory.SubFactory(BankStatementFactory)
    bank_account = factory.SelfAttribute("bank_statement.bank_account")
    reconciliation_date = date(2026, 1, 31)
    statement_balance = Decimal("125.0000")
    ledger_balance = Decimal("125.0000")
    difference = Decimal("0.0000")
    started_by_id = factory.LazyFunction(uuid.uuid4)


class ReconciliationMatchFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ReconciliationMatch

    tenant_id = factory.SelfAttribute("reconciliation.tenant_id")
    reconciliation = factory.SubFactory(ReconciliationSessionFactory)
    match_type = "manual"
    status = "proposed"


class ReconciliationMatchLineFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ReconciliationMatchLine

    tenant_id = factory.SelfAttribute("match.tenant_id")
    match = factory.SubFactory(ReconciliationMatchFactory)
    side = "ledger"
    ledger_entry_id = factory.LazyFunction(uuid.uuid4)
    ledger_entry_type = "journal_line"
    allocated_amount = Decimal("25.0000")
    currency = "USD"


class AsyncJobFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AsyncJob

    tenant_id = factory.LazyFunction(uuid.uuid4)
    actor_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    command = "bank_reconciliation.import_statement"
    idempotency_key = factory.Sequence(lambda n: f"bank-reconciliation-job-{n}")
    payload = factory.LazyFunction(dict)
    correlation_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
