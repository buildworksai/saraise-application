"""Validate the expanded UUID and lifecycle projection before contraction."""

from __future__ import annotations

import uuid

from django.db import migrations

BATCH_SIZE = 500


def validate_backfill(apps, schema_editor):
    """Fail closed if any canonical identity or deterministic key is incomplete."""

    model_names = (
        "Agent",
        "AgentExecution",
        "AgentSchedulerTask",
        "ApprovalRequest",
        "AuditEvent",
        "AuditTrail",
        "AuditTrailEvent",
        "CostRecord",
        "CostSummary",
        "EgressRequest",
        "EgressRule",
        "KillSwitch",
        "QuotaUsage",
        "Secret",
        "SecretAccess",
        "ShardSaturation",
        "SoDPolicy",
        "SoDViolation",
        "TokenUsage",
        "Tool",
        "ToolInvocation",
    )
    for model_name in model_names:
        Model = apps.get_model("ai_agent_management", model_name)
        for record_id, tenant_id in Model.objects.values_list("id", "tenant_id").iterator(chunk_size=BATCH_SIZE):
            try:
                uuid.UUID(str(record_id))
                uuid.UUID(str(tenant_id))
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValueError(f"Malformed UUID in {model_name} identity") from exc

    Execution = apps.get_model("ai_agent_management", "AgentExecution")
    if Execution.objects.filter(async_job_id__isnull=True).exists():
        raise ValueError("Execution async-job UUID backfill is incomplete")
    if Execution.objects.filter(idempotency_key="legacy").exists():
        raise ValueError("Execution idempotency-key backfill is incomplete")

    Schedule = apps.get_model("ai_agent_management", "AgentSchedulerTask")
    if Schedule.objects.filter(idempotency_key="legacy").exists():
        raise ValueError("Schedule idempotency-key backfill is incomplete")

    Invocation = apps.get_model("ai_agent_management", "ToolInvocation")
    if Invocation.objects.filter(idempotency_key="legacy").exists():
        raise ValueError("Tool invocation idempotency-key backfill is incomplete")


class Migration(migrations.Migration):
    dependencies = [("ai_agent_management", "0003_expand_foundation_schema")]

    operations = [
        migrations.RunPython(validate_backfill, validate_backfill),
    ]
