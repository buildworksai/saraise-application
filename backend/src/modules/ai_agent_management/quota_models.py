"""AI Quota Models.

Database models for quota tracking and kill switches.
Task: 402.2 - AI Quota Enforcement
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone
from typing import Optional, Dict, Any
import uuid

from .models import TenantBaseModel


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class QuotaType(models.TextChoices):
    """Quota type enumeration."""

    TOKEN_COUNT = "token_count", "Token Count"
    REQUEST_COUNT = "request_count", "Request Count"
    EXECUTION_TIME = "execution_time", "Execution Time (seconds)"
    TOOL_CALLS = "tool_calls", "Tool Calls"
    EXTERNAL_API_CALLS = "external_api_calls", "External API Calls"
    DATA_VOLUME = "data_volume", "Data Volume (bytes)"


class QuotaPeriod(models.TextChoices):
    """Quota period enumeration."""

    HOURLY = "hourly", "Hourly"
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"


class TenantQuota(TenantBaseModel):
    """Tenant-level quota definition model."""

    id = models.CharField(
        max_length=36, primary_key=True, default=generate_uuid
    )
    quota_type = models.CharField(
        max_length=50,
        choices=QuotaType.choices,
        db_index=True,
        help_text="Type of quota",
    )
    period = models.CharField(
        max_length=20,
        choices=QuotaPeriod.choices,
        db_index=True,
        help_text="Quota period",
    )
    limit_value = models.BigIntegerField(
        help_text="Quota limit value"
    )
    current_usage = models.BigIntegerField(
        default=0,
        help_text="Current usage in this period",
    )
    reset_at = models.DateTimeField(
        db_index=True,
        help_text="When quota resets",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ai_tenant_quotas"
        indexes = [
            models.Index(fields=["tenant_id", "quota_type"]),
            models.Index(fields=["tenant_id", "period"]),
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["tenant_id", "reset_at"]),
        ]
        unique_together = [["tenant_id", "quota_type", "period"]]

    def __str__(self) -> str:
        return f"Quota {self.quota_type} ({self.period}): {self.current_usage}/{self.limit_value}"


class QuotaUsage(TenantBaseModel):
    """Quota usage tracking model."""

    id = models.CharField(
        max_length=36, primary_key=True, default=generate_uuid
    )
    quota = models.ForeignKey(
        TenantQuota,
        on_delete=models.CASCADE,
        related_name="usage_records",
        db_index=True,
    )
    agent_execution = models.ForeignKey(
        "AgentExecution",
        on_delete=models.CASCADE,
        related_name="quota_usages",
        null=True,
        blank=True,
        db_index=True,
    )
    usage_value = models.BigIntegerField(
        help_text="Amount of quota used"
    )
    usage_timestamp = models.DateTimeField(
        auto_now_add=True, db_index=True
    )
    metadata = models.JSONField(
        default=dict, help_text="Usage metadata"
    )

    class Meta:
        db_table = "ai_quota_usage"
        indexes = [
            models.Index(fields=["tenant_id", "quota_id"]),
            models.Index(fields=["tenant_id", "agent_execution_id"]),
            models.Index(fields=["tenant_id", "usage_timestamp"]),
        ]

    def __str__(self) -> str:
        return f"Quota Usage {self.id}: {self.usage_value}"


class ShardSaturation(TenantBaseModel):
    """Shard-level saturation monitoring model."""

    id = models.CharField(
        max_length=36, primary_key=True, default=generate_uuid
    )
    shard_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Shard identifier",
    )
    saturation_level = models.FloatField(
        db_index=True,
        help_text="Saturation level (0.0 to 1.0)",
    )
    active_agents = models.IntegerField(
        default=0,
        help_text="Number of active agents",
    )
    active_executions = models.IntegerField(
        default=0,
        help_text="Number of active executions",
    )
    cpu_usage_percent = models.FloatField(
        null=True,
        blank=True,
        help_text="CPU usage percentage",
    )
    memory_usage_percent = models.FloatField(
        null=True,
        blank=True,
        help_text="Memory usage percentage",
    )
    measured_at = models.DateTimeField(
        auto_now_add=True, db_index=True
    )

    class Meta:
        db_table = "ai_shard_saturation"
        indexes = [
            models.Index(fields=["tenant_id", "shard_id"]),
            models.Index(fields=["tenant_id", "saturation_level"]),
            models.Index(fields=["tenant_id", "measured_at"]),
        ]

    def __str__(self) -> str:
        return f"Shard {self.shard_id} saturation: {self.saturation_level:.2%}"


class KillSwitch(TenantBaseModel):
    """Kill switch model.

    Global or tenant-specific kill switches for AI agent execution.
    """

    id = models.CharField(
        max_length=36, primary_key=True, default=generate_uuid
    )
    name = models.CharField(
        max_length=255, db_index=True, help_text="Kill switch name"
    )
    description = models.TextField(
        blank=True, help_text="Kill switch description"
    )
    scope = models.CharField(
        max_length=50,
        choices=[
            ("global", "Global"),
            ("tenant", "Tenant"),
            ("shard", "Shard"),
            ("agent", "Agent"),
        ],
        db_index=True,
        help_text="Kill switch scope",
    )
    scope_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="Scope identifier (tenant_id, shard_id, agent_id)",
    )
    is_active = models.BooleanField(
        default=True, db_index=True, help_text="Whether kill switch is active"
    )
    reason = models.TextField(
        blank=True, help_text="Reason for kill switch activation"
    )
    activated_by = models.CharField(
        max_length=36, db_index=True, help_text="User who activated kill switch"
    )
    activated_at = models.DateTimeField(
        auto_now_add=True, db_index=True
    )
    deactivated_at = models.DateTimeField(
        null=True, blank=True, help_text="When kill switch was deactivated"
    )

    class Meta:
        db_table = "ai_kill_switches"
        indexes = [
            models.Index(fields=["tenant_id", "scope"]),
            models.Index(fields=["tenant_id", "scope_id"]),
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["scope", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"Kill Switch {self.name} ({self.scope})"

