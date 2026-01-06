"""Entitlement Models.

Database models for subscription entitlements and runtime gating.
Task: 503.1 - Subscription Entitlements & Runtime Gating
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone
from typing import Optional, Dict, Any
import uuid


class SubscriptionPlan(models.Model):
    """Subscription plan model.

    Defines subscription plans and their entitlements.
    """

    id = models.CharField(
        max_length=36, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name = models.CharField(max_length=255, unique=True, db_index=True)
    description = models.TextField(blank=True, null=True)
    plan_type = models.CharField(
        max_length=50,
        choices=[
            ("free", "Free"),
            ("basic", "Basic"),
            ("professional", "Professional"),
            ("enterprise", "Enterprise"),
            ("custom", "Custom"),
        ],
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    metadata = models.JSONField(
        default=dict, help_text="Plan metadata"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription_plans"
        indexes = [
            models.Index(fields=["plan_type"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.plan_type})"


class PlanEntitlement(models.Model):
    """Plan entitlement model.

    Defines entitlements for a subscription plan.
    """

    id = models.CharField(
        max_length=36, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.CASCADE,
        related_name="entitlements",
        db_index=True,
    )
    entitlement_type = models.CharField(
        max_length=50,
        choices=[
            ("module_access", "Module Access"),
            ("feature_access", "Feature Access"),
            ("resource_limit", "Resource Limit"),
            ("api_rate_limit", "API Rate Limit"),
            ("storage_limit", "Storage Limit"),
            ("user_limit", "User Limit"),
        ],
        db_index=True,
    )
    resource_name = models.CharField(
        max_length=255, db_index=True, help_text="Module name, feature name, etc."
    )
    limit_value = models.IntegerField(
        null=True, blank=True, help_text="Limit value (null = unlimited)"
    )
    limit_unit = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Limit unit (per_month, per_user, etc.)",
    )
    metadata = models.JSONField(
        default=dict, help_text="Entitlement metadata"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "plan_entitlements"
        unique_together = [["plan", "entitlement_type", "resource_name"]]
        indexes = [
            models.Index(fields=["plan_id", "entitlement_type"]),
            models.Index(fields=["plan_id", "resource_name"]),
        ]

    def __str__(self) -> str:
        return f"{self.plan.name} - {self.entitlement_type}: {self.resource_name}"


class TenantSubscription(models.Model):
    """Tenant subscription model.

    Tracks tenant subscriptions to plans.
    """

    id = models.CharField(
        max_length=36, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id = models.CharField(max_length=36, unique=True, db_index=True)
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
        db_index=True,
    )
    status = models.CharField(
        max_length=50,
        choices=[
            ("active", "Active"),
            ("suspended", "Suspended"),
            ("cancelled", "Cancelled"),
            ("expired", "Expired"),
        ],
        default="active",
        db_index=True,
    )
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    metadata = models.JSONField(
        default=dict, help_text="Subscription metadata"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_subscriptions"
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "expires_at"]),
            models.Index(fields=["plan_id", "status"]),
        ]

    def __str__(self) -> str:
        return f"Tenant {self.tenant_id} - {self.plan.name} ({self.status})"


class EntitlementCheck(models.Model):
    """Entitlement check audit model.

    Tracks entitlement checks for auditing.
    """

    id = models.CharField(
        max_length=36, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id = models.CharField(max_length=36, db_index=True)
    entitlement_type = models.CharField(max_length=50, db_index=True)
    resource_name = models.CharField(max_length=255, db_index=True)
    allowed = models.BooleanField(db_index=True)
    reason = models.TextField(null=True, blank=True)
    checked_at = models.DateTimeField(auto_now_add=True, db_index=True)
    metadata = models.JSONField(
        default=dict, help_text="Check metadata"
    )

    class Meta:
        db_table = "entitlement_checks"
        indexes = [
            models.Index(fields=["tenant_id", "entitlement_type"]),
            models.Index(fields=["tenant_id", "checked_at"]),
            models.Index(fields=["tenant_id", "allowed"]),
        ]

    def __str__(self) -> str:
        return (
            f"Entitlement check: {self.entitlement_type}/{self.resource_name} "
            f"(Tenant: {self.tenant_id}) - {'ALLOWED' if self.allowed else 'DENIED'}"
        )

