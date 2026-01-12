"""
Tenant Management Models.

CRITICAL: These are PLATFORM-LEVEL models (NO tenant_id).
Tenant Management operates at the platform level to manage all tenants.
All queries are platform-scoped, not tenant-scoped.
"""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

User = get_user_model()


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class PlatformBaseModel(models.Model):
    """Base model for platform-level models.

    CRITICAL: Platform-level models do NOT have tenant_id.
    They operate at the platform level, accessible only to platform owners.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(
        max_length=36,
        blank=True,
        null=True,
        help_text="User ID who created this record",
    )
    updated_by = models.CharField(
        max_length=36,
        blank=True,
        null=True,
        help_text="User ID who last updated this record",
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class Tenant(PlatformBaseModel):
    """Tenant organization model.

    Represents a tenant organization in the multi-tenant system.
    CRITICAL: This is a platform-level model (no tenant_id).
    """

    class TenantStatus(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        CANCELLED = "cancelled", "Cancelled"
        ARCHIVED = "archived", "Archived"

    class CompanySize(models.TextChoices):
        SIZE_1_10 = "1-10", "1-10 employees"
        SIZE_11_50 = "11-50", "11-50 employees"
        SIZE_51_200 = "51-200", "51-200 employees"
        SIZE_201_500 = "201-500", "201-500 employees"
        SIZE_500_PLUS = "500+", "500+ employees"

    # Basic Information
    name = models.CharField(max_length=200, db_index=True, help_text="Tenant organization name")
    slug = models.CharField(max_length=100, unique=True, db_index=True, help_text="URL-safe identifier")
    subdomain = models.CharField(
        max_length=100,
        unique=True,
        blank=True,
        null=True,
        db_index=True,
        help_text="Subdomain (tenant.saraise.com)",
    )
    custom_domain = models.CharField(
        max_length=200,
        unique=True,
        blank=True,
        null=True,
        db_index=True,
        help_text="Custom domain (mycompany.com)",
    )

    # Status & Subscription
    status = models.CharField(
        max_length=50,
        choices=TenantStatus.choices,
        default=TenantStatus.TRIAL,
        db_index=True,
    )
    subscription_plan_id = models.CharField(
        max_length=36,
        blank=True,
        null=True,
        help_text="Subscription plan ID (references billing module)",
    )
    trial_ends_at = models.DateTimeField(blank=True, null=True, help_text="Trial expiration date")
    subscription_start_date = models.DateField(blank=True, null=True)
    subscription_end_date = models.DateField(blank=True, null=True)

    # Contact Information
    primary_contact_name = models.CharField(max_length=200, blank=True)
    primary_contact_email = models.EmailField(blank=True)
    primary_contact_phone = models.CharField(max_length=50, blank=True)
    billing_email = models.EmailField(blank=True)
    technical_email = models.EmailField(blank=True)

    # Company Information
    logo_url = models.URLField(max_length=500, blank=True)
    website_url = models.URLField(max_length=500, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    company_size = models.CharField(max_length=50, choices=CompanySize.choices, blank=True)
    tax_id = models.CharField(max_length=100, blank=True)

    # Configuration
    timezone = models.CharField(max_length=100, default="UTC")
    default_language = models.CharField(max_length=10, default="en")
    default_currency = models.CharField(max_length=10, default="USD")
    fiscal_year_start_month = models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(12)])
    date_format = models.CharField(max_length=50, default="YYYY-MM-DD")
    time_format = models.CharField(max_length=50, default="HH:mm:ss")

    # Branding
    primary_color = models.CharField(max_length=7, blank=True, help_text="Hex color code")
    secondary_color = models.CharField(max_length=7, blank=True)
    accent_color = models.CharField(max_length=7, blank=True)

    # Feature Flags
    features_enabled = models.JSONField(default=dict, help_text="Feature flags configuration")

    # Resource Limits
    max_users = models.IntegerField(default=10, validators=[MinValueValidator(1)])
    max_storage_gb = models.IntegerField(default=10, validators=[MinValueValidator(1)])
    max_api_calls_per_day = models.IntegerField(default=10000, validators=[MinValueValidator(0)])

    # Metadata
    onboarded_by = models.CharField(
        max_length=36,
        blank=True,
        null=True,
        help_text="User ID who onboarded this tenant",
    )
    metadata = models.JSONField(default=dict, help_text="Additional metadata")

    class Meta:
        db_table = "tenants"
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["subscription_plan_id"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.slug})"

    @property
    def is_trial(self) -> bool:
        """Check if tenant is in trial period."""
        if self.status == self.TenantStatus.TRIAL:
            if self.trial_ends_at:
                return timezone.now() < self.trial_ends_at
            return True
        return False

    @property
    def is_active(self) -> bool:
        """Check if tenant is active."""
        return self.status == self.TenantStatus.ACTIVE


class TenantModule(PlatformBaseModel):
    """Tenant module installation tracking.

    Tracks which modules are enabled for each tenant.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="modules", db_index=True)
    module_name = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Module identifier (e.g., 'crm', 'accounting')",
    )
    is_enabled = models.BooleanField(default=True, db_index=True)
    installed_at = models.DateTimeField(auto_now_add=True)
    installed_by = models.CharField(
        max_length=36,
        blank=True,
        null=True,
        help_text="User ID who installed this module",
    )
    version = models.CharField(max_length=50, blank=True, help_text="Module version installed")
    configuration = models.JSONField(default=dict, help_text="Module-specific configuration")
    last_used_at = models.DateTimeField(blank=True, null=True, help_text="Last time module was accessed")
    usage_count = models.IntegerField(default=0, help_text="Number of times module was accessed")

    class Meta:
        db_table = "tenant_modules"
        verbose_name = "Tenant Module"
        verbose_name_plural = "Tenant Modules"
        unique_together = [["tenant", "module_name"]]
        indexes = [
            models.Index(fields=["tenant", "is_enabled"]),
            models.Index(fields=["module_name"]),
        ]

    def __str__(self):
        return f"{self.tenant.name} - {self.module_name}"


