"""Transactional service behavior and tenant/concurrency safeguards."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from src.modules.budget_management.integrations import configure_integrations
from src.modules.budget_management.models import BudgetCommitment, BudgetLine
from src.modules.budget_management.services import BudgetControlService, BudgetDomainError, BudgetService


@pytest.fixture(autouse=True)
def reset_adapters():
    previous = configure_integrations()
    yield
    configure_integrations(
        accounting=previous.accounting, workflow=previous.workflow, notification=previous.notification
    )


@pytest.mark.django_db
def test_create_replace_total_variance_and_availability_are_decimal_and_tenant_scoped() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    budget = BudgetService.create_budget(
        tenant, actor, budget_code=" ops-25 ", budget_name="Operations", fiscal_year=2025,
        start_date=date(2025, 1, 1), end_date=date(2025, 12, 31),
        budget_type="operating", currency="usd", budget_ceiling="100.00",
    )
    budget = BudgetService.replace_allocations(
        tenant, budget.id, actor,
        [{"account_code": "6000", "period_type": "annual", "period_number": 1, "budget_amount": "100.00"}],
        expected_updated_at=budget.updated_at,
    )
    assert budget.budget_code == "OPS-25"
    assert budget.total_budget == Decimal("100.00")
    line = BudgetLine.objects.get(tenant_id=tenant, budget=budget)
    assert line.variance == Decimal("100.00")
    report = BudgetControlService.calculate_variance(tenant, budget.id)
    assert report.variance == Decimal("100.00")


@pytest.mark.django_db
def test_optimistic_concurrency_and_cross_tenant_parent_fail_closed() -> None:
    tenant, other, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    budget = BudgetService.create_budget(
        tenant, actor, budget_code="A", budget_name="A", fiscal_year=2025,
        start_date=date(2025, 1, 1), end_date=date(2025, 12, 31), budget_type="operating", currency="USD",
    )
    with pytest.raises(BudgetDomainError, match="changed"):
        BudgetService.update_budget(
            tenant, budget.id, actor, expected_updated_at="2024-01-01T00:00:00Z", changes={"budget_name": "B"}
        )
    with pytest.raises(BudgetDomainError) as exc:
        BudgetService.create_line(
            other, budget.id, actor,
            {"account_code": "6000", "period_type": "annual", "period_number": 1, "budget_amount": "1.00"},
        )
    assert exc.value.code == "NOT_FOUND"


@pytest.mark.django_db
def test_commitment_ledger_is_idempotent_and_release_cannot_underflow() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    budget = BudgetService.create_budget(
        tenant, actor, budget_code="C", budget_name="C", fiscal_year=2025,
        start_date=date(2025, 1, 1), end_date=date(2025, 12, 31), budget_type="operating", currency="USD",
    )
    line = BudgetService.create_line(
        tenant, budget.id, actor,
        {"account_code": "6100", "period_type": "annual", "period_number": 1, "budget_amount": "50.00"},
    )
    source_id = uuid.uuid4()
    BudgetControlService.record_commitment(tenant, line.id, "10.00", source_id=source_id, idempotency_key="reserve")
    repeated = BudgetControlService.record_commitment(
        tenant, line.id, "10.00", source_id=source_id, idempotency_key="reserve"
    )
    assert repeated.committed_amount == Decimal("10.00")
    assert BudgetCommitment.objects.filter(tenant_id=tenant, budget_line=line).count() == 1
    with pytest.raises(BudgetDomainError) as exc:
        BudgetControlService.release_commitment(
            tenant, line.id, "11.00", source_id=source_id, idempotency_key="release"
        )
    assert exc.value.code == "COMMITMENT_UNDERFLOW"


@pytest.mark.django_db
def test_actual_sync_without_accounting_is_explicitly_unavailable() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    budget = BudgetService.create_budget(
        tenant, actor, budget_code="S", budget_name="Sync", fiscal_year=2025,
        start_date=date(2025, 1, 1), end_date=date(2025, 12, 31), budget_type="operating", currency="USD",
    )
    with pytest.raises(Exception) as exc:
        BudgetControlService.request_actuals_sync(tenant, budget.id, actor, idempotency_key="sync-1")
    assert getattr(exc.value, "code", None) == "CAPABILITY_UNAVAILABLE"
