"""Factory Boy fixtures for the complete orchestration persistence graph."""

from __future__ import annotations

import uuid

import factory
from django.utils import timezone as django_timezone

from ..models import (
    AttemptStatus,
    DefinitionStatus,
    NodeType,
    OrchestrationDefinition,
    OrchestrationEdge,
    OrchestrationEvent,
    OrchestrationNode,
    OrchestrationRun,
    OrchestrationSchedule,
    OrchestrationTaskRun,
    RetryAttempt,
    RunStatus,
    RunTriggerType,
    ScheduleStatus,
    TaskRunStatus,
)


class TenantFactory(factory.django.DjangoModelFactory):
    """Shared deterministic ownership and audit values."""

    class Meta:
        abstract = True

    tenant_id = factory.LazyFunction(uuid.uuid4)


class AuditedTenantFactory(TenantFactory):
    class Meta:
        abstract = True

    created_by = factory.LazyFunction(uuid.uuid4)
    updated_by = factory.SelfAttribute("created_by")


class OrchestrationDefinitionFactory(AuditedTenantFactory):
    class Meta:
        model = OrchestrationDefinition

    key = factory.Sequence(lambda number: f"orchestration-{number}")
    version = 1
    name = factory.Sequence(lambda number: f"Orchestration {number}")
    status = DefinitionStatus.DRAFT

    class Params:
        published = factory.Trait(status=DefinitionStatus.PUBLISHED, is_current=True)
        retired = factory.Trait(status=DefinitionStatus.RETIRED, is_current=False)


class OrchestrationNodeFactory(AuditedTenantFactory):
    class Meta:
        model = OrchestrationNode

    definition = factory.SubFactory(OrchestrationDefinitionFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    key = factory.Sequence(lambda number: f"node-{number}")
    name = factory.Sequence(lambda number: f"Node {number}")
    node_type = NodeType.INTERNAL
    handler_key = factory.Sequence(lambda number: f"test.handler.{number}")


class OrchestrationEdgeFactory(AuditedTenantFactory):
    class Meta:
        model = OrchestrationEdge

    definition = factory.SubFactory(OrchestrationDefinitionFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    upstream_node = factory.SubFactory(
        OrchestrationNodeFactory,
        tenant_id=factory.SelfAttribute("..tenant_id"),
        definition=factory.SelfAttribute("..definition"),
    )
    downstream_node = factory.SubFactory(
        OrchestrationNodeFactory,
        tenant_id=factory.SelfAttribute("..tenant_id"),
        definition=factory.SelfAttribute("..definition"),
    )


class OrchestrationScheduleFactory(AuditedTenantFactory):
    class Meta:
        model = OrchestrationSchedule

    definition = factory.SubFactory(
        OrchestrationDefinitionFactory,
        tenant_id=factory.SelfAttribute("..tenant_id"),
        published=True,
    )
    name = factory.Sequence(lambda number: f"Schedule {number}")
    cron_expression = "0 * * * *"
    timezone = "UTC"
    status = ScheduleStatus.ACTIVE
    next_run_at = factory.LazyFunction(django_timezone.now)


class OrchestrationRunFactory(TenantFactory):
    class Meta:
        model = OrchestrationRun

    definition = factory.SubFactory(
        OrchestrationDefinitionFactory,
        tenant_id=factory.SelfAttribute("..tenant_id"),
        published=True,
    )
    trigger_type = RunTriggerType.MANUAL
    status = RunStatus.QUEUED
    idempotency_key = factory.LazyFunction(lambda: uuid.uuid4().hex)
    correlation_id = factory.LazyFunction(lambda: uuid.uuid4().hex)
    requested_by = factory.LazyFunction(uuid.uuid4)


def _execution_node(run: OrchestrationRun) -> OrchestrationNode:
    """Create the already-published node snapshot used by run-history factories.

    Production nodes are created while their definition is a draft and remain
    referenced after publication.  A focused factory cannot replay the entire
    publication command for every task, so it inserts that historical node in
    one bulk operation while still satisfying every database invariant.
    """
    actor_id = uuid.uuid4()
    node = OrchestrationNode(
        tenant_id=run.tenant_id,
        definition=run.definition,
        key=f"execution-node-{uuid.uuid4().hex[:12]}",
        name="Execution node",
        node_type=NodeType.INTERNAL,
        handler_key="test.execution",
        created_by=actor_id,
        updated_by=actor_id,
    )
    OrchestrationNode.objects.bulk_create([node])
    return node


class OrchestrationTaskRunFactory(TenantFactory):
    class Meta:
        model = OrchestrationTaskRun

    run = factory.SubFactory(OrchestrationRunFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    node = factory.LazyAttribute(lambda task: _execution_node(task.run))
    status = TaskRunStatus.BLOCKED
    max_attempts = 3


class RetryAttemptFactory(TenantFactory):
    class Meta:
        model = RetryAttempt

    task_run = factory.SubFactory(OrchestrationTaskRunFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    attempt_number = 1
    async_job_id = factory.LazyFunction(uuid.uuid4)
    idempotency_key = factory.LazyFunction(lambda: uuid.uuid4().hex)
    status = AttemptStatus.QUEUED
    available_at = factory.LazyFunction(django_timezone.now)
    correlation_id = factory.LazyFunction(lambda: uuid.uuid4().hex)


class OrchestrationEventFactory(TenantFactory):
    class Meta:
        model = OrchestrationEvent

    aggregate_type = "run"
    aggregate_id = factory.LazyFunction(uuid.uuid4)
    event_type = "run.created"
    correlation_id = factory.LazyFunction(lambda: uuid.uuid4().hex)


# Concise aliases keep tests and downstream extension packages readable.
DefinitionFactory = OrchestrationDefinitionFactory
NodeFactory = OrchestrationNodeFactory
EdgeFactory = OrchestrationEdgeFactory
ScheduleFactory = OrchestrationScheduleFactory
RunFactory = OrchestrationRunFactory
TaskRunFactory = OrchestrationTaskRunFactory
AttemptFactory = RetryAttemptFactory
EventFactory = OrchestrationEventFactory
