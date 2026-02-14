"""
Business logic services for Budget Management module.
"""

from typing import Optional
from decimal import Decimal
from django.db import transaction, models

from .models import Budget, BudgetLine


class BudgetService:
    """Service for budget operations."""

    @staticmethod
    def create_budget(tenant_id: str, budget_code: str, budget_name: str, fiscal_year: int, start_date: str, end_date: str, **kwargs) -> Budget:
        """Create a new budget."""
        return Budget.objects.create(
            tenant_id=tenant_id,
            budget_code=budget_code,
            budget_name=budget_name,
            fiscal_year=fiscal_year,
            start_date=start_date,
            end_date=end_date,
            **kwargs,
        )

    @staticmethod
    @transaction.atomic
    def calculate_total_budget(budget: Budget) -> Budget:
        """Calculate total budget from budget lines."""
        total = BudgetLine.objects.filter(budget=budget).aggregate(
            total=models.Sum("budget_amount")
        )["total"] or Decimal("0.00")
        budget.total_budget = total
        budget.save()
        return budget
