"""Concrete factories for tenant-safe workflow domain tests."""

from __future__ import annotations

import hashlib
import uuid

import factory
from django.utils import timezone

from ..models import (
    Workflow,
    WorkflowAssignmentKind,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepExecution,
    WorkflowStepType,
    WorkflowTask,
)


class TenantFactory(factory.django.DjangoModelFactory):
    """Base factory that always assigns a real UUID tenant boundary."""

    class Meta:
        abstract = True

    tenant_id = factory.LazyFunction(uuid.uuid4)


class WorkflowFactory(TenantFactory):
    class Meta:
        model = Workflow

    key = factory.Sequence(lambda number: f"workflow-{number}")
    version = 1
    name = factory.Sequence(lambda number: f"Workflow {number}")
    description = "A governed test workflow"
    workflow_type = "sequential"
    trigger_type = "manual"
    status = WorkflowStatus.DRAFT
    required_context_schema = factory.LazyFunction(dict)
    transition_history = factory.LazyFunction(list)

    class Params:
        published = factory.Trait(
            status=WorkflowStatus.PUBLISHED,
            published_at=factory.LazyFunction(timezone.now),
        )
        archived = factory.Trait(
            status=WorkflowStatus.ARCHIVED,
            archived_at=factory.LazyFunction(timezone.now),
        )


class WorkflowStepFactory(TenantFactory):
    class Meta:
        model = WorkflowStep

    workflow = factory.SubFactory(
        WorkflowFactory,
        tenant_id=factory.SelfAttribute("..tenant_id"),
    )
    key = factory.Sequence(lambda number: f"step-{number}")
    name = factory.Sequence(lambda number: f"Step {number}")
    step_type = WorkflowStepType.ACTION
    order = factory.Sequence(lambda number: number + 1)
    config = factory.LazyFunction(
        lambda: {
            "handler": "builtin.context_projection.v1",
            "schema_version": "1.0",
            "input_mapping": {},
        }
    )
    is_terminal = True


class WorkflowInstanceFactory(TenantFactory):
    class Meta:
        model = WorkflowInstance

    workflow = factory.SubFactory(
        WorkflowFactory,
        tenant_id=factory.SelfAttribute("..tenant_id"),
        published=True,
    )
    workflow_version = factory.LazyAttribute(lambda instance: instance.workflow.version)
    context_data = factory.LazyFunction(dict)
    result_data = factory.LazyFunction(dict)
    priority = 5
    idempotency_key = factory.LazyFunction(lambda: f"instance:{uuid.uuid4().hex}")
    correlation_id = factory.LazyFunction(lambda: str(uuid.uuid4()))


def _instance_step(instance: WorkflowInstance) -> WorkflowStep:
    # Production steps are created while the definition is a draft and remain
    # referenced after publication. Build the same historical row without
    # weakening the model's published-definition immutability guard.
    step = WorkflowStepFactory.build(
        tenant_id=instance.tenant_id,
        workflow=instance.workflow,
    )
    if instance._state.adding or instance.workflow._state.adding:
        return step
    WorkflowStep.objects.bulk_create([step])
    return step


class WorkflowTaskFactory(TenantFactory):
    class Meta:
        model = WorkflowTask

    instance = factory.SubFactory(
        WorkflowInstanceFactory,
        tenant_id=factory.SelfAttribute("..tenant_id"),
    )
    step = factory.LazyAttribute(lambda task: _instance_step(task.instance))
    assignment_kind = WorkflowAssignmentKind.ROLE
    assignee_role_id = factory.LazyFunction(uuid.uuid4)
    assignment_key = factory.LazyAttribute(lambda task: f"role:{task.assignee_role_id}")
    correlation_id = factory.LazyAttribute(lambda task: task.instance.correlation_id)
    meta_data = factory.LazyFunction(dict)
    transition_history = factory.LazyFunction(list)


class WorkflowStepExecutionFactory(TenantFactory):
    class Meta:
        model = WorkflowStepExecution

    instance = factory.SubFactory(
        WorkflowInstanceFactory,
        tenant_id=factory.SelfAttribute("..tenant_id"),
    )
    step = factory.LazyAttribute(lambda execution: _instance_step(execution.instance))
    attempt = 1
    operation_key = factory.LazyFunction(lambda: f"step:{uuid.uuid4().hex}")
    handler_key = "builtin.context_projection.v1"
    handler_contract_version = "1.0"
    handler_contract_fingerprint = factory.LazyFunction(lambda: hashlib.sha256(b"handler-contract").hexdigest())
    input_fingerprint = factory.LazyFunction(lambda: hashlib.sha256(b"input").hexdigest())
    correlation_id = factory.LazyAttribute(lambda execution: execution.instance.correlation_id)
    output_evidence = factory.LazyFunction(dict)
    provider_evidence = factory.LazyFunction(dict)


__all__ = [
    "WorkflowFactory",
    "WorkflowInstanceFactory",
    "WorkflowStepExecutionFactory",
    "WorkflowStepFactory",
    "WorkflowTaskFactory",
]
