"""Sanitized data-migration events persisted through the transactional outbox."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Final
from uuid import UUID

from src.core.async_jobs.models import OutboxEvent
from src.core.middleware.correlation import get_correlation_id

SCHEMA_VERSION: Final[int] = 1
EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "data_migration.job.created",
        "data_migration.job.updated",
        "data_migration.job.deleted",
        "data_migration.job.restored",
        "data_migration.job.archived",
        "data_migration.run.queued",
        "data_migration.run.cancelled",
        "data_migration.run.completed",
        "data_migration.rollback.queued",
        "data_migration.rollback.completed",
        "data_migration.configuration.changed",
    }
)
SAFE_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    {"status", "mode", "version", "from_version", "records", "outcome", "failure_code"}
)


def publish_event(
    tenant_id: UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    *,
    actor_id: UUID | None,
    correlation_id: str | None = None,
    payload: Mapping[str, object] | None = None,
) -> OutboxEvent:
    """Write an allow-listed event in the caller's transaction.

    Source rows, connection details and secret references cannot enter this API.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported data-migration event type: {event_type}")
    values = dict(payload or {})
    unsafe = set(values) - SAFE_PAYLOAD_KEYS
    if unsafe:
        raise ValueError(f"event payload contains unsafe keys: {', '.join(sorted(unsafe))}")
    correlation = correlation_id or get_correlation_id() or str(uuid.uuid4())
    event_id = uuid.uuid4()
    return OutboxEvent.objects.create(
        id=event_id,
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload={
            "event_id": str(event_id),
            "schema_version": SCHEMA_VERSION,
            "tenant_id": str(tenant_id),
            "aggregate_type": aggregate_type,
            "aggregate_id": str(aggregate_id),
            "actor_id": str(actor_id) if actor_id else None,
            "correlation_id": correlation,
            "payload": values,
        },
    )


__all__ = ["EVENT_TYPES", "SCHEMA_VERSION", "publish_event"]
