"""Domain invariants and state-machine evidence tests."""

from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from src.core.state_machine import IdempotencyConflictError, TerminalStateError
from src.core.tenancy import TenantScopedModel, TimestampedModel

from ..models import (
    Workflow,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepExecution,
    WorkflowTask,
    WorkflowTaskStatus,
)
from ..state_machines import WORKFLOW_DEFINITION_MACHINE, WORKFLOW_TASK_MACHINE
from .factories import (
    WorkflowFactory,
    WorkflowInstanceFactory,
    WorkflowStepExecutionFactory,
    WorkflowStepFactory,
    WorkflowTaskFactory,
)

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db


def test_all_domain_records_are_tenant_scoped_and_timestamped() -> None:
    for model in (Workflow, WorkflowStep, WorkflowInstance, WorkflowTask, WorkflowStepExecution):
        assert issubclass(model, TenantScopedModel)
        assert issubclass(model, TimestampedModel)
        tenant_field = model._meta.get_field("tenant_id")
        assert tenant_field.get_internal_type() == "UUIDField"
        assert tenant_field.db_index is True


def test_factory_builds_consistent_execution_evidence_graph() -> None:
    task = WorkflowTaskFactory()
    execution = WorkflowStepExecutionFactory(
        tenant_id=task.tenant_id,
        instance=task.instance,
        step=task.step,
    )
    assert task.tenant_id == task.instance.tenant_id == task.step.tenant_id
    assert task.instance.workflow_id == task.step.workflow_id
    assert execution.tenant_id == execution.instance.tenant_id == execution.step.tenant_id
    assert execution.attempt == 1


@pytest.mark.parametrize("field", ["name", "key"])
def test_workflow_rejects_blank_identity_fields(field: str) -> None:
    workflow = WorkflowFactory.build()
    setattr(workflow, field, "  ")
    with pytest.raises(ValidationError):
        workflow.full_clean()


def test_workflow_key_version_is_unique_per_tenant() -> None:
    workflow = WorkflowFactory()
    with pytest.raises((IntegrityError, ValidationError)):
        WorkflowFactory(
            tenant_id=workflow.tenant_id,
            key=workflow.key,
            version=workflow.version,
        )


def test_step_rejects_cross_tenant_workflow() -> None:
    workflow = WorkflowFactory()
    step = WorkflowStepFactory.build(tenant_id=uuid.uuid4(), workflow=workflow)
    with pytest.raises(ValidationError):
        step.full_clean()


def test_instance_rejects_cross_tenant_workflow_and_wrong_version() -> None:
    workflow = WorkflowFactory(published=True, version=3)
    wrong_tenant = WorkflowInstanceFactory.build(
        tenant_id=uuid.uuid4(),
        workflow=workflow,
        workflow_version=workflow.version,
    )
    with pytest.raises(ValidationError):
        wrong_tenant.full_clean()

    wrong_version = WorkflowInstanceFactory.build(
        tenant_id=workflow.tenant_id,
        workflow=workflow,
        workflow_version=2,
    )
    with pytest.raises(ValidationError):
        wrong_version.full_clean()


def test_task_requires_normalized_assignment_shape() -> None:
    task = WorkflowTaskFactory.build(assignment_key="role:not-the-role")
    with pytest.raises(ValidationError):
        task.full_clean()


def test_definition_transition_is_atomic_idempotent_and_append_only() -> None:
    workflow = WorkflowFactory()
    transitioned = WORKFLOW_DEFINITION_MACHINE.apply(
        workflow,
        "publish",
        tenant_id=workflow.tenant_id,
        transition_key="publish:v1",
        context={
            "definition_valid": True,
            "handlers_registered": True,
            "terminal_path_reachable": True,
            "references_resolved": True,
        },
    )
    assert transitioned.status == WorkflowStatus.PUBLISHED
    assert transitioned.published_at is not None
    assert len(transitioned.transition_history) == 1

    replay = WORKFLOW_DEFINITION_MACHINE.apply(
        transitioned,
        "publish",
        tenant_id=workflow.tenant_id,
        transition_key="publish:v1",
        context={"definition_valid": True},
    )
    assert len(replay.transition_history) == 1
    with pytest.raises(IdempotencyConflictError):
        WORKFLOW_DEFINITION_MACHINE.apply(
            replay,
            "archive",
            tenant_id=workflow.tenant_id,
            transition_key="publish:v1",
        )


def test_archived_definition_is_terminal_and_immutable() -> None:
    workflow = WorkflowFactory()
    workflow = WORKFLOW_DEFINITION_MACHINE.apply(
        workflow,
        "publish",
        tenant_id=workflow.tenant_id,
        transition_key="publish",
        context={"definition_valid": True},
    )
    workflow = WORKFLOW_DEFINITION_MACHINE.apply(
        workflow,
        "archive",
        tenant_id=workflow.tenant_id,
        transition_key="archive",
    )
    with pytest.raises(TerminalStateError):
        WORKFLOW_DEFINITION_MACHINE.apply(
            workflow,
            "publish",
            tenant_id=workflow.tenant_id,
            transition_key="publish-again",
        )
    workflow.name = "Mutated historical version"
    with pytest.raises(ValidationError):
        workflow.save()


def test_task_transition_records_actor_and_rejects_terminal_mutation(tenant_a_user: object) -> None:
    task = WorkflowTaskFactory()
    completed = WORKFLOW_TASK_MACHINE.apply(
        task,
        "complete",
        tenant_id=task.tenant_id,
        transition_key="decision:1",
        metadata={"actor_id": getattr(tenant_a_user, "pk")},
    )
    assert completed.status == WorkflowTaskStatus.COMPLETED
    assert completed.completed_at is not None
    assert completed.completed_by_id == getattr(tenant_a_user, "pk")
    assert completed.transition_history[0]["transition_key"] == "decision:1"
    completed.meta_data = {"tampered": True}
    with pytest.raises(ValidationError):
        completed.save()


def test_execution_history_cannot_be_deleted() -> None:
    instance = WorkflowInstanceFactory()
    task = WorkflowTaskFactory(tenant_id=instance.tenant_id, instance=instance)
    execution = WorkflowStepExecutionFactory(
        tenant_id=instance.tenant_id,
        instance=instance,
        step=task.step,
    )
    for record in (instance, task, execution):
        with pytest.raises(ValidationError):
            record.delete()
