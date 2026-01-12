"""
BillingSubscriptions Models.

Defines data models for BillingSubscriptions module.
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

    tenant_id = models.CharField(max_length=36, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "billing_subscriptions"
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class SubscriptionPlan(models.Model):
    """Subscription plan model (platform-level, no tenant_id)."""

    BILLING_CYCLE_CHOICES = [
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
        ("yearly", "Yearly"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Price in default currency",
    )
    billing_cycle = models.CharField(
        max_length=20,
        choices=BILLING_CYCLE_CHOICES,
        db_index=True,
    )
    features = models.JSONField(
        default=list,
        help_text="List of features included in this plan",
    )
    limits = models.JSONField(
        default=dict,
        help_text="Resource limits (e.g., max_users, max_storage_gb)",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "billing_subscriptions"
        db_table = "billing_subscriptions_plans"
        indexes = [
            models.Index(fields=["billing_cycle", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.billing_cycle})"


class Subscription(TenantBaseModel):
    """Subscription model for tenant subscriptions."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("cancelled", "Cancelled"),
        ("expired", "Expired"),
        ("trial", "Trial"),
        ("past_due", "Past Due"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="trial",
        db_index=True,
    )
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(null=True, blank=True, db_index=True)
    trial_start_date = models.DateField(null=True, blank=True)
    trial_end_date = models.DateField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        app_label = "billing_subscriptions"
        db_table = "billing_subscriptions_subscriptions"
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "end_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.tenant_id} - {self.plan.name} ({self.status})"

    @property
    def is_trial(self) -> bool:
        """Check if subscription is in trial period."""
        if not self.trial_end_date:
            return False
        return timezone.now().date() <= self.trial_end_date

    @property
    def is_active(self) -> bool:
        """Check if subscription is currently active."""
        return self.status == "active" and (
            self.end_date is None or timezone.now().date() <= self.end_date
        )


class Invoice(TenantBaseModel):
    """Invoice model for billing records."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("overdue", "Overdue"),
        ("cancelled", "Cancelled"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.PROTECT,
        related_name="invoices",
        null=True,
        blank=True,
    )
    invoice_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Sequential invoice number",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    tax_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
        db_index=True,
    )
    due_date = models.DateField(db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "billing_subscriptions"
        db_table = "billing_subscriptions_invoices"
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "due_date"]),
        ]

    def __str__(self) -> str:
        return f"Invoice {self.invoice_number} - {self.total_amount}"


class InvoiceLineItem(models.Model):
    """Invoice line item model for detailed billing."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="line_items",
    )
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    class Meta:
        app_label = "billing_subscriptions"
        db_table = "billing_subscriptions_invoice_line_items"

    def __str__(self) -> str:
        return f"{self.invoice.invoice_number} - {self.description}"

    def save(self, *args, **kwargs):
        """Calculate total_price on save."""
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)


class Payment(TenantBaseModel):
    """Payment model for tracking payments."""

    PAYMENT_METHOD_CHOICES = [
        ("credit_card", "Credit Card"),
        ("bank_transfer", "Bank Transfer"),
        ("paypal", "PayPal"),
        ("stripe", "Stripe"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    payment_method = models.CharField(
        max_length=50,
        choices=PAYMENT_METHOD_CHOICES,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    transaction_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="External payment gateway transaction ID",
    )
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "billing_subscriptions"
        db_table = "billing_subscriptions_payments"
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["invoice"]),
        ]

    def __str__(self) -> str:
        return f"Payment {self.amount} - {self.status}"


class UsageRecord(TenantBaseModel):
    """Usage record model for metered billing."""

    RESOURCE_TYPE_CHOICES = [
        ("api_calls", "API Calls"),
        ("storage_gb", "Storage (GB)"),
        ("users", "Users"),
        ("compute_hours", "Compute Hours"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    resource_type = models.CharField(
        max_length=50,
        choices=RESOURCE_TYPE_CHOICES,
        db_index=True,
    )
    quantity = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    recorded_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        app_label = "billing_subscriptions"
        db_table = "billing_subscriptions_usage_records"
        indexes = [
            models.Index(fields=["tenant_id", "resource_type", "recorded_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.resource_type}: {self.quantity} at {self.recorded_at}"
