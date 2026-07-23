"""Guarded, idempotent workflow lifecycle state machines.

The companion recorders extend the core JSON transition recorder so timestamps
and actor/failure evidence required by database constraints are written in the
same row update as the state transition.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from django.utils import timezone

from src.core.state_machine import JSONFieldTransitionRecorder, StateMachine, TransitionRecord
from src.core.state_machine import register as register_state_machine
from src.core.state_machine import registry as state_machine_registry

from .models import (
    Workflow,
    WorkflowInstance,
    WorkflowInstanceState,
    WorkflowStatus,
    WorkflowTask,
    WorkflowTaskStatus,
)


def _actor_id(metadata: Mapping[str, Any]) -> Any | None:
    return metadata.get("actor_id") or metadata.get("completed_by_id")


class _DefinitionTransitionRecorder(JSONFieldTransitionRecorder[Workflow]):
    def record(self, aggregate: Workflow, record: TransitionRecord) -> None:
        super().record(aggregate, record)
        now = timezone.now()
        if record.command == "publish":
            aggregate.published_at = aggregate.published_at or now
            actor_id = _actor_id(record.metadata)
            if actor_id is not None:
                aggregate.published_by_id = actor_id
        elif record.command == "archive":
            aggregate.archived_at = aggregate.archived_at or now
        elif record.command == "soft_delete":
            aggregate.deleted_at = aggregate.deleted_at or now

    def aggregate_update_fields(self) -> Collection[str]:
        return (
            "transition_history",
            "published_at",
            "published_by",
            "archived_at",
            "deleted_at",
        )


class _InstanceTransitionRecorder(JSONFieldTransitionRecorder[WorkflowInstance]):
    def record(self, aggregate: WorkflowInstance, record: TransitionRecord) -> None:
        super().record(aggregate, record)
        now = timezone.now()
        if record.command == "start":
            aggregate.started_at = aggregate.started_at or now
        if record.to_state in {
            WorkflowInstanceState.COMPLETED,
            WorkflowInstanceState.FAILED,
            WorkflowInstanceState.CANCELLED,
        }:
            aggregate.completed_at = aggregate.completed_at or now
        if record.command == "fail":
            code = record.metadata.get("failure_code") or record.metadata.get("code")
            if not isinstance(code, str) or not code.strip():
                raise ValueError("A fail transition requires a stable failure_code in metadata")
            aggregate.failure_code = code.strip()[:64]
            message = record.metadata.get("failure_message") or record.metadata.get("message") or ""
            # The service layer has already applied the tenant-configured
            # redaction and length policy before entering the state primitive.
            aggregate.failure_message = str(message).strip()

    def aggregate_update_fields(self) -> Collection[str]:
        return (
            "transition_history",
            "started_at",
            "completed_at",
            "failure_code",
            "failure_message",
        )


class _TaskTransitionRecorder(JSONFieldTransitionRecorder[WorkflowTask]):
    def record(self, aggregate: WorkflowTask, record: TransitionRecord) -> None:
        super().record(aggregate, record)
        if record.to_state in {
            WorkflowTaskStatus.COMPLETED,
            WorkflowTaskStatus.REJECTED,
            WorkflowTaskStatus.CANCELLED,
            WorkflowTaskStatus.EXPIRED,
        }:
            aggregate.completed_at = aggregate.completed_at or timezone.now()
        actor_id = _actor_id(record.metadata)
        if actor_id is not None and record.command in {"complete", "reject", "cancel"}:
            aggregate.completed_by_id = actor_id

    def aggregate_update_fields(self) -> Collection[str]:
        return ("transition_history", "completed_at", "completed_by")


def _definition_is_publishable(aggregate: Workflow, context: Mapping[str, Any]) -> bool:
    """Require service validation evidence; state transitions never infer it."""
    return (
        context.get("definition_valid") is True
        and context.get("handlers_registered") is True
        and context.get("terminal_path_reachable") is True
        and context.get("references_resolved") is True
        and aggregate.deleted_at is None
    )


def _definition_has_no_executions(aggregate: Workflow, context: Mapping[str, Any]) -> bool:
    del context
    return not aggregate.instances.exists()


WORKFLOW_DEFINITION_MACHINE = StateMachine[Workflow](
    name="workflow_automation.definition",
    model=Workflow,
    states=WorkflowStatus.values,
    transitions=(
        {
            "command": "publish",
            "from": WorkflowStatus.DRAFT,
            "to": WorkflowStatus.PUBLISHED,
            "guards": (_definition_is_publishable,),
        },
        {"command": "archive", "from": WorkflowStatus.PUBLISHED, "to": WorkflowStatus.ARCHIVED},
        {
            "command": "soft_delete",
            "from": WorkflowStatus.DRAFT,
            "to": WorkflowStatus.DRAFT,
            "guards": (_definition_has_no_executions,),
        },
    ),
    terminal_states=(WorkflowStatus.ARCHIVED,),
    state_field="status",
    recorder=_DefinitionTransitionRecorder(),
)


WORKFLOW_INSTANCE_MACHINE = StateMachine[WorkflowInstance](
    name="workflow_automation.instance",
    model=WorkflowInstance,
    states=WorkflowInstanceState.values,
    transitions=(
        {"command": "start", "from": WorkflowInstanceState.PENDING, "to": WorkflowInstanceState.RUNNING},
        {
            "command": "wait_for_task",
            "from": WorkflowInstanceState.RUNNING,
            "to": WorkflowInstanceState.WAITING,
        },
        {
            "command": "task_completed",
            "from": WorkflowInstanceState.WAITING,
            "to": WorkflowInstanceState.RUNNING,
        },
        {"command": "complete", "from": WorkflowInstanceState.RUNNING, "to": WorkflowInstanceState.COMPLETED},
        {"command": "fail", "from": WorkflowInstanceState.PENDING, "to": WorkflowInstanceState.FAILED},
        {"command": "fail", "from": WorkflowInstanceState.RUNNING, "to": WorkflowInstanceState.FAILED},
        {"command": "fail", "from": WorkflowInstanceState.WAITING, "to": WorkflowInstanceState.FAILED},
        {"command": "cancel", "from": WorkflowInstanceState.PENDING, "to": WorkflowInstanceState.CANCELLED},
        {"command": "cancel", "from": WorkflowInstanceState.RUNNING, "to": WorkflowInstanceState.CANCELLED},
        {"command": "cancel", "from": WorkflowInstanceState.WAITING, "to": WorkflowInstanceState.CANCELLED},
    ),
    terminal_states=(
        WorkflowInstanceState.COMPLETED,
        WorkflowInstanceState.FAILED,
        WorkflowInstanceState.CANCELLED,
    ),
    state_field="state",
    recorder=_InstanceTransitionRecorder(),
)


WORKFLOW_TASK_MACHINE = StateMachine[WorkflowTask](
    name="workflow_automation.task",
    model=WorkflowTask,
    states=WorkflowTaskStatus.values,
    transitions=(
        {"command": "complete", "from": WorkflowTaskStatus.PENDING, "to": WorkflowTaskStatus.COMPLETED},
        {"command": "reject", "from": WorkflowTaskStatus.PENDING, "to": WorkflowTaskStatus.REJECTED},
        {"command": "cancel", "from": WorkflowTaskStatus.PENDING, "to": WorkflowTaskStatus.CANCELLED},
        {"command": "expire", "from": WorkflowTaskStatus.PENDING, "to": WorkflowTaskStatus.EXPIRED},
    ),
    terminal_states=(
        WorkflowTaskStatus.COMPLETED,
        WorkflowTaskStatus.REJECTED,
        WorkflowTaskStatus.CANCELLED,
        WorkflowTaskStatus.EXPIRED,
    ),
    state_field="status",
    recorder=_TaskTransitionRecorder(),
)


def register_workflow_state_machines() -> None:
    """Register machines idempotently for Django autoreload and worker boot."""
    for name, machine in (
        ("workflow_automation.definition", WORKFLOW_DEFINITION_MACHINE),
        ("workflow_automation.instance", WORKFLOW_INSTANCE_MACHINE),
        ("workflow_automation.task", WORKFLOW_TASK_MACHINE),
    ):
        if name not in state_machine_registry.names():
            register_state_machine(name, machine)


# Friendly aliases retained for service imports while uppercase constants are
# the canonical public contract.
workflow_definition_machine = WORKFLOW_DEFINITION_MACHINE
workflow_instance_machine = WORKFLOW_INSTANCE_MACHINE
workflow_task_machine = WORKFLOW_TASK_MACHINE


__all__ = [
    "WORKFLOW_DEFINITION_MACHINE",
    "WORKFLOW_INSTANCE_MACHINE",
    "WORKFLOW_TASK_MACHINE",
    "register_workflow_state_machines",
    "workflow_definition_machine",
    "workflow_instance_machine",
    "workflow_task_machine",
]
