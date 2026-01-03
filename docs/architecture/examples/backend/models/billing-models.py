# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ REQUIRED: Billing model structures
# backend/src/modules/billing/models.py
# Reference: docs/architecture/module-framework.md § 3 (Module Models)
# Also: docs/architecture/application-architecture.md § 4.1 (Row-Level Multitenancy)

from django.db import models
from django.utils import timezone
from typing import Optional
from datetime import datetime
from decimal import Decimal
import uuid

class SubscriptionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"

class Subscription(models.Model):
    """Subscription model tracking tenant billing."""
    id = models.CharField(max_length=36, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = models.CharField(max_length=36, db_index=True)
    plan_id = models.CharField(max_length=36, db_index=True)
    status = models.CharField(
        max_length=50,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.ACTIVE,
        db_index=True
    )
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField(auto_now_add=True)
    current_period_end = models.DateTimeField()
    cancel_at_period_end = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscriptions"
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['status']),
            models.Index(fields=['tenant_id', 'status']),
        ]

    def __str__(self):
        return f"Subscription {self.id} ({self.status})"

class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING = "pending", "Pending"
    PAID = "paid", "Paid"
    OVERDUE = "overdue", "Overdue"
    CANCELLED = "cancelled", "Cancelled"

class Invoice(models.Model):
    """Invoice model for billing."""
    id = models.CharField(max_length=36, primary_key=True, default=lambda: str(uuid.uuid4()))
    subscription_id = models.CharField(max_length=36, db_index=True)
    tenant_id = models.CharField(max_length=36, db_index=True)
    invoice_number = models.CharField(max_length=50, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(
        max_length=50,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
        db_index=True
    )
    due_date = models.DateTimeField()
    paid_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "invoices"
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['subscription_id']),
            models.Index(fields=['status']),
            models.Index(fields=['tenant_id', 'status']),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} ({self.status})"

