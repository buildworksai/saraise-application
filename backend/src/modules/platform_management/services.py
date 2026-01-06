"""
Platform Management Business Logic
"""

from typing import Optional, Union
import uuid
from django.contrib.auth import get_user_model
from django.core.cache import cache
from .models import PlatformSetting, FeatureFlag, PlatformAuditEvent, PlatformMetrics


class PlatformManagementService:
    """Business logic for platform management operations."""

    @staticmethod
    def get_setting(key: str, tenant_id: Optional[Union[str, uuid.UUID]] = None, default=None):
        """Get a platform setting by key."""
        try:
            if tenant_id:
                # Convert string to UUID if needed
                if isinstance(tenant_id, str):
                    tenant_id = uuid.UUID(tenant_id)
                
                # Try tenant-specific first
                setting = PlatformSetting.objects.filter(
                    tenant_id=tenant_id, key=key
                ).first()
                if setting:
                    return setting.value

            # Fall back to platform-wide
            setting = PlatformSetting.objects.filter(
                tenant_id__isnull=True, key=key
            ).first()
            return setting.value if setting else default
        except Exception:
            return default

    @staticmethod
    def is_feature_enabled(
        name: str,
        tenant_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None
    ) -> bool:
        """Check if a feature flag is enabled."""
        try:
            flag = None

            # Check tenant-specific flag first
            if tenant_id:
                if isinstance(tenant_id, str):
                    tenant_id = uuid.UUID(tenant_id)
                flag = FeatureFlag.objects.filter(
                    tenant_id=tenant_id, name=name
                ).first()

            # Fall back to platform-wide
            if not flag:
                flag = FeatureFlag.objects.filter(
                    tenant_id__isnull=True, name=name
                ).first()

            if not flag:
                return False

            if not flag.enabled:
                return False

            # Check rollout percentage
            if flag.rollout_percentage < 100 and user_id:
                # Simple hash-based rollout
                user_id_str = str(user_id)
                user_hash = hash(user_id_str) % 100
                return user_hash < flag.rollout_percentage

            return flag.enabled
        except Exception:
            return False

    @staticmethod
    def log_audit_event(
        action: str,
        actor_id: Union[str, uuid.UUID],
        resource_type: str,
        resource_id: Optional[Union[str, uuid.UUID]] = None,
        tenant_id: Optional[Union[str, uuid.UUID]] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None
    ) -> PlatformAuditEvent:
        """Log an immutable audit event."""
        # Convert string IDs to UUID if needed
        if isinstance(actor_id, str):
            actor_id = uuid.UUID(actor_id)
        if resource_id and isinstance(resource_id, str):
            resource_id = uuid.UUID(resource_id)
        if tenant_id and isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id)
        
        return PlatformAuditEvent.objects.create(
            action=action,
            actor_type='user',
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            tenant_id=tenant_id,
            details=details or {},
            ip_address=ip_address
        )


class AnalyticsService:
    """Aggregate platform metrics from cache and database."""

    def get_api_metrics(self) -> dict:
        """Collect API metrics from cache."""
        from django.utils import timezone

        date_key = timezone.now().strftime('%Y-%m-%d')
        cache_key_prefix = f'api_metrics:{date_key}'

        total = cache.get(f'{cache_key_prefix}:total', 0) or 0
        errors = cache.get(f'{cache_key_prefix}:errors', 0) or 0
        response_times = cache.get(f'{cache_key_prefix}:response_times', []) or []

        if response_times:
            sorted_times = sorted(response_times)
            avg = sum(sorted_times) / len(sorted_times)
        else:
            avg = 0

        error_rate = (errors / total) * 100 if total else 0

        # Mapped to frontend interface: ApiMetrics
        return {
            "total_api_calls_30d": total,
            "error_rate_percent": round(error_rate, 2),
            "average_response_time_ms": round(avg, 2),
        }

    def get_tenant_metrics(self) -> dict:
        """Collect tenant metrics from tenant management."""
        try:
            from src.modules.tenant_management.models import Tenant
        except Exception:
            return {
                "total": 0, 
                "active_30d": 0, 
                "new_this_month": 0, 
                "churned_this_month": 0
            }

        total = Tenant.objects.count()
        active = Tenant.objects.filter(status=Tenant.TenantStatus.ACTIVE).count()
        
        # Placeholder for time-based metrics until history tracking implemented
        return {
            "total": total,
            "active_30d": active,
            "new_this_month": 0,
            "churned_this_month": 0,
        }

    def get_user_metrics(self) -> dict:
        """Collect user metrics from auth user model."""
        user_model = get_user_model()
        total = user_model.objects.count()
        
        # Placeholder for activity metrics
        return {
            "total": total,
            "active_7d": 0,
            "active_30d": 0,
            "new_this_month": 0,
        }

    def get_revenue_metrics(self) -> dict:
        """Placeholder revenue metrics until billing module is wired."""
        return {
            "mrr": 0,
            "arr": 0,
            "average_revenue_per_tenant": 0,
        }

    def get_resource_utilization(self) -> dict:
        """Placeholder resource utilization metrics."""
        return {
            "avg_cpu_percent": 0,
            "avg_memory_percent": 0,
            "avg_db_connections": 0,
        }

    def get_metrics(self, metric_type: str, time_range: str) -> dict:
        """Return metrics payload based on requested metric type."""
        if metric_type == PlatformMetrics.MetricType.TENANT:
            return self.get_tenant_metrics()
        if metric_type == PlatformMetrics.MetricType.USER:
            return self.get_user_metrics()
        if metric_type == PlatformMetrics.MetricType.API:
            return self.get_api_metrics()
        if metric_type == PlatformMetrics.MetricType.REVENUE:
            return self.get_revenue_metrics()
        if metric_type == PlatformMetrics.MetricType.RESOURCE:
            return self.get_resource_utilization()

        return {
            "tenant_metrics": self.get_tenant_metrics(),
            "user_metrics": self.get_user_metrics(),
            "api_metrics": self.get_api_metrics(),
            "revenue_metrics": self.get_revenue_metrics(),
            "resource_utilization": self.get_resource_utilization(),
            "time_range": time_range,
        }

    def save_metrics(
        self,
        metric_type: str,
        time_range: str,
        created_by: Optional[Union[str, uuid.UUID]] = None,
    ) -> PlatformMetrics:
        """Persist a metrics snapshot."""
        metrics_data = self.get_metrics(metric_type=metric_type, time_range=time_range)
        if created_by and isinstance(created_by, str):
            created_by = uuid.UUID(created_by)

        return PlatformMetrics.objects.create(
            metric_type=metric_type,
            time_range=time_range,
            metrics_data=metrics_data,
            created_by=created_by,
        )
