"""
Bank Reconciliation Models.

Defines data models for bank accounts, statements, and reconciliations.
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


class BankAccount(TenantBaseModel):
    """Bank account model - Bank account for reconciliation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    account_number = models.CharField(max_length=100, db_index=True)
    bank_name = models.CharField(max_length=255)
    account_name = models.CharField(max_length=255)
    account_type = models.CharField(max_length=50, default="checking")  # checking, savings, credit
    currency = models.CharField(max_length=3, default="USD")
    ledger_account_id = models.UUIDField(null=True, blank=True, help_text="FK to accounting account")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "bank_accounts"
        indexes = [
            models.Index(fields=["tenant_id", "account_number"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "account_number"], name="unique_account_number_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.bank_name} - {self.account_number}"


class BankStatement(TenantBaseModel):
    """Bank statement model - Imported bank statement."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name="statements")
    statement_date = models.DateField(db_index=True)
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    closing_balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    is_reconciled = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "bank_statements"
        indexes = [
            models.Index(fields=["tenant_id", "bank_account"]),
            models.Index(fields=["tenant_id", "statement_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.bank_account.account_number} - {self.statement_date}"


class BankTransaction(TenantBaseModel):
    """Bank transaction model - Individual transaction in a statement."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    bank_statement = models.ForeignKey(BankStatement, on_delete=models.CASCADE, related_name="transactions")
    transaction_date = models.DateField(db_index=True)
    description = models.CharField(max_length=500)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_type = models.CharField(max_length=20, db_index=True)  # debit, credit
    reference_number = models.CharField(max_length=100, blank=True)
    is_reconciled = models.BooleanField(default=False, db_index=True)
    matched_payment_id = models.UUIDField(null=True, blank=True, help_text="FK to payment if matched")

    class Meta:
        db_table = "bank_transactions"
        indexes = [
            models.Index(fields=["tenant_id", "bank_statement"]),
            models.Index(fields=["tenant_id", "transaction_date"]),
            models.Index(fields=["tenant_id", "is_reconciled"]),
        ]

    def __str__(self) -> str:
        return f"{self.transaction_date} - {self.description} - {self.amount}"
