"""
Django Admin configuration for Tenant Management module.
"""

from django.contrib import admin
from .models import (
    Tenant,
    TenantModule,
    TenantResourceUsage,
    TenantSettings,
    TenantHealthScore,
)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    """Admin interface for Tenant model."""

    list_display = [
        "name",
        "slug",
        "status",
        "subscription_plan_id",
        "created_at",
        "trial_ends_at",
    ]
    list_filter = ["status", "company_size", "industry", "created_at"]
    search_fields = [
        "name",
        "slug",
        "subdomain",
        "custom_domain",
        "primary_contact_email",
    ]
    readonly_fields = ["id", "created_at", "updated_at"]

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("name", "slug", "subdomain", "custom_domain", "status")},
        ),
        (
            "Subscription",
            {
                "fields": (
                    "subscription_plan_id",
                    "trial_ends_at",
                    "subscription_start_date",
                    "subscription_end_date",
                )
            },
        ),
        (
            "Contact Information",
            {
                "fields": (
                    "primary_contact_name",
                    "primary_contact_email",
                    "primary_contact_phone",
                    "billing_email",
                    "technical_email",
                )
            },
        ),
        (
            "Company Information",
            {
                "fields": (
                    "logo_url",
                    "website_url",
                    "industry",
                    "company_size",
                    "tax_id",
                )
            },
        ),
        (
            "Configuration",
            {
                "fields": (
                    "timezone",
                    "default_language",
                    "default_currency",
                    "fiscal_year_start_month",
                    "date_format",
                    "time_format",
                )
            },
        ),
        ("Branding", {"fields": ("primary_color", "secondary_color", "accent_color")}),
        (
            "Resource Limits",
            {"fields": ("max_users", "max_storage_gb", "max_api_calls_per_day")},
        ),
        (
            "Metadata",
            {
                "fields": (
                    "features_enabled",
                    "metadata",
                    "created_by",
                    "onboarded_by",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


@admin.register(TenantModule)
class TenantModuleAdmin(admin.ModelAdmin):
    """Admin interface for TenantModule model."""

    list_display = [
        "tenant",
        "module_name",
        "is_enabled",
        "version",
        "installed_at",
        "last_used_at",
    ]
    list_filter = ["is_enabled", "module_name", "installed_at"]
    search_fields = ["tenant__name", "module_name"]
    readonly_fields = ["id", "installed_at", "created_at", "updated_at"]


@admin.register(TenantResourceUsage)
class TenantResourceUsageAdmin(admin.ModelAdmin):
    """Admin interface for TenantResourceUsage model."""

    list_display = [
        "tenant",
        "date",
        "active_users",
        "api_calls",
        "storage_used_gb",
        "error_count",
    ]
    list_filter = ["date", "tenant"]
    search_fields = ["tenant__name"]
    readonly_fields = ["id", "created_at", "updated_at"]
    date_hierarchy = "date"


@admin.register(TenantSettings)
class TenantSettingsAdmin(admin.ModelAdmin):
    """Admin interface for TenantSettings model."""

    list_display = ["tenant", "category", "key", "is_encrypted", "updated_at"]
    list_filter = ["category", "is_encrypted", "updated_at"]
    search_fields = ["tenant__name", "category", "key"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(TenantHealthScore)
class TenantHealthScoreAdmin(admin.ModelAdmin):
    """Admin interface for TenantHealthScore model."""

    list_display = ["tenant", "date", "overall_score", "churn_risk", "calculated_at"]
    list_filter = ["date", "calculated_at"]
    search_fields = ["tenant__name"]
    readonly_fields = ["id", "calculated_at", "created_at", "updated_at"]
    date_hierarchy = "date"
