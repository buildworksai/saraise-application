"""Persistence invariants for the governed budget domain."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from src.core.tenancy import TenantScopedModel, TimestampedModel
from src.modules.budget_management.models import (
    AppendOnlyDomainError,
    Budget,
    BudgetApproval,
    BudgetCommitment,
    BudgetLine,
    BudgetTransition,
    VarianceAlert,
)


@pytest.fixture
def identity() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.uuid4(), uuid.uuid4()


@pytest.fixture
def budget(db, identity: tuple[uuid.UUID, uuid.UUID]) -> Budget:
    tenant, actor = identity
    return Budget.objects.create(
        tenant_id=tenant, created_by=actor, updated_by=actor, budget_code="FY25-OPS",
        budget_name="Operations", fiscal_year=2025, start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31), budget_type="operating", currency="USD",
    )


@pytest.mark.django_db
def test_entities_use_canonical_tenancy_and_timestamps() -> None:
    assert issubclass(Budget, TenantScopedModel)
    assert issubclass(Budget, TimestampedModel)
    assert issubclass(BudgetLine, TenantScopedModel)
    assert issubclass(BudgetApproval, TenantScopedModel)
    assert issubclass(BudgetTransition, TenantScopedModel)
    assert issubclass(VarianceAlert, TenantScopedModel)
    assert issubclass(BudgetCommitment, TenantScopedModel)


@pytest.mark.django_db
def test_budget_defaults_and_string_representation(budget: Budget) -> None:
    assert budget.status == "draft"
    assert budget.total_budget == Decimal("0.00")
    assert str(budget) == "FY25-OPS - Operations"


@pytest.mark.django_db
def test_append_only_transition_and_approval_reject_update_delete(budget: Budget, identity) -> None:
    tenant, actor = identity
    approval = BudgetApproval.objects.create(
        tenant_id=tenant, budget=budget, approver_id=uuid.uuid4(), approval_level=1,
        status="pending", created_by=actor,
    )
    transition = BudgetTransition.objects.create(
        tenant_id=tenant, budget=budget, transition_key="submit-1", command="submit",
        from_state="draft", to_state="pending_approval", actor_id=actor,
    )
    approval.status = "approved"
    with pytest.raises(AppendOnlyDomainError):
        approval.save()
    with pytest.raises(AppendOnlyDomainError):
        transition.delete()
    with pytest.raises(AppendOnlyDomainError):
        BudgetTransition.objects.filter(pk=transition.pk).update(command="reject")


@pytest.mark.django_db
def test_soft_delete_and_period_invariants_validate(budget: Budget, identity) -> None:
    tenant, actor = identity
    budget.is_deleted = True
    with pytest.raises(ValidationError):
        budget.full_clean()
    line = BudgetLine(
        tenant_id=tenant, budget=budget, created_by=actor, updated_by=actor,
        account_code="6000", period_type="quarterly", period_number=5,
        budget_amount=Decimal("1.00"),
    )
    with pytest.raises(ValidationError):
        line.full_clean()
