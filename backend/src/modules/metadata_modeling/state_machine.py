"""Declarative entity lifecycle registration and immutable audit recorder."""

from __future__ import annotations

import uuid
from typing import Collection

from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent
from src.core.state_machine import StateMachine, TransitionRecord, register, registry

from .models import EntityDefinition

MACHINE_NAME = "metadata_modeling.entity_definition"


class EntityTransitionRecorder:
    """Persist idempotency/audit evidence in the durable outbox transaction."""

    def find(self, aggregate: EntityDefinition, transition_key: str) -> TransitionRecord | None:
        event = OutboxEvent.objects.for_tenant(aggregate.tenant_id).filter(
            aggregate_type="entity_definition",
            aggregate_id=aggregate.id,
            event_type="metadata_modeling.entity.transitioned.v1",
            payload__transition_key=transition_key,
        ).first()
        if event is None:
            return None
        payload = event.payload
        return TransitionRecord(
            transition_key=str(payload["transition_key"]),
            command=str(payload["command"]),
            from_state=str(payload["from_state"]),
            to_state=str(payload["to_state"]),
            occurred_at=str(payload["occurred_at"]),
            metadata=dict(payload.get("metadata", {})),
        )

    def record(self, aggregate: EntityDefinition, record: TransitionRecord) -> None:
        actor_value = record.metadata.get("actor_id", uuid.UUID(int=0))
        actor_id = actor_value if isinstance(actor_value, uuid.UUID) else uuid.UUID(str(actor_value))
        if record.command == "archive":
            aggregate.archived_at = timezone.now()
            aggregate.archived_by = actor_id
        elif record.command == "restore":
            aggregate.archived_at = None
            aggregate.archived_by = None
        OutboxEvent.objects.create(
            tenant_id=aggregate.tenant_id,
            aggregate_type="entity_definition",
            aggregate_id=aggregate.id,
            event_type="metadata_modeling.entity.transitioned.v1",
            payload={**record.as_dict(), "correlation_id": str(record.metadata.get("correlation_id", ""))},
        )

    def aggregate_update_fields(self) -> Collection[str]:
        return ("archived_at", "archived_by")


def register_entity_state_machine() -> StateMachine[EntityDefinition]:
    """Register once; startup reloads must remain idempotent."""
    if MACHINE_NAME in registry.names():
        return registry.get(MACHINE_NAME)
    machine = StateMachine(
        name=MACHINE_NAME,
        model=EntityDefinition,
        state_field="status",
        states=("draft", "published", "archived"),
        transitions=(
            {"command": "publish", "source": "draft", "target": "published"},
            {"command": "publish_new_version", "source": "published", "target": "published"},
            {"command": "archive", "source": "draft", "target": "archived"},
            {"command": "archive", "source": "published", "target": "archived"},
            {"command": "restore", "source": "archived", "target": "published"},
        ),
        recorder=EntityTransitionRecorder(),
    )
    return register(MACHINE_NAME, machine)


__all__ = ["MACHINE_NAME", "EntityTransitionRecorder", "register_entity_state_machine"]
