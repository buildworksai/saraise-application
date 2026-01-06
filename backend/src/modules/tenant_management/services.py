"""
Tenant Management Services

⚠️ ARCHITECTURAL NOTE: This module is READ-ONLY in the Application layer.
Tenant lifecycle operations (create, suspend, terminate, module installation)
MUST be performed via Control Plane services in saraise-platform/saraise-control-plane/.

This service provides read-only operations for:
- Reading tenant information for filtering
- Reading tenant status for authorization
- Reading tenant modules for access control
- Reading tenant resource usage for display
- Reading tenant health scores for monitoring

CRITICAL: Tenant lifecycle operations are FORBIDDEN here - use Control Plane APIs.
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
    """
    READ-ONLY business logic for tenant information.
    
    ⚠️ ARCHITECTURAL ENFORCEMENT: All lifecycle operations removed.
    Tenant lifecycle MUST be performed via Control Plane services.
    """

    # ⚠️ ARCHITECTURAL ENFORCEMENT: Lifecycle operations removed
    # - create_tenant() → Use Control Plane
    # - activate_tenant() → Use Control Plane
    # - suspend_tenant() → Use Control Plane
    # - cancel_tenant() → Use Control Plane
    # - archive_tenant() → Use Control Plane
    # - install_module() → Use Control Plane
    # - uninstall_module() → Use Control Plane
    # - enable_module() → Use Control Plane
    # - disable_module() → Use Control Plane

    # ⚠️ ARCHITECTURAL NOTE: record_resource_usage() kept for metrics collection
    # This is data persistence (metrics), not tenant lifecycle management.
    # Metrics recording is acceptable in Runtime Plane.
    
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
        
        NOTE: This is metrics/data persistence, not tenant lifecycle management.
        Metrics recording is acceptable in Runtime Plane.

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

    # ⚠️ ARCHITECTURAL ENFORCEMENT: Setting management removed
    # - set_tenant_setting() → Use Control Plane

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

    # ⚠️ ARCHITECTURAL NOTE: calculate_health_score() kept for analytics
    # This is analytics/metrics calculation, not tenant lifecycle management.
    # Health score calculation is acceptable in Runtime Plane.
    
    @staticmethod
    def calculate_health_score(
        tenant_id: str, target_date: Optional[date] = None
    ) -> TenantHealthScore:
        """
        Calculate health score for a tenant.
        
        NOTE: This is analytics/metrics calculation, not tenant lifecycle management.
        Health score calculation is acceptable in Runtime Plane.

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
