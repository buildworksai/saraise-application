"""Versioned, tenant-scoped MDM transactional outbox events.

Only allow-listed operational metadata is accepted.  Master values, snapshots,
matching evidence, and quality evidence must never be copied into the outbox.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent
from src.core.observability import get_correlation_id, get_task_context

SCHEMA_VERSION: Final[int] = 1
EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "mdm.entity_type.created",
        "mdm.entity_type.updated",
        "mdm.entity_type.deactivated",
        "mdm.entity.created",
        "mdm.entity.updated",
        "mdm.entity.archived",
        "mdm.entity.restored",
        "mdm.entity.review_requested",
        "mdm.entity.review_approved",
        "mdm.entity.rolled_back",
        "mdm.entity.quality_scored",
        "mdm.quality_rule.created",
        "mdm.quality_rule.updated",
        "mdm.quality_rule.deactivated",
        "mdm.quality_issue.opened",
        "mdm.quality_issue.assigned",
        "mdm.quality_issue.resolved",
        "mdm.quality_issue.waived",
        "mdm.matching_rule.created",
        "mdm.matching_rule.updated",
        "mdm.matching_rule.deactivated",
        "mdm.match_candidate.created",
        "mdm.match_candidate.reviewed",
        "mdm.entities.merged",
        "mdm.merge.reversed",
    }
)

SAFE_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "changed_fields",
        "entity_type_id",
        "entity_type_key",
        "schema_version",
        "version",
        "status",
        "from_status",
        "to_status",
        "quality_score",
        "evaluated",
        "issue_count",
        "dimension_counts",
        "finding_summaries",
        "candidate_id",
        "matching_rule_id",
        "confidence",
        "decision",
        "merge_id",
        "golden_record_id",
        "source_entity_ids",
        "reason_code",
        "job_id",
        "command",
        "request_fingerprint",
    }
)


def _json_value(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("event decimal values must be finite")
        return str(value)
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            raise ValueError("event datetimes must be timezone-aware")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    raise TypeError(f"unsupported event value type: {type(value).__name__}")


def publish_domain_event(
    tenant_id: UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    *,
    actor_id: UUID | None,
    payload: Mapping[str, object] | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> OutboxEvent:
    """Persist a sanitized event in the caller's database transaction."""

    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported MDM event type: {event_type}")
    if not aggregate_type or len(aggregate_type) > 100:
        raise ValueError("aggregate_type must be a bounded non-empty string")
    supplied = dict(payload or {})
    unsafe = set(supplied) - SAFE_PAYLOAD_KEYS
    if unsafe:
        raise ValueError(f"event payload contains non-allowlisted keys: {', '.join(sorted(unsafe))}")

    task = get_task_context()
    correlation = correlation_id or get_correlation_id() or str(uuid.uuid4())
    cause = causation_id or (task.causation_id if task else None)
    event_id = uuid.uuid4()
    envelope = {
        "event_id": str(event_id),
        "schema_id": f"{event_type}.v{SCHEMA_VERSION}",
        "schema_version": SCHEMA_VERSION,
        "event_type": event_type,
        "tenant_id": str(tenant_id),
        "aggregate_type": aggregate_type,
        "aggregate_id": str(aggregate_id),
        "actor_id": str(actor_id) if actor_id else None,
        "correlation_id": correlation,
        "causation_id": cause,
        "occurred_at": timezone.now().isoformat(),
        "payload": {key: _json_value(value) for key, value in supplied.items()},
    }
    return OutboxEvent.objects.create(
        id=event_id,
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=envelope,
    )


__all__ = ["EVENT_TYPES", "SAFE_PAYLOAD_KEYS", "SCHEMA_VERSION", "publish_domain_event"]
