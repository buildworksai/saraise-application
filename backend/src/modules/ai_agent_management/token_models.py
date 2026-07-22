"""Immutable token and cost attribution plus recalculable summaries."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from src.core.tenancy.registry import TENANT_SCOPED, tenancy_scope

from .models import AITenantModel, AppendOnlyTenantModel, validate_same_tenant


def generate_uuid() -> str:
    return str(uuid.uuid4())


class CostType(models.TextChoices):
    TOKEN = "token", "Token"
    API_CALL = "api_call", "API call"
    EXECUTION_TIME = "execution_time", "Execution time"
    STORAGE = "storage", "Storage"
    EGRESS = "egress", "Egress"


class CostPeriod(models.TextChoices):
    HOURLY = "hourly", "Hourly"
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"


@tenancy_scope(TENANT_SCOPED)
class TokenUsage(AppendOnlyTenantModel):
    agent_execution = models.ForeignKey("AgentExecution", on_delete=models.PROTECT, related_name="token_usages")
    provider = models.CharField(max_length=100)
    model = models.CharField(max_length=255)
    input_tokens = models.PositiveBigIntegerField(default=0)
    output_tokens = models.PositiveBigIntegerField(default=0)
    total_tokens = models.PositiveBigIntegerField(default=0)
    usage_timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ai_token_usage"
        constraints = [
            models.CheckConstraint(
                condition=Q(total_tokens=F("input_tokens") + F("output_tokens")),
                name="ai_token_total_ck",
            )
        ]
        indexes = [
            models.Index(fields=("tenant_id", "agent_execution", "usage_timestamp"), name="ai_token_t_exec_idx"),
            models.Index(fields=("tenant_id", "provider", "model", "usage_timestamp"), name="ai_token_t_provider_idx"),
        ]
        ordering = ("-usage_timestamp", "id")

    def clean(self) -> None:
        validate_same_tenant(self, "agent_execution")
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValidationError({"total_tokens": "Must equal input_tokens plus output_tokens."})

    def __str__(self) -> str:
        return f"Token Usage {self.id}: {self.total_tokens} ({self.provider}/{self.model})"


@tenancy_scope(TENANT_SCOPED)
class CostRecord(AppendOnlyTenantModel):
    agent_execution = models.ForeignKey(
        "AgentExecution", on_delete=models.PROTECT, related_name="cost_records", null=True, blank=True
    )
    tool_invocation = models.ForeignKey(
        "ToolInvocation", on_delete=models.PROTECT, related_name="cost_records", null=True, blank=True
    )
    module_name = models.CharField(max_length=100, null=True, blank=True)
    cost_type = models.CharField(max_length=30, choices=CostType.choices)
    provider = models.CharField(max_length=100, null=True, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=8)
    currency = models.CharField(max_length=3)
    pricing_version = models.CharField(max_length=100)
    cost_timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ai_cost_records"
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=Decimal("0")), name="ai_cost_amount_ck"),
            models.CheckConstraint(
                condition=Q(agent_execution__isnull=False)
                | Q(tool_invocation__isnull=False)
                | Q(module_name__isnull=False),
                name="ai_cost_attribution_ck",
            ),
            models.CheckConstraint(condition=Q(currency__regex=r"^[A-Z]{3}$"), name="ai_cost_currency_ck"),
            models.CheckConstraint(condition=~Q(pricing_version=""), name="ai_cost_pricing_version_ck"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "agent_execution", "cost_timestamp"), name="ai_cost_t_exec_idx"),
            models.Index(fields=("tenant_id", "module_name", "cost_timestamp"), name="ai_cost_t_module_idx"),
            models.Index(fields=("tenant_id", "cost_type", "provider", "cost_timestamp"), name="ai_cost_t_type_idx"),
        ]
        ordering = ("-cost_timestamp", "id")

    def clean(self) -> None:
        validate_same_tenant(self, "agent_execution", "tool_invocation")
        self.currency = self.currency.strip().upper()
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValidationError({"currency": "Use a three-letter ISO currency code."})
        if self.module_name is not None and not self.module_name.strip():
            self.module_name = None

    def __str__(self) -> str:
        return f"Cost {self.id}: {self.amount} {self.currency} ({self.cost_type})"


@tenancy_scope(TENANT_SCOPED)
class CostSummary(AITenantModel):
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    period_type = models.CharField(max_length=20, choices=CostPeriod.choices)
    total_cost = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("0"))
    currency = models.CharField(max_length=3)
    cost_by_type = models.JSONField(default=dict, blank=True)
    cost_by_module = models.JSONField(default=dict, blank=True)
    cost_by_provider = models.JSONField(default=dict, blank=True)
    total_tokens = models.PositiveBigIntegerField(default=0)
    total_executions = models.PositiveBigIntegerField(default=0)
    calculated_at = models.DateTimeField()

    class Meta:
        db_table = "ai_cost_summaries"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "period_start", "period_end", "period_type", "currency"),
                name="ai_cost_sum_t_period_uniq",
            ),
            models.CheckConstraint(condition=Q(period_end__gt=F("period_start")), name="ai_cost_sum_period_ck"),
            models.CheckConstraint(condition=Q(total_cost__gte=Decimal("0")), name="ai_cost_sum_total_ck"),
            models.CheckConstraint(condition=Q(currency__regex=r"^[A-Z]{3}$"), name="ai_cost_sum_currency_ck"),
        ]
        indexes = [models.Index(fields=("tenant_id", "period_type", "period_start"), name="ai_cost_sum_t_period_idx")]
        ordering = ("-period_start", "id")

    def clean(self) -> None:
        self.currency = self.currency.strip().upper()
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValidationError({"currency": "Use a three-letter ISO currency code."})
        for field in ("cost_by_type", "cost_by_module", "cost_by_provider"):
            if not isinstance(getattr(self, field), dict):
                raise ValidationError({field: "Must be a JSON object."})

    def __str__(self) -> str:
        return f"Cost Summary {self.id}: {self.total_cost} {self.currency} ({self.period_type})"
