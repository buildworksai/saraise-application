# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Rate Limit Models
# Reference: docs/architecture/module-framework.md § 3 (Module Models)
# Also: docs/architecture/security-model.md § 4.1 (Rate Limiting)
# 
# CRITICAL NOTES:
# - All rate limit models include tenant_id for Row-Level Multitenancy
# - Rate limit policies per tenant defined via CharField with choices
# - Request tracking via sliding window counter (atomic Redis operations)
# - Quota enforcement at route level via RateLimitMiddleware (after authorization)

from django.db import models
from django.utils import timezone
from typing import Optional
from datetime import datetime
import uuid

class RateLimitScopeChoices(models.TextChoices):
    API = "api", "API endpoint rate limiting"
    WORKFLOW = "workflow", "Workflow execution rate limiting"
    AGENT = "agent", "AI agent execution rate limiting"
    DATA_EXPORT = "data_export", "Data export rate limiting"
    FILE_UPLOAD = "file_upload", "File upload rate limiting"

class RateLimitPeriodChoices(models.TextChoices):
    SECOND = "second", "Per second"
    MINUTE = "minute", "Per minute"
    HOUR = "hour", "Per hour"
    DAY = "day", "Per day"
    MONTH = "month", "Per month"

class SubscriptionRateLimit(models.Model):
    """Rate limit configuration per subscription plan."""
    id = models.CharField(max_length=36, primary_key=True, default=lambda: str(uuid.uuid4()))
    subscription_plan_id = models.CharField(max_length=36, db_index=True)
    scope = models.CharField(
        max_length=50,
        choices=RateLimitScopeChoices.choices,
        db_index=True
    )
    limit = models.IntegerField()  # Number of requests
    period = models.CharField(
        max_length=50,
        choices=RateLimitPeriodChoices.choices
    )
    burst_limit = models.IntegerField(null=True, blank=True)  # Burst limit (optional)
    can_override = models.BooleanField(default=False)
    override_reason_required = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription_rate_limits"
        indexes = [
            models.Index(fields=['subscription_plan_id']),
            models.Index(fields=['scope']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['subscription_plan_id', 'scope'],
                name='uq_plan_scope'
            )
        ]

    def __str__(self):
        return f"{self.scope}: {self.limit}/{self.period}"

class RateLimitUsage(models.Model):
    """Track rate limit usage per tenant."""
    id = models.CharField(max_length=36, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = models.CharField(max_length=36, db_index=True)
    subscription_id = models.CharField(max_length=36, null=True, blank=True)
    scope = models.CharField(
        max_length=50,
        choices=RateLimitScopeChoices.choices,
        db_index=True
    )
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    request_count = models.IntegerField(default=0)
    limit = models.IntegerField()
    violations = models.IntegerField(default=0)
    last_violation_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rate_limit_usage"
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['scope']),
            models.Index(fields=['period_start', 'period_end']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant_id', 'scope', 'period_start'],
                name='uq_tenant_scope_period'
            )
        ]

    def __str__(self):
        return f"{self.tenant_id} ({self.scope}): {self.request_count}/{self.limit}"
    last_violation_at: Optional[datetime]] = models.DateTimeField(timezone=True))

    # Metadata
    created_at: datetime] = models.DateTimeField(timezone=True), server_default=func.now())
    updated_at: datetime] = models.DateTimeField(timezone=True), onupdate=func.now())

    # Relationships
    tenant: "Tenant"] = # Django ORM relationships via ForeignKey"Tenant", foreign_keys=[tenant_id])
    subscription: Optional["Subscription"]] = # Django ORM relationships via ForeignKey"Subscription", foreign_keys=[subscription_id])

    __table_args__ = (
        Index('idx_rate_usage_tenant', 'tenant_id'),
        Index('idx_rate_usage_scope', 'scope'),
        Index('idx_rate_usage_period', 'period_start', 'period_end'),
        UniqueConstraint('tenant_id', 'scope', 'period_start', name='uq_tenant_scope_period'),
    )

class RateLimitViolation(Base):
    class Meta:
        db_table = "rate_limit_violations"

    id: str] = models.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: str] = models.String, models.models.models.models.ForeignKey("tenants.id"), nullable=False)
    user_id: Optional[str]] = models.String, models.models.models.models.ForeignKey("users.id"))

    # Violation Details
    scope: str] = models.Enum(RateLimitScope), nullable=False)
    endpoint: Optional[str]] = models.CharField(max_length=500))
    request_method: Optional[str]] = models.CharField(max_length=10))
    limit: int] = models.IntegerField(), nullable=False)
    current_count: int] = models.IntegerField(), nullable=False)

    # Request Details
    ip_address: Optional[str]] = models.CharField(max_length=50))
    user_agent: Optional[str]] = models.Text)

    # Status
    is_resolved: bool] = models.BooleanField(), default=False)
    resolved_at: Optional[datetime]] = models.DateTimeField(timezone=True))

    # Metadata
    created_at: datetime] = models.DateTimeField(timezone=True), server_default=func.now())

    # Relationships
    tenant: "Tenant"] = # Django ORM relationships via ForeignKey"Tenant", foreign_keys=[tenant_id])
    user: Optional["User"]] = # Django ORM relationships via ForeignKey"User", foreign_keys=[user_id])

    __table_args__ = (
        Index('idx_violation_tenant', 'tenant_id'),
        Index('idx_violation_scope', 'scope'),
        Index('idx_violation_created', 'created_at'),
        Index('idx_violation_resolved', 'is_resolved'),
    )

