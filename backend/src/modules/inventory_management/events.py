"""Versioned, allowlisted inventory transactional-outbox events."""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent
from src.core.observability import get_correlation_id

EVENT_SCHEMA_VERSION: Final = 1
EVENT_TYPES: Final = frozenset(
    {
        "inventory.warehouse.created/v1",
        "inventory.item.updated/v1",
        "inventory.stock_entry.submitted/v1",
        "inventory.stock.posted/v1",
        "inventory.stock.reversed/v1",
        "inventory.reservation.changed/v1",
        "inventory.batch.recalled/v1",
        "inventory.cycle_count.posted/v1",
    }
)

EVENT_PAYLOAD_FIELDS: Final[Mapping[str, frozenset[str]]] = {
    "inventory.warehouse.created/v1": frozenset({"warehouse_code", "warehouse_type", "is_default"}),
    "inventory.item.updated/v1": frozenset({"item_code", "tracking_mode", "valuation_method", "version"}),
    "inventory.stock_entry.submitted/v1": frozenset({"entry_number", "entry_type", "line_count", "status"}),
    "inventory.stock.posted/v1": frozenset(
        {"entry_number", "entry_type", "ledger_sequence_from", "ledger_sequence_to", "status"}
    ),
    "inventory.stock.reversed/v1": frozenset({"entry_number", "reversal_entry_id", "status"}),
    "inventory.reservation.changed/v1": frozenset(
        {"reservation_number", "item_id", "quantity", "from_status", "to_status"}
    ),
    "inventory.batch.recalled/v1": frozenset({"batch_number", "item_id", "status"}),
    "inventory.cycle_count.posted/v1": frozenset(
        {"count_number", "warehouse_id", "adjustment_entry_id", "variance_line_count", "status"}
    ),
}

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:@/+\-]{1,255}$")


def _uuid(value: UUID | str, field_name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc


def _identifier(value: object, field_name: str, maximum: int) -> str:
    normalized = str(value)
    if len(normalized) > maximum or _SAFE_IDENTIFIER.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must be a bounded safe identifier")
    return normalized


def _json_value(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("event decimal values must be finite")
        return str(value)
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            raise ValueError("event datetime values must be timezone-aware")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("event float values must be finite")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    raise TypeError(f"event value of type {type(value).__name__} is not JSON serializable")


def publish_domain_event(
    tenant_id: UUID | str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID | str,
    *,
    correlation_id: str | None = None,
    actor_id: UUID | str | None = None,
    occurred_at: datetime | None = None,
    payload: Mapping[str, object] | None = None,
) -> OutboxEvent:
    """Persist a validated outbox event in the caller's active transaction."""

    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported inventory event type: {event_type}")
    safe_aggregate_type = _identifier(aggregate_type, "aggregate_type", 100)
    supplied_payload = dict(payload or {})
    unsupported = set(supplied_payload) - EVENT_PAYLOAD_FIELDS[event_type]
    if unsupported:
        raise ValueError(f"event payload contains non-allowlisted keys: {', '.join(sorted(unsupported))}")
    tenant = _uuid(tenant_id, "tenant_id")
    aggregate = _uuid(aggregate_id, "aggregate_id")
    correlation = _identifier(
        correlation_id or get_correlation_id() or uuid.uuid4(),
        "correlation_id",
        64,
    )
    actor = _identifier(actor_id, "actor_id", 64) if actor_id is not None else None
    timestamp = occurred_at or timezone.now()
    if timezone.is_naive(timestamp):
        raise ValueError("occurred_at must be timezone-aware")
    event_id = uuid.uuid4()
    event_payload = {
        "event_id": str(event_id),
        "schema_id": event_type,
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_version": 1,
        "event_type": event_type,
        "module": "inventory_management",
        "tenant_id": str(tenant),
        "aggregate_type": safe_aggregate_type,
        "aggregate_id": str(aggregate),
        "actor_id": actor,
        "correlation_id": correlation,
        "occurred_at": timestamp.isoformat(),
        "payload": {key: _json_value(value) for key, value in supplied_payload.items()},
    }
    return OutboxEvent.objects.create(
        id=event_id,
        tenant_id=tenant,
        aggregate_type=safe_aggregate_type,
        aggregate_id=aggregate,
        event_type=event_type,
        payload=event_payload,
    )


# Concise alias for service call sites.
emit_event = publish_domain_event

__all__ = ["EVENT_PAYLOAD_FIELDS", "EVENT_SCHEMA_VERSION", "EVENT_TYPES", "emit_event", "publish_domain_event"]
