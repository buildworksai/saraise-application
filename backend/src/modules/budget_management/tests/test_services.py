"""
Service tests for Budget Management module.
"""

import uuid
import pytest
from datetime import date

from src.modules.budget_management.models import Budget
from src.modules.budget_management.services import BudgetService


@pytest.mark.django_db
class TestBudgetService:
    """Test BudgetService."""

    def test_create_budget(self):
        """Test creating a budget via service."""
        tenant_id = uuid.uuid4()
        budget = BudgetService.create_budget(
            tenant_id=str(tenant_id),
            budget_code="BUD-001",
            budget_name="Test Budget",
            fiscal_year=2024,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        assert budget.budget_code == "BUD-001"
        assert budget.fiscal_year == 2024
        assert str(budget.tenant_id) == str(tenant_id)
