"""Business-engine coverage for definitions, schedules and durable execution."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, OutboxEvent

from ..models import (
    OrchestrationEvent,
    OrchestrationNode,
    OrchestrationRun,
    OrchestrationSchedule,
    OrchestrationTaskRun,
    RetryAttempt,
)
from ..node_registry import (
    CORE_CAPABILITY,
    CommitState,
    NodeDescriptor,
    NodeExecutionContext,
    NodeExecutionResult,
    RetrySafety,
    register_node,
    unregister_node,
)
from ..services import (
    CronExpression,
    DefinitionService,
    ExecutionService,
    IdempotencyConflictError,
    ScheduleService,
    ServiceValidationError,
    StateConflictError,
)

pytestmark = pytest.mark.django_db


def _published_graph(tenant_id: uuid.UUID, actor_id: uuid.UUID, *, key: str = "order-import"):
    definition = DefinitionService.create_definition(
        tenant_id,
        actor_id,
        {
            "key": key,
            "name": "Order import",
            "input_schema": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
                "additionalProperties": False,
            },
            "output_schema": {"type": "object", "additionalProperties": True},
        },
    )
    node = DefinitionService.add_node(
        tenant_id,
        definition.id,
        actor_id,
        {
            "key": "load",
            "name": "Load order",
            "node_type": "internal",
            "handler_key": "core.passthrough",
            "config": {},
            "input_mapping": {"order_id": "$input.order_id"},
        },
    )
    published = DefinitionService.publish(tenant_id, definition.id, actor_id, "publish-1")
    return published, node


def _descriptor(handler_key: str, *, retry_safety: RetrySafety = RetrySafety.IDEMPOTENT) -> NodeDescriptor:
    object_schema = {"type": "object", "additionalProperties": True}
    return NodeDescriptor(
        key=handler_key,
        display_name="Test executor",
        category="Tests",
        description="Deterministic orchestration service test executor",
        configuration_schema={"type": "object", "additionalProperties": False},
        input_schema=object_schema,
        output_schema=object_schema,
        icon_key="test",
        capability=CORE_CAPABILITY,
        source_module="automation_orchestration",
        retry_safety=retry_safety,
    )


def _published_custom_graph(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    handler_key: str,
    *,
    max_attempts: int = 3,
    retry_initial_delay_seconds: int = 1,
):
    definition = DefinitionService.create_definition(
        tenant_id,
        actor_id,
        {
            "key": f"graph-{uuid.uuid4().hex[:12]}",
            "name": "Custom graph",
            "input_schema": {"type": "object", "additionalProperties": True},
            "output_schema": {"type": "object", "additionalProperties": True},
        },
    )
    node = DefinitionService.add_node(
        tenant_id,
        definition.id,
        actor_id,
        {
            "key": "root",
            "name": "Root",
            "node_type": "internal",
            "handler_key": handler_key,
            "max_attempts": max_attempts,
            "retry_initial_delay_seconds": retry_initial_delay_seconds,
            "retry_max_delay_seconds": retry_initial_delay_seconds,
        },
    )
    return DefinitionService.publish(tenant_id, definition.id, actor_id, f"publish-{uuid.uuid4()}"), node


def test_create_definition_accepts_required_input_schema_and_is_tenant_scoped() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    definition = DefinitionService.create_definition(
        tenant_id,
        actor_id,
        {
            "key": "required-input",
            "name": "Required input",
            "input_schema": {
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "string"}},
            },
        },
    )
    assert definition.tenant_id == tenant_id
    assert definition.status == "draft"
    assert OrchestrationEvent.objects.for_tenant(tenant_id).filter(event_type="definition.created").exists()
    with pytest.raises(ObjectDoesNotExist):
        DefinitionService.update_draft(uuid.uuid4(), definition.id, actor_id, {"name": "No"}, "cross-tenant")


def test_node_edit_increments_revision_and_unknown_handler_is_rejected() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    definition = DefinitionService.create_definition(tenant_id, actor_id, {"key": "graph", "name": "Graph"})
    with pytest.raises(ServiceValidationError, match="registered"):
        DefinitionService.add_node(
            tenant_id,
            definition.id,
            actor_id,
            {"key": "missing", "name": "Missing", "node_type": "extension", "handler_key": "missing.node"},
        )
    node = DefinitionService.add_node(
        tenant_id,
        definition.id,
        actor_id,
        {"key": "root", "name": "Root", "node_type": "internal", "handler_key": "core.passthrough"},
    )
    definition.refresh_from_db()
    assert definition.graph_revision == 2
    DefinitionService.update_node(tenant_id, node.id, actor_id, {"name": "Renamed"})
    definition.refresh_from_db()
    assert definition.graph_revision == 3


def test_cycle_is_rejected_and_rolled_back() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    definition = DefinitionService.create_definition(tenant_id, actor_id, {"key": "cycle", "name": "Cycle"})
    one = DefinitionService.add_node(
        tenant_id,
        definition.id,
        actor_id,
        {"key": "one", "name": "One", "node_type": "internal", "handler_key": "core.passthrough"},
    )
    two = DefinitionService.add_node(
        tenant_id,
        definition.id,
        actor_id,
        {"key": "two", "name": "Two", "node_type": "internal", "handler_key": "core.passthrough"},
    )
    DefinitionService.add_edge(
        tenant_id,
        definition.id,
        actor_id,
        {"upstream_node_id": one.id, "downstream_node_id": two.id},
    )
    with pytest.raises(ServiceValidationError, match="invalid graph"):
        DefinitionService.add_edge(
            tenant_id,
            definition.id,
            actor_id,
            {"upstream_node_id": two.id, "downstream_node_id": one.id},
        )
    assert definition.edges.filter(is_deleted=False).count() == 1


def test_publish_pins_contract_clone_preserves_graph_and_retire_is_guarded() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, _ = _published_graph(tenant_id, actor_id)
    assert published.contract_snapshot["node_contracts"]["load"]["handler_key"] == "core.passthrough"
    clone = DefinitionService.clone_version(tenant_id, published.id, actor_id)
    assert clone.version == 2
    assert clone.status == "draft"
    assert clone.nodes.count() == 1
    retired = DefinitionService.retire(tenant_id, published.id, actor_id, "retire-1")
    assert retired.status == "retired"
    with pytest.raises(StateConflictError):
        DefinitionService.update_draft(tenant_id, retired.id, actor_id, {"name": "No"}, "immutable")


def test_cron_timezone_and_schedule_lifecycle() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, _ = _published_graph(tenant_id, actor_id, key="scheduled")
    schedule = ScheduleService.create_schedule(
        tenant_id,
        actor_id,
        {
            "definition_id": published.id,
            "name": "Hourly",
            "cron_expression": "0 * * * *",
            "timezone": "Asia/Kolkata",
            "misfire_policy": "run_once",
            "concurrency_policy": "forbid",
            "input": {"order_id": "A-1"},
        },
    )
    assert schedule.next_run_at > timezone.now()
    paused = ScheduleService.pause_schedule(tenant_id, schedule.id, actor_id, "pause-1")
    assert paused.status == "paused"
    with pytest.raises(StateConflictError, match="Retire"):
        ScheduleService.delete_schedule(tenant_id, schedule.id, actor_id)
    ScheduleService.retire_schedule(tenant_id, schedule.id, actor_id, "retire-schedule")
    assert ScheduleService.delete_schedule(tenant_id, schedule.id, actor_id).is_deleted
    with pytest.raises(ServiceValidationError, match="IANA"):
        ScheduleService.create_schedule(
            tenant_id,
            actor_id,
            {
                "definition_id": published.id,
                "name": "Bad",
                "cron_expression": "* * * * *",
                "timezone": "Mars/Olympus",
                "input": {"order_id": "1"},
            },
        )


def test_due_claim_recomputes_next_occurrence_and_is_tenant_isolated() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, _ = _published_graph(tenant_id, actor_id, key="due")
    schedule = ScheduleService.create_schedule(
        tenant_id,
        actor_id,
        {
            "definition_id": published.id,
            "name": "Due",
            "cron_expression": "* * * * *",
            "timezone": "UTC",
            "misfire_policy": "run_once",
            "input": {"order_id": "1"},
        },
    )
    before = timezone.now() - timedelta(minutes=5)
    type(schedule).objects.for_tenant(tenant_id).filter(id=schedule.id).update(next_run_at=before)
    assert ScheduleService.claim_due_schedules(uuid.uuid4(), timezone.now(), 10) == []
    claims = ScheduleService.claim_due_schedules(tenant_id, timezone.now(), 10)
    assert claims[0].schedule_id == schedule.id
    schedule.refresh_from_db()
    assert schedule.next_run_at > timezone.now() - timedelta(seconds=2)


def test_start_run_is_idempotent_and_atomically_creates_job_outbox_and_tasks() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, _ = _published_graph(tenant_id, actor_id, key="execute")
    run = ExecutionService.start_run(tenant_id, published.id, actor_id, {"order_id": "42"}, "request-42", "manual")
    duplicate = ExecutionService.start_run(
        tenant_id, published.id, actor_id, {"order_id": "42"}, "request-42", "manual"
    )
    assert duplicate.id == run.id
    assert OrchestrationTaskRun.objects.for_tenant(tenant_id).filter(run=run).count() == 1
    job = AsyncJob.objects.for_tenant(tenant_id).get(command="automation_orchestration.execute_run")
    assert OutboxEvent.objects.for_tenant(tenant_id).filter(aggregate_id=job.id).exists()
    with pytest.raises(IdempotencyConflictError):
        ExecutionService.start_run(tenant_id, published.id, actor_id, {"order_id": "different"}, "request-42", "manual")


def test_execution_resolves_task_persists_attempt_and_finalizes_output() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, _ = _published_graph(tenant_id, actor_id, key="complete")
    run = ExecutionService.start_run(tenant_id, published.id, actor_id, {"order_id": "42"}, "complete-42", "manual")
    ExecutionService.execute_run(tenant_id, run.id)
    task = OrchestrationTaskRun.objects.for_tenant(tenant_id).get(run=run)
    assert task.status == "queued"
    attempt = RetryAttempt.objects.for_tenant(tenant_id).get(task_run=task)
    operation_token = task.operation_token
    ExecutionService.execute_task(tenant_id, attempt.id)
    run.refresh_from_db()
    task.refresh_from_db()
    attempt.refresh_from_db()
    assert run.status == "succeeded"
    assert task.status == "succeeded"
    assert attempt.status == "succeeded"
    assert task.operation_token == operation_token
    assert attempt.request_fingerprint
    assert run.output == {"load": {"order_id": "42"}}


def test_pause_resume_cancel_and_retry_lineage_are_durable() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    published, _ = _published_graph(tenant_id, actor_id, key="control")
    run = ExecutionService.start_run(tenant_id, published.id, actor_id, {"order_id": "42"}, "control-42", "manual")
    ExecutionService.execute_run(tenant_id, run.id)
    assert ExecutionService.pause_run(tenant_id, run.id, actor_id, "pause-run").status == "paused"
    assert ExecutionService.resume_run(tenant_id, run.id, actor_id, "resume-run").status == "running"
    cancelled = ExecutionService.cancel_run(tenant_id, run.id, actor_id, "cancel-run")
    assert cancelled.status == "cancelled"
    retried = ExecutionService.retry_run(tenant_id, run.id, actor_id, "retry-control-42")
    assert retried.parent_run_id == run.id
    assert retried.id != run.id


def test_cron_expression_supports_ranges_steps_and_rejects_invalid_values() -> None:
    expression = CronExpression("*/15 9-17 * * 1-5")
    next_run = expression.next_after(timezone.now(), __import__("zoneinfo").ZoneInfo("UTC"))
    assert next_run.minute in {0, 15, 30, 45}
    with pytest.raises(ServiceValidationError, match="five fields"):
        CronExpression("* * *")
