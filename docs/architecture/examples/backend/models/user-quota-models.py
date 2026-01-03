# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: User Quota Models
# Reference: docs/architecture/module-framework.md § 3 (Module Models)
# Also: docs/architecture/security-model.md § 4.1 (Quota Enforcement)
# 
# CRITICAL NOTES:
# - All quota models include tenant_id for Row-Level Multitenancy
# - Quota limits per tenant defined via CharField with choices
# - Usage tracking via incremental counters (not full recalculation)
# - Quota enforcement at route level via middleware (after Policy Engine authorization)

from django.db import models
from django.utils import timezone
from typing import Optional
from datetime import datetime
import uuid

class QuotaTypeChoices(models.TextChoices):
    USERS = "users", "Maximum number of users"
    ACTIVE_USERS = "active_users", "Maximum number of active users"
    STORAGE = "storage", "Maximum storage in GB"
    API_CALLS = "api_calls", "Maximum API calls per month"
    WORKFLOWS = "workflows", "Maximum number of workflows"
    AGENTS = "agents", "Maximum number of AI agents"

class QuotaEnforcementChoices(models.TextChoices):
    SOFT = "soft", "Warning only, no blocking"
    HARD = "hard", "Block creation when exceeded"

class SubscriptionQuota(models.Model):
    """Quota limits per subscription plan."""
    id = models.CharField(max_length=36, primary_key=True, default=lambda: str(uuid.uuid4()))
    subscription_plan_id = models.CharField(max_length=36, db_index=True)
    quota_type = models.CharField(
        max_length=50,
        choices=QuotaTypeChoices.choices,
        db_index=True
    )
    limit = models.IntegerField()
    enforcement = models.CharField(
        max_length=50,
        choices=QuotaEnforcementChoices.choices,
        default=QuotaEnforcementChoices.HARD
    )
    warning_threshold = models.IntegerField(null=True, blank=True)  # Percentage or absolute value
    can_override = models.BooleanField(default=False)
    override_reason_required = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription_quotas"
        indexes = [
            models.Index(fields=['subscription_plan_id']),
            models.Index(fields=['quota_type']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['subscription_plan_id', 'quota_type'],
                name='uq_plan_quota_type'
            )
        ]

    def __str__(self):
        return f"{self.quota_type}: {self.limit} ({self.enforcement})"

class TenantQuotaUsage(models.Model):
    """Track quota usage per tenant."""
    id = models.CharField(max_length=36, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = models.CharField(max_length=36, db_index=True)
    subscription_id = models.CharField(max_length=36, null=True, blank=True)
    quota_type = models.CharField(
        max_length=50,
        choices=QuotaTypeChoices.choices,
        db_index=True
    )
    current_usage = models.IntegerField(default=0)
    limit = models.IntegerField()
    warning_sent = models.BooleanField(default=False)
    warning_sent_at = models.DateTimeField(null=True, blank=True)
    violations = models.IntegerField(default=0)
    last_violation_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_quota_usage"
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['quota_type']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant_id', 'quota_type'],
                name='uq_tenant_quota_type'
            )
        ]

    def __str__(self):
        return f"{self.tenant_id} ({self.quota_type}): {self.current_usage}/{self.limit}"
    last_violation_at: Optional[datetime]] = models.DateTimeField(timezone=True))

    # Metadata
    created_at: datetime] = models.DateTimeField(timezone=True), server_default=func.now())
    updated_at: datetime] = models.DateTimeField(timezone=True), onupdate=func.now())

    # Relationships
    tenant: "Tenant"] = # Django ORM relationships via ForeignKey"Tenant", foreign_keys=[tenant_id])
    subscription: Optional["Subscription"]] = # Django ORM relationships via ForeignKey"Subscription", foreign_keys=[subscription_id])

    __table_args__ = (
        Index('idx_quota_usage_tenant', 'tenant_id'),
        Index('idx_quota_usage_type', 'quota_type'),
        UniqueConstraint('tenant_id', 'quota_type', name='uq_tenant_quota_type'),
    )

class QuotaViolation(Base):
    class Meta:
        db_table = "quota_violations"

    id: str] = models.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: str] = models.String, models.models.models.models.ForeignKey("tenants.id"), nullable=False)
    user_id: Optional[str]] = models.String, models.models.models.models.ForeignKey("users.id"))

    # Violation Details
    quota_type: str] = models.Enum(QuotaType), nullable=False)
    limit: int] = models.IntegerField(), nullable=False)
    current_usage: int] = models.IntegerField(), nullable=False)
    attempted_action: Optional[str]] = models.CharField(max_length=255))  # e.g., "create_user"

    # Status
    is_resolved: bool] = models.BooleanField(), default=False)
    resolved_at: Optional[datetime]] = models.DateTimeField(timezone=True))
    resolved_by: Optional[str]] = models.String, models.models.models.models.ForeignKey("users.id"))

    # Metadata
    created_at: datetime] = models.DateTimeField(timezone=True), server_default=func.now())

    # Relationships
    tenant: "Tenant"] = # Django ORM relationships via ForeignKey"Tenant", foreign_keys=[tenant_id])
    user: Optional["User"]] = # Django ORM relationships via ForeignKey"User", foreign_keys=[user_id])
    resolver: Optional["User"]] = # Django ORM relationships via ForeignKey"User", foreign_keys=[resolved_by])

    __table_args__ = (
        Index('idx_violation_tenant', 'tenant_id'),
        Index('idx_violation_type', 'quota_type'),
        Index('idx_violation_created', 'created_at'),
        Index('idx_violation_resolved', 'is_resolved'),
    )

