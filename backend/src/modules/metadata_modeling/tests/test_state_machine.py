"""Registered entity lifecycle behavior and transition evidence."""

import uuid

import pytest

from src.core.async_jobs.models import OutboxEvent
from src.core.state_machine import IdempotencyConflictError, IllegalTransitionError, registry
from src.modules.metadata_modeling.models import EntityDefinition
from src.modules.metadata_modeling.state_machine import MACHINE_NAME, register_entity_state_machine

from .helpers import ACTOR_ID

pytest_plugins = ["src.core.testing.factories"]


def test_machine_registration_is_idempotent_and_declares_all_required_edges():
    first = register_entity_state_machine()
    second = register_entity_state_machine()
    assert first is second is registry.get(MACHINE_NAME)
    assert {(item.command, item.source, item.target) for item in first.transitions} == {
        ("publish", "draft", "published"),
        ("publish_new_version", "published", "published"),
        ("archive", "draft", "archived"),
        ("archive", "published", "archived"),
        ("restore", "archived", "published"),
    }


@pytest.mark.django_db
def test_archive_is_audited_idempotently_and_illegal_transition_is_rejected():
    tenant_id = uuid.uuid4()
    entity = EntityDefinition.objects.create(
        tenant_id=tenant_id,
        name="Draft",
        plural_name="Drafts",
        code="draft",
    )
    machine = register_entity_state_machine()
    metadata = {"actor_id": str(ACTOR_ID), "correlation_id": "corr-transition"}
    result = machine.apply(entity, "archive", transition_key="archive-once", metadata=metadata)
    repeated = machine.apply(entity, "archive", transition_key="archive-once", metadata=metadata)
    assert result.status == repeated.status == "archived"
    assert (
        OutboxEvent.objects.for_tenant(tenant_id).filter(event_type="metadata_modeling.entity.transitioned.v1").count()
        == 1
    )
    with pytest.raises(IllegalTransitionError):
        machine.apply(entity, "publish", transition_key="bad-publish", metadata=metadata)
    with pytest.raises(IdempotencyConflictError):
        machine.apply(entity, "restore", transition_key="archive-once", metadata=metadata)
