"""Persistence invariants for the orchestration domain."""

from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from src.core.tenancy import TenantScopedModel, TimestampedModel

from ..models import (
    AttemptStatus,
    DefinitionStatus,
    OrchestrationDefinition,
    OrchestrationEvent,
    OrchestrationRun,
    OrchestrationTaskRun,
    RetryAttempt,
    RunStatus,
    TaskRunStatus,
)
from .factories import (
    AttemptFactory,
    DefinitionFactory,
    EdgeFactory,
    EventFactory,
    NodeFactory,
    RunFactory,
    ScheduleFactory,
    TaskRunFactory,
)

pytestmark = pytest.mark.django_db


def test_all_eight_models_use_canonical_tenant_scope() -> None:
    model_types = {
        OrchestrationDefinition,
        NodeFactory._meta.model,
        EdgeFactory._meta.model,
        ScheduleFactory._meta.model,
        OrchestrationRun,
        OrchestrationTaskRun,
        RetryAttempt,
        OrchestrationEvent,
    }
    assert all(issubclass(model, TenantScopedModel) for model in model_types)
    assert all(model._meta.get_field("tenant_id").get_internal_type() == "UUIDField" for model in model_types)
    assert all(model._meta.get_field("tenant_id").db_index for model in model_types)
    assert all(issubclass(model, TimestampedModel) for model in model_types if model is not OrchestrationEvent)


def test_tenant_queryset_has_an_explicit_boundary() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    own = DefinitionFactory(tenant_id=tenant_a)
    DefinitionFactory(tenant_id=tenant_b)

    assert list(OrchestrationDefinition.objects.for_tenant(tenant_a)) == [own]


def test_definition_versions_and_current_rows_are_unique_per_tenant() -> None:
    definition = DefinitionFactory(is_current=True)
    with pytest.raises(ValidationError):
        DefinitionFactory(tenant_id=definition.tenant_id, key=definition.key, version=definition.version)
    with pytest.raises(ValidationError):
        DefinitionFactory(tenant_id=definition.tenant_id, key=definition.key, version=2, is_current=True)


def test_definition_bounds_are_database_constraints() -> None:
    with pytest.raises(ValidationError):
        DefinitionFactory(max_parallel_tasks=101)
    with pytest.raises(ValidationError):
        DefinitionFactory(default_timeout_seconds=0)
    with pytest.raises(ValidationError):
        DefinitionFactory(default_max_attempts=21)


def test_published_contract_is_immutable_but_can_retire() -> None:
    definition = DefinitionFactory(published=True)
    definition.name = "rewritten"
    with pytest.raises(ValidationError, match="immutable"):
        definition.save()

    definition.refresh_from_db()
    definition.status = DefinitionStatus.RETIRED
    definition.is_current = False
    definition.save()
    assert definition.status == DefinitionStatus.RETIRED


def test_draft_or_retired_definition_soft_delete_requires_timestamp_and_no_active_schedule() -> None:
    draft = DefinitionFactory()
    draft.is_deleted = True
    with pytest.raises(ValidationError, match="deleted_at"):
        draft.save()

    draft.deleted_at = timezone.now()
    draft.save()
    assert draft.is_deleted

    retired = DefinitionFactory(retired=True)
    # Factory schedules require a published definition, so create while published then retire.
    published = DefinitionFactory(published=True)
    schedule = ScheduleFactory(definition=published, tenant_id=published.tenant_id)
    published.status = DefinitionStatus.RETIRED
    published.is_current = False
    published.save()
    published.is_deleted = True
    published.deleted_at = timezone.now()
    with pytest.raises(ValidationError, match="active schedule"):
        published.save()
    assert retired.status == DefinitionStatus.RETIRED
    assert schedule.pk


