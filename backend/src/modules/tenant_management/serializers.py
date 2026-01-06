"""
Tenant Management Serializers.

DRF serializers for Tenant Management API endpoints.
"""

from rest_framework import serializers
from .models import (
    Tenant,
    TenantModule,
    TenantResourceUsage,
    TenantSettings,
    TenantHealthScore,
)


class TenantSerializer(serializers.ModelSerializer):
    """Tenant serializer for create/update/read operations."""

    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "slug",
            "subdomain",
            "custom_domain",
            "status",
            "subscription_plan_id",
            "trial_ends_at",
            "subscription_start_date",
            "subscription_end_date",
            "primary_contact_name",
            "primary_contact_email",
            "primary_contact_phone",
            "billing_email",
            "technical_email",
            "logo_url",
            "website_url",
            "industry",
            "company_size",
            "tax_id",
            "timezone",
            "default_language",
            "default_currency",
            "fiscal_year_start_month",
            "date_format",
            "time_format",
            "primary_color",
            "secondary_color",
            "accent_color",
            "features_enabled",
            "max_users",
            "max_storage_gb",
            "max_api_calls_per_day",
            "metadata",
            "created_at",
            "updated_at",
            "created_by",
            "onboarded_by",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "created_by"]

    def validate_slug(self, value):
        """Validate slug format."""
        if not value.replace("_", "").replace("-", "").isalnum():
            raise serializers.ValidationError(
                "Slug must contain only alphanumeric characters, hyphens, and underscores."
            )
        return value.lower()

    def validate(self, data):
        """Validate tenant data."""
        # For partial updates, check instance values if not in data
        instance = getattr(self, "instance", None)

        # Ensure subdomain or custom_domain is provided
        subdomain = data.get("subdomain")
        custom_domain = data.get("custom_domain")

        # For partial updates, use instance values if not provided
        if instance:
            if subdomain is None:
                subdomain = instance.subdomain
            if custom_domain is None:
                custom_domain = instance.custom_domain

        if not subdomain and not custom_domain:
            raise serializers.ValidationError(
                "Either subdomain or custom_domain must be provided."
            )

        # Validate trial dates
        trial_ends_at = data.get("trial_ends_at")
        subscription_start_date = data.get("subscription_start_date")

        # For partial updates, use instance values if not provided
        if instance:
            if trial_ends_at is None:
                trial_ends_at = instance.trial_ends_at
            if subscription_start_date is None:
                subscription_start_date = instance.subscription_start_date

        if trial_ends_at and subscription_start_date:
            if trial_ends_at > subscription_start_date:
                raise serializers.ValidationError(
                    "Trial end date must be before subscription start date."
                )

        return data


class TenantModuleSerializer(serializers.ModelSerializer):
    """Tenant module serializer."""

    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = TenantModule
        fields = [
            "id",
            "tenant",
            "tenant_name",
            "module_name",
            "is_enabled",
            "installed_at",
            "installed_by",
            "version",
            "configuration",
            "last_used_at",
            "usage_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "installed_at", "created_at", "updated_at"]


class TenantResourceUsageSerializer(serializers.ModelSerializer):
    """Tenant resource usage serializer."""

    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = TenantResourceUsage
        fields = [
            "id",
            "tenant",
            "tenant_name",
            "date",
            "active_users",
            "api_calls",
            "storage_used_gb",
            "bandwidth_used_gb",
            "email_sent",
            "sms_sent",
            "avg_response_time_ms",
            "error_count",
            "slow_query_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TenantSettingsSerializer(serializers.ModelSerializer):
    """Tenant settings serializer."""

    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = TenantSettings
        fields = [
            "id",
            "tenant",
            "tenant_name",
            "category",
            "key",
            "value",
            "is_encrypted",
            "created_at",
            "updated_at",
            "updated_by",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TenantHealthScoreSerializer(serializers.ModelSerializer):
    """Tenant health score serializer."""

    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = TenantHealthScore
        fields = [
            "id",
            "tenant",
            "tenant_name",
            "date",
            "overall_score",
            "usage_score",
            "performance_score",
            "error_score",
            "engagement_score",
            "churn_risk",
            "at_risk_reasons",
            "calculated_at",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "calculated_at", "created_at", "updated_at"]


class TenantListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for tenant list views."""

    module_count = serializers.SerializerMethodField()
    active_user_count = serializers.SerializerMethodField()
    current_health_score = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "slug",
            "status",
            "subscription_plan_id",
            "trial_ends_at",
            "primary_contact_email",
            "industry",
            "company_size",
            "module_count",
            "active_user_count",
            "current_health_score",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_module_count(self, obj):
        """Get count of enabled modules."""
        return obj.modules.filter(is_enabled=True).count()

    def get_active_user_count(self, obj):
        """Get current active user count from latest resource usage."""
        latest_usage = obj.resource_usage.order_by("-date").first()
        return latest_usage.active_users if latest_usage else 0

    def get_current_health_score(self, obj):
        """Get most recent health score."""
        latest_score = obj.health_scores.order_by("-date").first()
        return latest_score.overall_score if latest_score else None
