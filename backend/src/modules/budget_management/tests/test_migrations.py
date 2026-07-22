"""Migration durability and PostgreSQL RLS evidence for budget management."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

LEGACY = ("budget_management", "0001_initial")
LATEST = ("budget_management", "0005_enable_budget_rls")


def _migrate(target: tuple[str, str]):
    executor = MigrationExecutor(connection)
    executor.migrate([target])
    return executor.loader.project_state([target]).apps


@pytest.mark.django_db(transaction=True)
def test_forward_reverse_forward_preserves_legacy_identity_and_variance() -> None:
    tenant_id, budget_id, line_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        legacy = _migrate(LEGACY)
        Budget = legacy.get_model("budget_management", "Budget")
        BudgetLine = legacy.get_model("budget_management", "BudgetLine")
        budget = Budget.objects.create(
            id=budget_id, tenant_id=tenant_id, budget_code="LEG-001", budget_name="Legacy",
            fiscal_year=2025, start_date="2025-01-01", end_date="2025-12-31",
        )
        BudgetLine.objects.create(
            id=line_id, tenant_id=tenant_id, budget=budget, account_id=uuid.uuid4(),
            account_code="6000", budget_amount=Decimal("100.00"),
            actual_amount=Decimal("125.00"), variance=Decimal("25.00"),
        )

        current = _migrate(LATEST)
        CurrentBudget = current.get_model("budget_management", "Budget")
        CurrentLine = current.get_model("budget_management", "BudgetLine")
        assert CurrentBudget.objects.get(pk=budget_id).total_budget == Decimal("100.00")
        assert CurrentLine.objects.get(pk=line_id).variance == Decimal("-25.00")
        assert CurrentLine.objects.get(pk=line_id).period_type == "annual"

        restored = _migrate(LEGACY)
        RestoredLine = restored.get_model("budget_management", "BudgetLine")
        assert RestoredLine.objects.get(pk=line_id).variance == Decimal("25.00")
        assert RestoredLine.objects.get(pk=line_id).budget_id == budget_id

        current_again = _migrate(LATEST)
        assert current_again.get_model("budget_management", "BudgetLine").objects.get(pk=line_id).variance == Decimal("-25.00")
    finally:
        _migrate(LATEST)


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_all_domain_tables_have_forced_rls_and_tenant_policies() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL policy evidence requires PostgreSQL")
    _migrate(LATEST)
    tables = {
        "budget_budgets",
        "budget_lines",
        "budget_approvals",
        "budget_approval_decisions",
        "budget_transitions",
        "budget_variance_alerts", "budget_commitments",
    }
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   p.qual, p.with_check
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_policies p ON p.tablename = c.relname AND p.schemaname = n.nspname
            WHERE n.nspname = current_schema() AND c.relname = ANY(%s)
            """,
            [sorted(tables)],
        )
        evidence = {row[0]: row[1:] for row in cursor.fetchall()}
    assert set(evidence) == tables
    for enabled, forced, using_expression, check_expression in evidence.values():
        assert enabled is True
        assert forced is True
        assert using_expression
        assert check_expression
