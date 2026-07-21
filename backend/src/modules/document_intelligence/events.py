"""Durable, sanitized domain events for document intelligence."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Final
from uuid import UUID

from src.core.async_jobs.models import OutboxEvent
from src.core.observability import get_correlation_id, get_task_context

SCHEMA_VERSION: Final[int] = 1
EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "document_intelligence.extraction.started",
        "document_intelligence.extraction.completed",
        "document_intelligence.extraction.needs_review",
        "document_intelligence.extraction.failed",
        "document_intelligence.classification.completed",
        "document_intelligence.classification.low_confidence",
        "document_intelligence.classification.reviewed",
        "document_intelligence.training.started",
        "document_intelligence.training.completed",
        "document_intelligence.training.failed",
        "document_intelligence.model.activated",
        "document_intelligence.model.rolled_back",
        "document_intelligence.template.created",
        "document_intelligence.template.activated",
        "document_intelligence.template.matched",
    }
)

# Event payloads are allowlisted rather than scrubbed after the fact.  This
# prevents content, provider bodies, signed URLs, and credentials from entering
# the outbox when an adapter adds a new field.
SAFE_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "status",
        "from_status",
        "to_status",
        "engine",
        "provider_key",
        "extraction_type",
        "page_count",
        "training_data_count",
        "model_version_id",
        "template_id",
        "matched",
        "review_status",
        "failure_code",
        "duration_ms",
    }
)


def publish_domain_event(
    tenant_id: UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    *,
    actor_id: UUID | None,
    payload: Mapping[str, object] | None = None,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> OutboxEvent:
    """Persist one transactional-outbox event in the caller's transaction."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported document-intelligence event type: {event_type}")
    if not aggregate_type or len(aggregate_type) > 100:
        raise ValueError("aggregate_type must be a bounded non-empty string")
    supplied = dict(payload or {})
    unsafe = set(supplied) - SAFE_PAYLOAD_KEYS
    if unsafe:
        raise ValueError(f"event payload contains non-allowlisted keys: {', '.join(sorted(unsafe))}")

    task_context = get_task_context()
    correlation = correlation_id or get_correlation_id() or str(uuid.uuid4())
    cause = causation_id or (task_context.causation_id if task_context else None)
    event_id = uuid.uuid4()
    timestamp = datetime.now(timezone.utc).isoformat()
    envelope = {
        "event_id": str(event_id),
        "schema_version": SCHEMA_VERSION,
        "tenant_id": str(tenant_id),
        "aggregate_id": str(aggregate_id),
        "aggregate_type": aggregate_type,
        "actor_id": str(actor_id) if actor_id else None,
        "correlation_id": correlation,
        "causation_id": cause,
        "timestamp": timestamp,
        "payload": supplied,
    }
    return OutboxEvent.objects.create(
        id=event_id,
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=envelope,
    )


__all__ = ["EVENT_TYPES", "SCHEMA_VERSION", "publish_domain_event"]
