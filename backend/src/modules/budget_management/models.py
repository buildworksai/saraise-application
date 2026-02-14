"""
Budget Management Models.

Defines data models for budgets, budget lines, and variance tracking.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class TenantBaseModel(models.Model):
    """Base model for tenant-scoped models with Row-Level Multitenancy.

    CRITICAL: All tenant-scoped models MUST inherit from this base class
    and include tenant_id. All queries MUST filter explicitly by tenant_id.
    """

    tenant_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class Budget(TenantBaseModel):
    """Budget model - Budget container for a period."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    budget_code = models.CharField(max_length=50, db_index=True)
    budget_name = models.CharField(max_length=255)
    fiscal_year = models.IntegerField(db_index=True)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    status = models.CharField(max_length=50, default="draft", db_index=True)  # draft, approved, active, closed
    currency = models.CharField(max_length=3, default="USD")
    total_budget = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        db_table = "budget_budgets"
        indexes = [
            models.Index(fields=["tenant_id", "budget_code"]),
            models.Index(fields=["tenant_id", "fiscal_year"]),
            models.Index(fields=["tenant_id", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "budget_code"], name="unique_budget_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.budget_code} - {self.budget_name}"


class BudgetLine(TenantBaseModel):
    """Budget line model - Individual account budget allocation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="lines")
    account_id = models.UUIDField(db_index=True, help_text="FK to accounting account")
    account_code = models.CharField(max_length=50)
    budget_amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    actual_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    variance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        db_table = "budget_lines"
        indexes = [
            models.Index(fields=["tenant_id", "budget"]),
            models.Index(fields=["tenant_id", "account_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.budget.budget_code} - {self.account_code}"

    def save(self, *args, **kwargs):
        """Calculate variance on save."""
        self.variance = self.actual_amount - self.budget_amount
        super().save(*args, **kwargs)
