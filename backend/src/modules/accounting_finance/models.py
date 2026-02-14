"""
Accounting & Finance Models.

Defines data models for financial management including Chart of Accounts,
Journal Entries, AP/AR Invoices, and Payments.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


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


class AccountType(models.TextChoices):
    """Account type choices for Chart of Accounts."""

    ASSET = "asset", "Asset"
    LIABILITY = "liability", "Liability"
    EQUITY = "equity", "Equity"
    REVENUE = "revenue", "Revenue"
    EXPENSE = "expense", "Expense"


class Account(TenantBaseModel):
    """Chart of Accounts - Ledger account model."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    code = models.CharField(max_length=50, db_index=True, help_text="Account code (e.g., 1000, 2000)")
    name = models.CharField(max_length=255, db_index=True)
    account_type = models.CharField(max_length=20, choices=AccountType.choices, db_index=True)
    parent_account_id = models.UUIDField(null=True, blank=True, help_text="Parent account for hierarchy")
    is_active = models.BooleanField(default=True, db_index=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "accounting_accounts"
        indexes = [
            models.Index(fields=["tenant_id", "code"]),
            models.Index(fields=["tenant_id", "account_type"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "code"], name="unique_account_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class PostingPeriodStatus(models.TextChoices):
    """Posting period status choices."""

    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"


class PostingPeriod(TenantBaseModel):
    """Posting period for financial transactions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    period_name = models.CharField(max_length=50, db_index=True, help_text="e.g., 2024-01")
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=PostingPeriodStatus.choices, default=PostingPeriodStatus.OPEN)

    class Meta:
        db_table = "accounting_posting_periods"
        indexes = [
            models.Index(fields=["tenant_id", "start_date", "end_date"]),
            models.Index(fields=["tenant_id", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "period_name"], name="unique_period_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.period_name} ({self.status})"


class JournalEntryStatus(models.TextChoices):
    """Journal entry status choices."""

    DRAFT = "draft", "Draft"
    POSTED = "posted", "Posted"
    REVERSED = "reversed", "Reversed"


class JournalEntry(TenantBaseModel):
    """Journal entry - Financial transaction with debits and credits."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    entry_number = models.CharField(max_length=50, db_index=True, help_text="Sequential entry number")
    posting_date = models.DateField(db_index=True)
    posting_period = models.ForeignKey(PostingPeriod, on_delete=models.PROTECT, related_name="journal_entries")
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=JournalEntryStatus.choices, default=JournalEntryStatus.DRAFT)
    debit_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    credit_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.CharField(max_length=36, null=True, blank=True)

    class Meta:
        db_table = "accounting_journal_entries"
        indexes = [
            models.Index(fields=["tenant_id", "posting_date"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "entry_number"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "entry_number"], name="accounting_unique_entry_number_per_tenant"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.entry_number} - {self.posting_date}"

    def clean(self):
        """Validate that debits equal credits."""
        from django.core.exceptions import ValidationError

        if abs(self.debit_total - self.credit_total) > Decimal("0.01"):
            raise ValidationError("Debits must equal credits in a journal entry")


class JournalLine(TenantBaseModel):
    """Journal line - Individual debit or credit in a journal entry."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="journal_lines")
    debit_amount = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))]
    )
    credit_amount = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))]
    )
    description = models.CharField(max_length=500, blank=True)
    cost_center = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "accounting_journal_lines"
        indexes = [
            models.Index(fields=["tenant_id", "journal_entry"]),
            models.Index(fields=["tenant_id", "account"]),
        ]

    def __str__(self) -> str:
        return f"{self.journal_entry.entry_number} - {self.account.code}"

    def clean(self):
        """Validate that either debit or credit is set, but not both."""
        from django.core.exceptions import ValidationError

        if self.debit_amount > 0 and self.credit_amount > 0:
            raise ValidationError("A journal line cannot have both debit and credit amounts")
        if self.debit_amount == 0 and self.credit_amount == 0:
            raise ValidationError("A journal line must have either a debit or credit amount")


class APInvoiceStatus(models.TextChoices):
    """AP Invoice status choices."""

    DRAFT = "draft", "Draft"
    PENDING = "pending", "Pending"
    PARTIALLY_PAID = "partially_paid", "Partially Paid"
    PAID = "paid", "Paid"
    CANCELLED = "cancelled", "Cancelled"


class APInvoice(TenantBaseModel):
    """Accounts Payable Invoice - Supplier bill."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    invoice_number = models.CharField(max_length=100, db_index=True, help_text="Supplier invoice number")
    supplier_id = models.UUIDField(db_index=True, help_text="FK to supplier (master_data_management)")
    invoice_date = models.DateField(db_index=True)
    due_date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=APInvoiceStatus.choices, default=APInvoiceStatus.DRAFT)
    currency = models.CharField(max_length=3, default="USD")
    description = models.TextField(blank=True)

    class Meta:
        db_table = "accounting_ap_invoices"
        indexes = [
            models.Index(fields=["tenant_id", "supplier_id"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "due_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "supplier_id", "invoice_number"], name="unique_ap_invoice_per_tenant"
            ),
        ]

    def __str__(self) -> str:
        return f"AP-{self.invoice_number} - {self.total_amount}"


class ARInvoiceStatus(models.TextChoices):
    """AR Invoice status choices."""

    DRAFT = "draft", "Draft"
    PENDING = "pending", "Pending"
    PARTIALLY_PAID = "partially_paid", "Partially Paid"
    PAID = "paid", "Paid"
    OVERDUE = "overdue", "Overdue"
    CANCELLED = "cancelled", "Cancelled"


class ARInvoice(TenantBaseModel):
    """Accounts Receivable Invoice - Customer invoice."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    invoice_number = models.CharField(max_length=100, db_index=True, help_text="Sequential invoice number")
    customer_id = models.UUIDField(db_index=True, help_text="FK to customer (master_data_management)")
    invoice_date = models.DateField(db_index=True)
    due_date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=ARInvoiceStatus.choices, default=ARInvoiceStatus.DRAFT)
    currency = models.CharField(max_length=3, default="USD")
    description = models.TextField(blank=True)

    class Meta:
        db_table = "accounting_ar_invoices"
        indexes = [
            models.Index(fields=["tenant_id", "customer_id"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "due_date"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "invoice_number"], name="unique_ar_invoice_number_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"AR-{self.invoice_number} - {self.total_amount}"


class PaymentMethod(models.TextChoices):
    """Payment method choices."""

    CASH = "cash", "Cash"
    CHECK = "check", "Check"
    WIRE_TRANSFER = "wire_transfer", "Wire Transfer"
    ACH = "ach", "ACH"
    CREDIT_CARD = "credit_card", "Credit Card"
    OTHER = "other", "Other"


class Payment(TenantBaseModel):
    """Payment - Money paid to supplier or received from customer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    payment_date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    currency = models.CharField(max_length=3, default="USD")
    reference_number = models.CharField(max_length=100, blank=True)
    ap_invoice = models.ForeignKey(APInvoice, on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    ar_invoice = models.ForeignKey(ARInvoice, on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    description = models.TextField(blank=True)

    class Meta:
        db_table = "accounting_payments"
        indexes = [
            models.Index(fields=["tenant_id", "payment_date"]),
            models.Index(fields=["tenant_id", "ap_invoice"]),
            models.Index(fields=["tenant_id", "ar_invoice"]),
        ]

    def __str__(self) -> str:
        return f"Payment {self.amount} - {self.payment_date}"

    def clean(self):
        """Validate that payment is linked to either AP or AR invoice, but not both."""
        from django.core.exceptions import ValidationError

        if not self.ap_invoice and not self.ar_invoice:
            raise ValidationError("Payment must be linked to either AP or AR invoice")
        if self.ap_invoice and self.ar_invoice:
            raise ValidationError("Payment cannot be linked to both AP and AR invoice")
