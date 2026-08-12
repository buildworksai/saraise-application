"""Strict bank reconciliation collection filter coverage."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from ..filters import (
    BankAccountFilterSet,
    BankStatementFilterSet,
    BankTransactionFilterSet,
    BaseFilterSet,
    FilterValidationError,
    MatchingRuleFilterSet,
    ReconciliationFilterSet,
    StatementImportFilterSet,
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


def assert_ids(queryset, expected) -> None:
    assert list(queryset.values_list("id", flat=True)) == [item.id for item in expected]


def test_base_filterset_rejects_unknown_query_and_requires_queryset() -> None:
    filterset = BaseFilterSet({"tenant_id": "spoof"})
    assert filterset.is_valid() is False
    assert filterset.errors == {"query": "Unsupported filters: tenant_id."}
    with pytest.raises(FilterValidationError):
        _ = filterset.qs

    empty = BaseFilterSet({}, None)
    with pytest.raises(ValueError, match="requires a queryset"):
        empty.is_valid()


def test_bank_account_filterset_filters_searches_and_orders_safely() -> None:
    operating = BankAccountFactory(
        bank_name="Acme Bank",
        account_name="Operating",
        account_type="checking",
        currency="USD",
        is_active=True,
        account_number="000000001234",
    )
    BankAccountFactory(
        tenant_id=operating.tenant_id,
        bank_name="Other Bank",
        account_name="Reserve",
        account_type="savings",
        currency="EUR",
        is_active=False,
        account_number="000000005678",
    )

    queryset = BankAccountFilterSet(
        {"search": "1234", "is_active": "true", "account_type": "checking", "currency": "USD"},
        BankAccountFactory._meta.model.objects.for_tenant(operating.tenant_id),
    ).qs

    assert_ids(queryset, [operating])
    invalid = BankAccountFilterSet({"is_active": "sometimes"}, BankAccountFactory._meta.model.objects.all())
    assert invalid.is_valid() is False
    assert invalid.errors == {"is_active": "Must be a boolean."}


def test_statement_filterset_validates_uuid_dates_variance_and_search() -> None:
    account = BankAccountFactory(account_name="Payroll")
    clean = BankStatementFactory(
        bank_account=account,
        statement_reference="JAN-2026",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        balance_variance=Decimal("0.0000"),
    )
    BankStatementFactory(
        bank_account=account,
        statement_reference="FEB-2026",
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
        balance_variance=Decimal("10.0000"),
    )

    base = BankStatementFactory._meta.model.objects.for_tenant(account.tenant_id)
    result = BankStatementFilterSet(
        {
            "account": str(account.id),
            "period_start": "2026-01-15",
            "period_end": "2026-01-31",
            "has_variance": "false",
            "search": "payroll",
        },
        base,
    ).qs
    assert list(result) == [clean]
    invalid = BankStatementFilterSet(
        {"account": "not-a-uuid", "period_start": "31-01-2026", "has_variance": "maybe"},
        base,
    )
    assert invalid.is_valid() is False
    assert invalid.errors == {
        "account": "Must be a valid UUID.",
        "period_start": "Must be an ISO date.",
    }
    invalid_variance = BankStatementFilterSet({"has_variance": "maybe"}, base)
    assert invalid_variance.is_valid() is False
    assert invalid_variance.errors == {"has_variance": "Must be a boolean."}


def test_transaction_filterset_searches_amount_ranges_and_rejects_bad_decimals() -> None:
    statement = BankStatementFactory()
    target = BankTransactionFactory(
        bank_statement=statement,
        description="Stripe payout",
        reference_number="PAY-1",
        counterparty_name="Stripe",
        amount=Decimal("25.0000"),
        transaction_type="credit",
    )
    BankTransactionFactory(bank_statement=statement, description="Fee", amount=Decimal("-5.0000"))

    base = BankTransactionFactory._meta.model.objects.for_tenant(statement.tenant_id)
    result = BankTransactionFilterSet(
        {
            "statement": str(statement.id),
            "transaction_type": "credit",
            "amount_min": "20",
            "amount_max": "30",
            "search": "stripe",
        },
        base,
    ).qs
    assert list(result) == [target]
    invalid = BankTransactionFilterSet({"amount_min": "NaN", "ordering": "tenant_id"}, base)
    assert invalid.is_valid() is False
    assert invalid.errors == {"ordering": "Ordering field is not allowed."}
    invalid_amount = BankTransactionFilterSet({"amount_min": "NaN"}, base)
    assert invalid_amount.is_valid() is False
    assert invalid_amount.errors == {"amount_min": "Must be a finite decimal."}


def test_import_rule_and_reconciliation_filtersets_cover_extra_boolean_paths() -> None:
    account = BankAccountFactory(account_name="Operations")
    imported = BankStatementImportFactory(
        bank_account=account,
        source_filename="jan.csv",
        file_format="csv",
        status="pending",
    )
    rule = MatchingRuleFactory(tenant_id=account.tenant_id, name="Exact invoice", is_active=True, rule_type="exact")
    statement = BankStatementFactory(bank_account=account)
    open_session = ReconciliationSessionFactory(bank_statement=statement, difference=Decimal("0.0000"))
    finalized_statement = BankStatementFactory(bank_account=account, statement_reference="FINAL-2026")
    finalized = ReconciliationSessionFactory(
        bank_statement=finalized_statement,
        status="finalized",
        difference=Decimal("1.0000"),
        finalized_by_id=account.created_by_id,
        finalized_at=timezone.now(),
    )

    assert_ids(
        StatementImportFilterSet(
            {"bank_account": str(account.id), "format": "csv", "status": "pending", "search": "jan"},
            BankStatementImportFactory._meta.model.objects.for_tenant(account.tenant_id),
        ).qs,
        [imported],
    )
    assert_ids(
        MatchingRuleFilterSet(
            {"rule_type": "exact", "is_active": "1", "search": "invoice"},
            MatchingRuleFactory._meta.model.objects.for_tenant(account.tenant_id),
        ).qs,
        [rule],
    )
    assert_ids(
        ReconciliationFilterSet(
            {"bank_statement": str(statement.id), "has_difference": "false", "finalized": "false"},
            ReconciliationSessionFactory._meta.model.objects.for_tenant(account.tenant_id),
        ).qs,
        [open_session],
    )
    assert_ids(
        ReconciliationFilterSet(
            {"bank_statement": str(finalized_statement.id), "has_difference": "true", "finalized": "true"},
            ReconciliationSessionFactory._meta.model.objects.for_tenant(account.tenant_id),
        ).qs,
        [finalized],
    )
    invalid = ReconciliationFilterSet(
        {"has_difference": "unknown", "finalized": "unknown"},
        ReconciliationSessionFactory._meta.model.objects.for_tenant(account.tenant_id),
    )
    assert invalid.is_valid() is False
    assert invalid.errors == {"has_difference": "Must be a boolean."}
