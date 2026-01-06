"""
Tenant Management Services

Business logic for tenant lifecycle management, module installation,
resource tracking, and health scoring.

CRITICAL: Platform-level operations - these services manage tenants themselves.
"""

from typing import Optional, Dict, Any
from django.db.models import Sum, Avg
from datetime import date, timedelta

from .models import (
    Tenant,
    TenantModule,
    TenantResourceUsage,
    TenantSettings,
    TenantHealthScore,
)


class TenantManagementService:
    """Business logic for tenant management operations."""

    @staticmethod
    def create_tenant(
        name: str, slug: str, created_by: Optional[str] = None, **kwargs
    ) -> Tenant:
        """
        Create a new tenant with default configuration.

        Args:
            name: Tenant organization name
            slug: URL-safe identifier
            created_by: User ID who created the tenant
            **kwargs: Additional tenant fields

        Returns:
            Created Tenant instance
        """
        tenant = Tenant.objects.create(
            name=name,
            slug=slug,
            created_by=created_by,
            onboarded_by=created_by,
            **kwargs
        )
        return tenant

    @staticmethod
    def activate_tenant(tenant_id: str) -> Tenant:
        """Activate a tenant (change status to ACTIVE)."""
        tenant = Tenant.objects.get(id=tenant_id)
        tenant.status = Tenant.TenantStatus.ACTIVE
        tenant.save()
        return tenant

    @staticmethod
    def suspend_tenant(tenant_id: str) -> Tenant:
        """Suspend a tenant (change status to SUSPENDED)."""
        tenant = Tenant.objects.get(id=tenant_id)
        tenant.status = Tenant.TenantStatus.SUSPENDED
        tenant.save()
        return tenant

    @staticmethod
    def cancel_tenant(tenant_id: str) -> Tenant:
        """Cancel a tenant (change status to CANCELLED)."""
        tenant = Tenant.objects.get(id=tenant_id)
        tenant.status = Tenant.TenantStatus.CANCELLED
        tenant.save()
        return tenant

    @staticmethod
    def archive_tenant(tenant_id: str) -> Tenant:
        """Archive a tenant (change status to ARCHIVED)."""
        tenant = Tenant.objects.get(id=tenant_id)
        tenant.status = Tenant.TenantStatus.ARCHIVED
        tenant.save()
        return tenant

    @staticmethod
    def install_module(
        tenant_id: str,
        module_name: str,
        installed_by: Optional[str] = None,
        version: Optional[str] = None,
        configuration: Optional[Dict[str, Any]] = None,
    ) -> TenantModule:
        """
        Install a module for a tenant.

        Args:
            tenant_id: Tenant ID
            module_name: Module identifier
            installed_by: User ID who installed the module
            version: Module version
            configuration: Module-specific configuration

        Returns:
            TenantModule instance
        """
        tenant = Tenant.objects.get(id=tenant_id)
        tenant_module, created = TenantModule.objects.get_or_create(
            tenant=tenant,
            module_name=module_name,
            defaults={
                "installed_by": installed_by,
                "version": version or "1.0.0",
                "configuration": configuration or {},
                "is_enabled": True,
            },
        )
        if not created:
            # Update existing module
            tenant_module.is_enabled = True
            tenant_module.version = version or tenant_module.version
            if configuration:
                tenant_module.configuration.update(configuration)
            tenant_module.save()
        return tenant_module

    @staticmethod
    def uninstall_module(tenant_id: str, module_name: str) -> None:
        """Uninstall a module for a tenant."""
        tenant = Tenant.objects.get(id=tenant_id)
        TenantModule.objects.filter(tenant=tenant, module_name=module_name).delete()

    @staticmethod
    def enable_module(tenant_id: str, module_name: str) -> TenantModule:
        """Enable a module for a tenant."""
        tenant_module = TenantModule.objects.get(
            tenant_id=tenant_id, module_name=module_name
        )
        tenant_module.is_enabled = True
        tenant_module.save()
        return tenant_module

    @staticmethod
    def disable_module(tenant_id: str, module_name: str) -> TenantModule:
        """Disable a module for a tenant."""
        tenant_module = TenantModule.objects.get(
            tenant_id=tenant_id, module_name=module_name
        )
        tenant_module.is_enabled = False
        tenant_module.save()
        return tenant_module

    @staticmethod
    def record_resource_usage(
        tenant_id: str,
        date: date,
        active_users: int = 0,
        api_calls: int = 0,
        storage_used_gb: float = 0.0,
        bandwidth_used_gb: float = 0.0,
        email_sent: int = 0,
        sms_sent: int = 0,
        avg_response_time_ms: Optional[float] = None,
        error_count: int = 0,
        slow_query_count: int = 0,
    ) -> TenantResourceUsage:
        """
        Record daily resource usage for a tenant.

        Args:
            tenant_id: Tenant ID
            date: Date for this usage record
            active_users: Number of active users
            api_calls: Number of API calls
            storage_used_gb: Storage used in GB
            bandwidth_used_gb: Bandwidth used in GB
            email_sent: Number of emails sent
            sms_sent: Number of SMS sent
            avg_response_time_ms: Average response time in milliseconds
            error_count: Number of errors
            slow_query_count: Number of slow queries

        Returns:
            TenantResourceUsage instance
        """
        tenant = Tenant.objects.get(id=tenant_id)
        usage, created = TenantResourceUsage.objects.update_or_create(
            tenant=tenant,
            date=date,
            defaults={
                "active_users": active_users,
                "api_calls": api_calls,
                "storage_used_gb": storage_used_gb,
                "bandwidth_used_gb": bandwidth_used_gb,
                "email_sent": email_sent,
                "sms_sent": sms_sent,
                "avg_response_time_ms": avg_response_time_ms,
                "error_count": error_count,
                "slow_query_count": slow_query_count,
            },
        )
        return usage

    @staticmethod
    def get_resource_usage_summary(tenant_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get resource usage summary for a tenant over the last N days.

        Args:
            tenant_id: Tenant ID
            days: Number of days to summarize

        Returns:
            Dictionary with usage summary statistics
        """
        tenant = Tenant.objects.get(id=tenant_id)
        date_from = date.today() - timedelta(days=days)

        usage_records = TenantResourceUsage.objects.filter(
            tenant=tenant, date__gte=date_from
        )

        return {
            "tenant_id": tenant_id,
            "tenant_name": tenant.name,
            "period_days": days,
            "date_from": date_from.isoformat(),
            "date_to": date.today().isoformat(),
            "total_api_calls": usage_records.aggregate(Sum("api_calls"))[
                "api_calls__sum"
            ]
            or 0,
            "avg_api_calls_per_day": usage_records.aggregate(Avg("api_calls"))[
                "api_calls__avg"
            ]
            or 0,
            "max_storage_gb": usage_records.aggregate(Sum("storage_used_gb"))[
                "storage_used_gb__sum"
            ]
            or 0,
            "avg_active_users": usage_records.aggregate(Avg("active_users"))[
                "active_users__avg"
            ]
            or 0,
            "total_errors": usage_records.aggregate(Sum("error_count"))[
                "error_count__sum"
            ]
            or 0,
            "avg_response_time_ms": usage_records.aggregate(
                Avg("avg_response_time_ms")
            )["avg_response_time_ms__avg"]
            or None,
        }

    @staticmethod
    def set_tenant_setting(
        tenant_id: str,
        category: str,
        key: str,
        value: Any,
        updated_by: Optional[str] = None,
        is_encrypted: bool = False,
    ) -> TenantSettings:
        """
        Set a tenant setting.

        Args:
            tenant_id: Tenant ID
            category: Setting category
            key: Setting key
            value: Setting value (will be JSON-encoded)
            updated_by: User ID who updated the setting
            is_encrypted: Whether the value is encrypted

        Returns:
            TenantSettings instance
        """
        tenant = Tenant.objects.get(id=tenant_id)
        setting, created = TenantSettings.objects.update_or_create(
            tenant=tenant,
            category=category,
            key=key,
            defaults={
                "value": value,
                "is_encrypted": is_encrypted,
                "updated_by": updated_by,
            },
        )
        return setting

    @staticmethod
    def get_tenant_setting(
        tenant_id: str, category: str, key: str, default: Any = None
    ) -> Any:
        """
        Get a tenant setting value.

        Args:
            tenant_id: Tenant ID
            category: Setting category
            key: Setting key
            default: Default value if setting not found

        Returns:
            Setting value or default
        """
        try:
            tenant = Tenant.objects.get(id=tenant_id)
            setting = TenantSettings.objects.get(
                tenant=tenant, category=category, key=key
            )
            return setting.value
        except (Tenant.DoesNotExist, TenantSettings.DoesNotExist):
            return default

    @staticmethod
    def calculate_health_score(
        tenant_id: str, target_date: Optional[date] = None
    ) -> TenantHealthScore:
        """
        Calculate health score for a tenant.

        Health score is based on:
        - Usage score: Active users, API calls, feature usage
        - Performance score: Response times, error rates
        - Error score: Error count, slow queries
        - Engagement score: User activity, feature adoption

        Args:
            tenant_id: Tenant ID
            target_date: Date to calculate score for (defaults to today)

        Returns:
            TenantHealthScore instance
        """
        if target_date is None:
            target_date = date.today()

        tenant = Tenant.objects.get(id=tenant_id)

        # Get resource usage for the date
        try:
            usage = TenantResourceUsage.objects.get(tenant=tenant, date=target_date)
        except TenantResourceUsage.DoesNotExist:
            # Use latest available usage
            usage = tenant.resource_usage.order_by("-date").first()

        # Calculate component scores (0-100)
        usage_score = 50  # Default
        performance_score = 50
        error_score = 50
        engagement_score = 50

        if usage:
            # Usage score: Based on active users and API calls
            if usage.active_users > 0:
                usage_score = min(100, (usage.active_users / tenant.max_users) * 100)

            # Performance score: Based on response time
            if usage.avg_response_time_ms:
                if usage.avg_response_time_ms < 100:
                    performance_score = 100
                elif usage.avg_response_time_ms < 500:
                    performance_score = 80
                elif usage.avg_response_time_ms < 1000:
                    performance_score = 60
                else:
                    performance_score = 40

            # Error score: Lower is better (inverse)
            if usage.error_count == 0:
                error_score = 100
            elif usage.error_count < 10:
                error_score = 80
            elif usage.error_count < 50:
                error_score = 60
            else:
                error_score = 40

            # Engagement score: Based on API calls
            if usage.api_calls > 0:
                engagement_score = min(100, (usage.api_calls / 10000) * 100)

        # Calculate overall score (weighted average)
        overall_score = int(
            (usage_score * 0.3)
            + (performance_score * 0.3)
            + (error_score * 0.2)
            + (engagement_score * 0.2)
        )

        # Calculate churn risk (inverse of health score)
        churn_risk = max(0, 100 - overall_score)

        # Determine at-risk reasons
        at_risk_reasons = []
        if overall_score < 50:
            at_risk_reasons.append("low_health_score")
        if usage and usage.error_count > 50:
            at_risk_reasons.append("high_error_rate")
        if usage and usage.avg_response_time_ms and usage.avg_response_time_ms > 1000:
            at_risk_reasons.append("slow_performance")
        if usage and usage.active_users == 0:
            at_risk_reasons.append("no_active_users")

        # Create or update health score
        health_score, created = TenantHealthScore.objects.update_or_create(
            tenant=tenant,
            date=target_date,
            defaults={
                "overall_score": overall_score,
                "usage_score": usage_score,
                "performance_score": performance_score,
                "error_score": error_score,
                "engagement_score": engagement_score,
                "churn_risk": churn_risk,
                "at_risk_reasons": at_risk_reasons,
            },
        )

        return health_score

    @staticmethod
    def get_tenant_summary(tenant_id: str) -> Dict[str, Any]:
        """
        Get comprehensive summary for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Dictionary with tenant summary information
        """
        tenant = Tenant.objects.get(id=tenant_id)

        # Get latest resource usage
        latest_usage = tenant.resource_usage.order_by("-date").first()

        # Get latest health score
        latest_health = tenant.health_scores.order_by("-date").first()

        # Get module count
        enabled_modules = tenant.modules.filter(is_enabled=True).count()
        total_modules = tenant.modules.count()

        return {
            "tenant": {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "status": tenant.status,
                "subscription_plan_id": tenant.subscription_plan_id,
            },
            "modules": {
                "enabled": enabled_modules,
                "total": total_modules,
            },
            "resource_usage": (
                {
                    "active_users": latest_usage.active_users if latest_usage else 0,
                    "api_calls_today": latest_usage.api_calls if latest_usage else 0,
                    "storage_used_gb": (
                        float(latest_usage.storage_used_gb) if latest_usage else 0.0
                    ),
                }
                if latest_usage
                else None
            ),
            "health": (
                {
                    "overall_score": (
                        latest_health.overall_score if latest_health else None
                    ),
                    "churn_risk": (
                        float(latest_health.churn_risk) if latest_health else None
                    ),
                    "at_risk_reasons": (
                        latest_health.at_risk_reasons if latest_health else []
                    ),
                }
                if latest_health
                else None
            ),
        }
