"""
Platform Management Models
Implements: Platform settings, feature flags, health checks, audit events

Architecture Compliance:
- ✅ Django ORM
- ✅ tenant_id for tenant-specific settings
- ✅ Indexes on frequently queried fields
"""

from django.db import models
import uuid


def generate_uuid():
    """Generate UUID string for model primary keys (for migration compatibility)."""
    return str(uuid.uuid4())


class PlatformSetting(models.Model):
    """Platform-wide or tenant-specific configuration settings."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, null=True, blank=True)  # null = platform-wide

    key = models.CharField(max_length=255)
    value = models.TextField()
    category = models.CharField(max_length=100, default='general')
    description = models.TextField(blank=True)
    is_secret = models.BooleanField(default=False)
    data_type = models.CharField(
        max_length=20,
        choices=[
            ('string', 'String'),
            ('integer', 'Integer'),
            ('boolean', 'Boolean'),
            ('json', 'JSON'),
        ],
        default='string'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.UUIDField(null=True, blank=True)
    updated_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'platform_settings'
        unique_together = [['tenant_id', 'key']]
        indexes = [
            models.Index(fields=['tenant_id', 'category']),
            models.Index(fields=['key']),
        ]

    def __str__(self):
        return f"{self.key}={self.value[:50]}"


class FeatureFlag(models.Model):
    """Feature flags for gradual rollout and A/B testing."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, null=True, blank=True)  # null = platform-wide

    name = models.CharField(max_length=255)
    enabled = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    rollout_percentage = models.IntegerField(default=100)  # 0-100%

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'platform_feature_flags'
        unique_together = [['tenant_id', 'name']]
        indexes = [
            models.Index(fields=['tenant_id', 'enabled']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return f"{self.name}: {'ON' if self.enabled else 'OFF'}"


class SystemHealth(models.Model):
    """Health check results for platform services."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    service_name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=[
            ('healthy', 'Healthy'),
            ('degraded', 'Degraded'),
            ('unhealthy', 'Unhealthy'),
        ],
        default='healthy'
    )
    last_check = models.DateTimeField(auto_now=True)
    response_time_ms = models.IntegerField(null=True, blank=True)
    details = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'platform_system_health'
        indexes = [
            models.Index(fields=['service_name', 'status']),
            models.Index(fields=['last_check']),
        ]

    def __str__(self):
        return f"{self.service_name}: {self.status}"


class PlatformAuditEvent(models.Model):
    """
    Immutable audit log for platform operations.
    
    CRITICAL: This model is APPEND-ONLY. Updates and deletes are forbidden.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, null=True, blank=True)

    action = models.CharField(max_length=100)
    actor_type = models.CharField(max_length=20)  # user, system, agent
    actor_id = models.UUIDField()
    resource_type = models.CharField(max_length=100)
    resource_id = models.UUIDField(null=True, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    details = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        db_table = 'platform_audit_events'
        indexes = [
            models.Index(fields=['tenant_id', 'timestamp']),
            models.Index(fields=['actor_id', 'timestamp']),
            models.Index(fields=['resource_type', 'resource_id']),
        ]
        # CRITICAL: No update/delete allowed
        managed = True

    def save(self, *args, **kwargs):
        if self.pk and PlatformAuditEvent.objects.filter(pk=self.pk).exists():
            raise ValueError("Audit events are immutable - updates forbidden")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit events are immutable - deletes forbidden")

    def __str__(self):
        return f"{self.action} by {self.actor_id} at {self.timestamp}"


class PlatformMetrics(models.Model):
    """Platform metrics snapshots for reporting and dashboards."""

    class MetricType(models.TextChoices):
        TENANT = "tenant_metrics", "Tenant Metrics"
        USER = "user_metrics", "User Metrics"
        API = "api_metrics", "API Metrics"
        REVENUE = "revenue_metrics", "Revenue Metrics"
        RESOURCE = "resource_utilization", "Resource Utilization"
        COMPLETE = "complete", "Complete Metrics"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    metric_type = models.CharField(max_length=50, choices=MetricType.choices)
    time_range = models.CharField(max_length=20, default="30d")
    metrics_data = models.JSONField(default=dict)
    recorded_at = models.DateTimeField(auto_now_add=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.UUIDField(null=True, blank=True)
    updated_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "platform_metrics"
        indexes = [
            models.Index(fields=["metric_type", "recorded_at"]),
            models.Index(fields=["time_range", "recorded_at"]),
        ]

    def __str__(self):
        return f"{self.metric_type} ({self.time_range})"