class TenantResourceUsage(PlatformBaseModel):
    """Tenant resource usage tracking.

    Tracks daily resource consumption per tenant.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="resource_usage", db_index=True)
    date = models.DateField(db_index=True, help_text="Date for this usage record")

    # Usage Metrics
    active_users = models.IntegerField(default=0)
    api_calls = models.IntegerField(default=0)
    storage_used_gb = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bandwidth_used_gb = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    email_sent = models.IntegerField(default=0)
    sms_sent = models.IntegerField(default=0)

    # Performance Metrics
    avg_response_time_ms = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    error_count = models.IntegerField(default=0)
    slow_query_count = models.IntegerField(default=0)

    class Meta:
        db_table = "tenant_resource_usage"
        verbose_name = "Tenant Resource Usage"
        verbose_name_plural = "Tenant Resource Usage"
        unique_together = [["tenant", "date"]]
        indexes = [
            models.Index(fields=["tenant", "date"]),
        ]

    def __str__(self):
        return f"{self.tenant.name} - {self.date}"


class TenantSettings(PlatformBaseModel):
    """Tenant-specific settings (key-value configuration).

    Stores tenant configuration settings by category.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="settings", db_index=True)
    category = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Setting category (e.g., 'email', 'notifications', 'security')",
    )
    key = models.CharField(max_length=200, db_index=True)
    value = models.JSONField(help_text="Setting value")
    is_encrypted = models.BooleanField(default=False)
    updated_by = models.CharField(
        max_length=36,
        blank=True,
        null=True,
        help_text="User ID who last updated this setting",
    )

    class Meta:
        db_table = "tenant_settings"
        verbose_name = "Tenant Setting"
        verbose_name_plural = "Tenant Settings"
        unique_together = [["tenant", "category", "key"]]
        indexes = [
            models.Index(fields=["tenant", "category"]),
        ]

    def __str__(self):
        return f"{self.tenant.name} - {self.category}.{self.key}"


class TenantHealthScore(PlatformBaseModel):
    """Tenant health score tracking.

    Tracks overall tenant health based on usage, errors, and performance.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="health_scores", db_index=True)
    date = models.DateField(db_index=True)
    overall_score = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Overall health score (0-100)",
    )

    # Component Scores
    usage_score = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)], blank=True, null=True)
    performance_score = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)], blank=True, null=True
    )
    error_score = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)], blank=True, null=True)
    engagement_score = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)], blank=True, null=True
    )

    # Risk Indicators
    churn_risk = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Churn risk percentage (0-100)",
    )
    at_risk_reasons = models.JSONField(default=list, help_text="List of risk factors")

    # Metadata
    calculated_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "tenant_health_scores"
        verbose_name = "Tenant Health Score"
        verbose_name_plural = "Tenant Health Scores"
        unique_together = [["tenant", "date"]]
        indexes = [
            models.Index(fields=["tenant", "date"]),
            models.Index(fields=["overall_score"]),
            models.Index(fields=["churn_risk"]),
        ]

    def __str__(self):
        return f"{self.tenant.name} - {self.date} (Score: {self.overall_score})"
