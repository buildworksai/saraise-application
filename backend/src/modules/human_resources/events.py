"""Versioned, PII-minimal Human Resources transactional-outbox events."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Final, cast
from uuid import UUID

from src.core.async_jobs.models import OutboxEvent
from src.core.observability import get_correlation_id, get_task_context

SCHEMA_VERSION: Final[int] = 1
EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "human_resources.department.created",
        "human_resources.department.updated",
        "human_resources.department.deactivated",
        "human_resources.department.archived",
        "human_resources.employee.created",
        "human_resources.employee.updated",
        "human_resources.employee.status_changed",
        "human_resources.employee.department_changed",
        "human_resources.employee.manager_changed",
        "human_resources.employee.terminated",
        "human_resources.employee.archived",
        "human_resources.attendance.recorded",
        "human_resources.attendance.clocked_in",
        "human_resources.attendance.clocked_out",
        "human_resources.attendance.corrected",
        "human_resources.attendance.archived",
        "human_resources.leave_balance.created",
        "human_resources.leave_balance.adjusted",
        "human_resources.leave_balance.reserved",
        "human_resources.leave_balance.consumed",
        "human_resources.leave_balance.released",
        "human_resources.leave_balance.archived",
        "human_resources.leave_request.submitted",
        "human_resources.leave_request.updated",
        "human_resources.leave_request.approved",
        "human_resources.leave_request.rejected",
        "human_resources.leave_request.cancelled",
        "human_resources.leave_request.archived",
    }
)

# Explicit allowlisting prevents reasons, contact details, or raw request data
# from becoming durable integration payloads.
SAFE_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "attendance_date",
        "command",
        "department_id",
        "effective_date",
        "employee_id",
        "fingerprint",
        "from_state",
        "idempotency_key",
        "leave_balance_id",
        "leave_request_id",
        "leave_type",
        "new_department_id",
        "new_manager_id",
        "period_end",
        "period_start",
        "previous_department_id",
        "previous_manager_id",
        "status",
        "to_state",
        "transition_key",
        "version",
    }
)


def _json_safe(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def publish_domain_event(
    tenant_id: UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    *,
    actor_id: str,
    payload: Mapping[str, object] | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> OutboxEvent:
    """Persist one validated event in the caller's database transaction."""

    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unsupported Human Resources event type: {event_type}")
    if not aggregate_type.strip() or len(aggregate_type) > 100:
        raise ValueError("aggregate_type must be a bounded non-empty string")
    supplied = dict(payload or {})
    unsafe = set(supplied) - SAFE_PAYLOAD_KEYS
    if unsafe:
        raise ValueError(f"Event payload contains non-allowlisted keys: {', '.join(sorted(unsafe))}")
    correlation = correlation_id or get_correlation_id() or str(uuid.uuid4())
    task_context = get_task_context()
    cause = causation_id or (task_context.causation_id if task_context else None)
    event_id = uuid.uuid4()
    occurred_at = datetime.now(timezone.utc).isoformat()
    safe_payload = cast(dict[str, object], _json_safe(supplied))
    envelope = {
        "event_id": str(event_id),
        "event_type": event_type,
        "schema_version": SCHEMA_VERSION,
        "tenant_id": str(tenant_id),
        "aggregate_type": aggregate_type,
        "aggregate_id": str(aggregate_id),
        "occurred_at": occurred_at,
        "actor_id": actor_id,
        "correlation_id": correlation,
        "causation_id": cause,
        "payload": safe_payload,
    }
    return cast(
        OutboxEvent,
        OutboxEvent.objects.create(
            id=event_id,
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=envelope,
        ),
    )


__all__ = ["EVENT_TYPES", "SAFE_PAYLOAD_KEYS", "SCHEMA_VERSION", "publish_domain_event"]
