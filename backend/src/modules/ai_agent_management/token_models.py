"""Token Metering Models.

Database models for token counting and cost attribution.
Task: 402.3 - Token Metering & Cost Attribution
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


class TokenUsage(TenantBaseModel):
    """Token usage tracking model.

    Tracks token consumption for agent executions.
    """

    id = models.CharField(
        max_length=36, primary_key=True, default=generate_uuid
    )
    agent_execution = models.ForeignKey(
        "AgentExecution",
        on_delete=models.CASCADE,
        related_name="token_usages",
        db_index=True,
    )
    provider = models.CharField(
        max_length=50,
        db_index=True,
        help_text="AI provider (openai, anthropic, etc.)",
    )
    model = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Model name (gpt-4, claude-3, etc.)",
    )
    input_tokens = models.IntegerField(
        default=0, help_text="Input tokens consumed"
    )
    output_tokens = models.IntegerField(
        default=0, help_text="Output tokens generated"
    )
    total_tokens = models.IntegerField(
        default=0, help_text="Total tokens (input + output)"
    )
    usage_timestamp = models.DateTimeField(
        auto_now_add=True, db_index=True
    )
    metadata = models.JSONField(
        default=dict, help_text="Usage metadata"
    )

    class Meta:
        db_table = "ai_token_usage"
        indexes = [
            models.Index(fields=["tenant_id", "agent_execution_id"]),
            models.Index(fields=["tenant_id", "provider"]),
            models.Index(fields=["tenant_id", "model"]),
            models.Index(fields=["tenant_id", "usage_timestamp"]),
        ]

    def __str__(self) -> str:
        return f"Token Usage {self.id}: {self.total_tokens} tokens ({self.provider}/{self.model})"


class CostRecord(TenantBaseModel):
    """Cost record model.

    Tracks cost attribution for AI operations.
    """

    id = models.CharField(
        max_length=36, primary_key=True, default=generate_uuid
    )
    agent_execution = models.ForeignKey(
        "AgentExecution",
        on_delete=models.CASCADE,
        related_name="cost_records",
        null=True,
        blank=True,
        db_index=True,
    )
    tool_invocation = models.ForeignKey(
        "ToolInvocation",
        on_delete=models.CASCADE,
        related_name="cost_records",
        null=True,
        blank=True,
        db_index=True,
    )
    module_name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="Module that incurred the cost",
    )
    cost_type = models.CharField(
        max_length=50,
        choices=[
            ("token", "Token Cost"),
            ("api_call", "API Call Cost"),
            ("execution_time", "Execution Time Cost"),
            ("storage", "Storage Cost"),
            ("egress", "Egress Cost"),
        ],
        db_index=True,
        help_text="Type of cost",
    )
    provider = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        help_text="Cost provider (openai, anthropic, etc.)",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        help_text="Cost amount",
    )
    currency = models.CharField(
        max_length=3,
        default="USD",
        help_text="Currency code",
    )
    cost_timestamp = models.DateTimeField(
        auto_now_add=True, db_index=True
    )
    metadata = models.JSONField(
        default=dict, help_text="Cost metadata"
    )

    class Meta:
        db_table = "ai_cost_records"
        indexes = [
            models.Index(fields=["tenant_id", "agent_execution_id"]),
            models.Index(fields=["tenant_id", "module_name"]),
            models.Index(fields=["tenant_id", "cost_type"]),
            models.Index(fields=["tenant_id", "provider"]),
            models.Index(fields=["tenant_id", "cost_timestamp"]),
        ]

    def __str__(self) -> str:
        return f"Cost {self.id}: {self.amount} {self.currency} ({self.cost_type})"


class CostSummary(TenantBaseModel):
    """Cost summary model.

    Aggregated cost summaries for reporting.
    """

    id = models.CharField(
        max_length=36, primary_key=True, default=generate_uuid
    )
    period_start = models.DateTimeField(
        db_index=True, help_text="Period start time"
    )
    period_end = models.DateTimeField(
        db_index=True, help_text="Period end time"
    )
    period_type = models.CharField(
        max_length=20,
        choices=[
            ("hourly", "Hourly"),
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
        ],
        db_index=True,
        help_text="Period type",
    )
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        help_text="Total cost for period",
    )
    currency = models.CharField(
        max_length=3,
        default="USD",
        help_text="Currency code",
    )
    cost_by_type = models.JSONField(
        default=dict,
        help_text="Cost breakdown by type",
    )
    cost_by_module = models.JSONField(
        default=dict,
        help_text="Cost breakdown by module",
    )
    cost_by_provider = models.JSONField(
        default=dict,
        help_text="Cost breakdown by provider",
    )
    total_tokens = models.BigIntegerField(
        default=0, help_text="Total tokens consumed"
    )
    total_executions = models.IntegerField(
        default=0, help_text="Total agent executions"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_cost_summaries"
        indexes = [
            models.Index(fields=["tenant_id", "period_start"]),
            models.Index(fields=["tenant_id", "period_end"]),
            models.Index(fields=["tenant_id", "period_type"]),
        ]
        unique_together = [["tenant_id", "period_start", "period_end", "period_type"]]

    def __str__(self) -> str:
        return f"Cost Summary {self.id}: {self.total_cost} {self.currency} ({self.period_type})"

