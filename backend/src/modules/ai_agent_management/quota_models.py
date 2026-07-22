"""Quota attribution, saturation samples, and tenant emergency controls."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from src.core.access.entitlements import Quota as TenantQuota
from src.core.tenancy.registry import TENANT_SCOPED, tenancy_scope

from .models import AppendOnlyTenantModel, StatefulTenantModel, validate_same_tenant


def generate_uuid() -> str:
    """Preserve the callable referenced by migration 0001."""

    return str(uuid.uuid4())


class QuotaType(models.TextChoices):
    TOKEN_COUNT = "token_count", "Token count"
    REQUEST_COUNT = "request_count", "Request count"
    EXECUTION_TIME = "execution_time", "Execution time"
    TOOL_CALLS = "tool_calls", "Tool calls"
    EXTERNAL_API_CALLS = "external_api_calls", "External API calls"
    DATA_VOLUME = "data_volume", "Data volume"


class QuotaPeriod(models.TextChoices):
    HOURLY = "hourly", "Hourly"
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"


class KillSwitchScope(models.TextChoices):
    TENANT = "tenant", "Tenant"
    SHARD = "shard", "Shard"
    AGENT = "agent", "Agent"


class KillSwitchStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"


@tenancy_scope(TENANT_SCOPED)
class QuotaUsage(AppendOnlyTenantModel):
    resource = models.CharField(max_length=255)
    agent_execution = models.ForeignKey(
        "AgentExecution",
        on_delete=models.PROTECT,
        related_name="quota_usages",
        null=True,
        blank=True,
    )
    usage_value = models.PositiveBigIntegerField()
    remaining_after = models.PositiveBigIntegerField()
    usage_timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ai_quota_usage"
        constraints = [
            models.CheckConstraint(condition=Q(usage_value__gt=0), name="ai_quota_usage_positive_ck"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "resource", "usage_timestamp"), name="ai_quota_use_t_res_idx"),
            models.Index(fields=("tenant_id", "agent_execution", "usage_timestamp"), name="ai_quota_use_t_exec_idx"),
        ]
        ordering = ("-usage_timestamp", "id")

    def clean(self) -> None:
        validate_same_tenant(self, "agent_execution")
        if not self.resource.strip():
            raise ValidationError({"resource": "A quota resource is required."})
        if not isinstance(self.metadata, dict):
            raise ValidationError({"metadata": "Must be a JSON object."})

    def __str__(self) -> str:
        return f"Quota Usage {self.id}: {self.usage_value} {self.resource}"


@tenancy_scope(TENANT_SCOPED)
class ShardSaturation(AppendOnlyTenantModel):
    shard_id = models.CharField(max_length=100)
    saturation_level = models.DecimalField(max_digits=5, decimal_places=4)
    active_agents = models.PositiveIntegerField(default=0)
    active_executions = models.PositiveIntegerField(default=0)
    cpu_usage_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    memory_usage_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    measured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_shard_saturation"
        constraints = [
            models.CheckConstraint(
                condition=Q(saturation_level__gte=Decimal("0"), saturation_level__lte=Decimal("1")),
                name="ai_shard_saturation_ck",
            ),
            models.CheckConstraint(
                condition=Q(cpu_usage_percent__isnull=True) | Q(cpu_usage_percent__gte=0, cpu_usage_percent__lte=100),
                name="ai_shard_cpu_ck",
            ),
            models.CheckConstraint(
                condition=Q(memory_usage_percent__isnull=True)
                | Q(memory_usage_percent__gte=0, memory_usage_percent__lte=100),
                name="ai_shard_memory_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "shard_id", "measured_at"), name="ai_shard_t_shard_idx"),
            models.Index(fields=("tenant_id", "saturation_level", "measured_at"), name="ai_shard_t_level_idx"),
        ]
        ordering = ("-measured_at", "id")

    def __str__(self) -> str:
        return f"Shard {self.shard_id} saturation: {self.saturation_level:.2%}"


@tenancy_scope(TENANT_SCOPED)
class KillSwitch(StatefulTenantModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    scope = models.CharField(max_length=20, choices=KillSwitchScope.choices)
    scope_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=KillSwitchStatus.choices, default=KillSwitchStatus.ACTIVE)
    transition_history = models.JSONField(default=list, blank=True, editable=False)
    reason = models.TextField()
    activated_by = models.UUIDField()
    activated_at = models.DateTimeField(default=timezone.now)
    deactivated_by = models.UUIDField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    state_field = "status"
    terminal_states = frozenset((KillSwitchStatus.INACTIVE,))

    class Meta:
        db_table = "ai_kill_switches"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(scope=KillSwitchScope.TENANT, scope_id__isnull=True)
                    | Q(scope__in=(KillSwitchScope.SHARD, KillSwitchScope.AGENT), scope_id__isnull=False)
                ),
                name="ai_kill_scope_id_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=KillSwitchStatus.ACTIVE, deactivated_by__isnull=True, deactivated_at__isnull=True)
                    | Q(status=KillSwitchStatus.INACTIVE, deactivated_by__isnull=False, deactivated_at__isnull=False)
                ),
                name="ai_kill_deactivate_ck",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "scope", "scope_id"),
                condition=Q(status=KillSwitchStatus.ACTIVE),
                name="ai_kill_t_active_scope_uniq",
                nulls_distinct=False,
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "scope"), name="ai_kill_t_status_idx"),
            models.Index(fields=("tenant_id", "scope", "scope_id"), name="ai_kill_t_scope_idx"),
        ]
        ordering = ("-activated_at", "id")

    @property
    def is_active(self) -> bool:
        """Compatibility projection for callers migrating from the v1 boolean."""

        return self.status == KillSwitchStatus.ACTIVE

    def clean(self) -> None:
        if not isinstance(self.transition_history, list):
            raise ValidationError({"transition_history": "Must be a JSON list."})
        if not self.reason.strip():
            raise ValidationError({"reason": "An activation reason is required."})

    def __str__(self) -> str:
        return f"Kill Switch {self.name} ({self.scope}/{self.status})"


__all__ = [
    "KillSwitch",
    "KillSwitchScope",
    "KillSwitchStatus",
    "QuotaPeriod",
    "QuotaType",
    "QuotaUsage",
    "ShardSaturation",
    "TenantQuota",
]