def test_node_edge_and_schedule_reject_cross_tenant_relationships() -> None:
    definition = DefinitionFactory()
    with pytest.raises(ValidationError, match="same tenant"):
        NodeFactory(definition=definition, tenant_id=uuid.uuid4())

    upstream = NodeFactory(definition=definition, tenant_id=definition.tenant_id)
    other_definition = DefinitionFactory(tenant_id=definition.tenant_id)
    downstream = NodeFactory(definition=other_definition, tenant_id=definition.tenant_id)
    with pytest.raises(ValidationError, match="same tenant and definition"):
        EdgeFactory(
            definition=definition,
            tenant_id=definition.tenant_id,
            upstream_node=upstream,
            downstream_node=downstream,
        )

    published = DefinitionFactory(published=True)
    with pytest.raises(ValidationError, match="same tenant"):
        ScheduleFactory(definition=published, tenant_id=uuid.uuid4())


def test_edge_rejects_self_dependency() -> None:
    node = NodeFactory()
    with pytest.raises(ValidationError, match="cannot depend on itself"):
        EdgeFactory(
            tenant_id=node.tenant_id,
            definition=node.definition,
            upstream_node=node,
            downstream_node=node,
        )


def test_run_relationships_are_tenant_and_definition_safe() -> None:
    parent = RunFactory()
    other_definition = DefinitionFactory(tenant_id=parent.tenant_id, published=True)
    with pytest.raises(ValidationError, match="exact definition"):
        RunFactory(
            tenant_id=parent.tenant_id,
            definition=other_definition,
            parent_run=parent,
        )


@pytest.mark.parametrize(
    ("factory", "terminal_status"),
    [
        (RunFactory, RunStatus.SUCCEEDED),
        (TaskRunFactory, TaskRunStatus.SUCCEEDED),
        (AttemptFactory, AttemptStatus.SUCCEEDED),
    ],
)
def test_terminal_execution_history_is_immutable_and_not_deletable(factory, terminal_status: str) -> None:
    record = factory(status=terminal_status)
    record.error_message = "mutation"
    with pytest.raises(ValidationError, match="immutable"):
        record.save()
    with pytest.raises(ValidationError, match="cannot be deleted"):
        record.delete()
    with pytest.raises(ValidationError, match="immutable"):
        type(record).objects.filter(pk=record.pk).update(error_message="bulk mutation")
    with pytest.raises(ValidationError, match="cannot be deleted"):
        type(record).objects.filter(pk=record.pk).delete()


def test_illegal_execution_state_rewind_is_rejected() -> None:
    run = RunFactory(status=RunStatus.RUNNING)
    run.status = RunStatus.QUEUED
    with pytest.raises(ValidationError, match="Illegal transition"):
        run.save()


def test_task_and_attempt_are_bound_to_same_tenant() -> None:
    task = TaskRunFactory()
    with pytest.raises(ValidationError, match="same tenant"):
        AttemptFactory(task_run=task, tenant_id=uuid.uuid4())


def test_operation_and_delivery_tokens_are_stable_and_unique() -> None:
    task = TaskRunFactory()
    original_operation_token = task.operation_token
    task.status = TaskRunStatus.READY
    task.save()
    task.refresh_from_db()
    assert task.operation_token == original_operation_token

    attempt = AttemptFactory(task_run=task, tenant_id=task.tenant_id)
    with pytest.raises((ValidationError, IntegrityError)):
        with transaction.atomic():
            AttemptFactory(delivery_token=attempt.delivery_token)


def test_event_instance_and_queryset_are_append_only() -> None:
    event = EventFactory(payload={"safe": "evidence"})
    event.payload = {"changed": True}
    with pytest.raises(ValidationError, match="append-only"):
        event.save()
    with pytest.raises(ValidationError, match="append-only"):
        OrchestrationEvent.objects.filter(pk=event.pk).update(event_type="rewritten")
    with pytest.raises(ValidationError, match="append-only"):
        OrchestrationEvent.objects.filter(pk=event.pk).delete()
    with pytest.raises(ValidationError, match="append-only"):
        event.delete()


def test_execution_uniqueness_and_bounds_are_enforced() -> None:
    run = RunFactory()
    with pytest.raises(ValidationError):
        RunFactory(tenant_id=run.tenant_id, idempotency_key=run.idempotency_key)

    task = TaskRunFactory()
    with pytest.raises(ValidationError):
        TaskRunFactory(run=task.run, node=task.node, tenant_id=task.tenant_id)

    with pytest.raises(ValidationError):
        AttemptFactory(attempt_number=21)
