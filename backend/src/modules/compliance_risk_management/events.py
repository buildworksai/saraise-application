"""Versioned, sanitized compliance-risk transactional outbox events.

Callers must invoke :func:`publish_domain_event` inside the same atomic
transaction as the aggregate mutation.  Payloads contain identifiers and
operational state only; narrative risk, finding, mitigation, and evidence
content is deliberately forbidden.
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
        "risk.created.v1",
        "risk.updated.v1",
        "risk.deleted.v1",
        "risk.status_changed.v1",
        "risk.transitioned.v1",
        "risk.level_changed.v1",
        "control.created.v1",
        "control.updated.v1",
        "control.deleted.v1",
        "control.status_changed.v1",
        "control.transitioned.v1",
        "control_test.scheduled.v1",
        "control_test.started.v1",
        "control_test.updated.v1",
        "control_test.completed.v1",
        "control_test.cancelled.v1",
        "requirement.created.v1",
        "requirement.updated.v1",
        "requirement.deleted.v1",
        "requirement.status_changed.v1",
        "calendar.created.v1",
        "calendar.updated.v1",
        "calendar.deleted.v1",
        "calendar.status_changed.v1",
        "calendar.transitioned.v1",
        "calendar.reminder_due.v1",
        "remediation.created.v1",
        "remediation.updated.v1",
        "remediation.deleted.v1",
        "remediation.status_changed.v1",
        "remediation.transitioned.v1",
        "remediation.overdue.v1",
        "configuration.published.v1",
        "configuration.rolled_back.v1",
        "configuration.imported.v1",
        "risk_configuration.published.v1",
    }
)

# The values behind these keys may be copied to an external broker.  Never add
# narrative or evidence keys here merely for convenience.
SAFE_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "action_code",
        "changed_fields",
        "command",
        "configuration_version",
        "control_code",
        "control_id",
        "control_test_id",
        "due_date",
        "environment",
        "from_level",
        "from_status",
        "job_id",
        "priority",
        "regulation_code",
        "remediation_id",
        "requirement_code",
        "requirement_id",
        "result",
        "restored_from_version",
        "risk_code",
        "risk_id",
        "scheduled_date",
        "scheduled_for",
        "score",
        "to_level",
        "to_status",
        "transition_key",
        "version",
    }
)


def _uuid(value: UUID | str, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field} must be a valid UUID") from exc


def _json_value(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Event decimal values must be finite")
        return str(value)
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            raise ValueError("Event datetimes must be timezone-aware")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    raise TypeError(f"Unsupported event value type: {type(value).__name__}")


def publish_domain_event(
    tenant_id: UUID | str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID | str,
    *,
    actor_id: UUID | str | None,
    payload: Mapping[str, object] | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> OutboxEvent:
    """Persist one typed event without leaking sensitive aggregate content."""

    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unsupported compliance-risk event type: {event_type}")
    if not isinstance(aggregate_type, str) or not aggregate_type.strip() or len(aggregate_type) > 100:
        raise ValueError("aggregate_type must be a bounded non-empty string")
    tenant = _uuid(tenant_id, "tenant_id")
    aggregate = _uuid(aggregate_id, "aggregate_id")
    actor = _uuid(actor_id, "actor_id") if actor_id is not None else None
    supplied = dict(payload or {})
    unsafe = set(supplied) - SAFE_PAYLOAD_KEYS
    if unsafe:
        raise ValueError(f"Event payload contains non-allowlisted keys: {', '.join(sorted(unsafe))}")

    task = get_task_context()
    correlation = correlation_id or get_correlation_id() or str(uuid.uuid4())
    if not isinstance(correlation, str) or not correlation.strip() or len(correlation) > 64:
        raise ValueError("correlation_id must be a bounded non-empty string")
    cause = causation_id or (task.causation_id if task else None)
    event_id = uuid.uuid4()
    envelope = {
        "event_id": str(event_id),
        "schema_id": event_type,
        "schema_version": SCHEMA_VERSION,
        "event_type": event_type,
        "tenant_id": str(tenant),
        "aggregate_type": aggregate_type.strip(),
        "aggregate_id": str(aggregate),
        "actor_id": str(actor) if actor else None,
        "correlation_id": correlation,
        "causation_id": cause,
        "occurred_at": timezone.now().isoformat(),
        "payload": {key: _json_value(value) for key, value in supplied.items()},
    }
    return OutboxEvent.objects.create(
        id=event_id,
        tenant_id=tenant,
        aggregate_type=aggregate_type.strip(),
        aggregate_id=aggregate,
        event_type=event_type,
        payload=envelope,
    )


# Public service-layer aliases kept intentionally explicit for extension DX.
emit_domain_event = publish_domain_event
publish_event = publish_domain_event

__all__ = [
    "EVENT_TYPES",
    "SAFE_PAYLOAD_KEYS",
    "SCHEMA_VERSION",
    "emit_domain_event",
    "publish_domain_event",
    "publish_event",
]
