"""Versioned transactional-outbox ABI for email marketing.

Payloads are accepted through per-event allowlists. Raw addresses, message
bodies, personalization, signed links, provider bodies, and tokens therefore
cannot enter the integration bus by accident.
"""

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
from src.core.observability import get_correlation_id, get_task_context

EVENT_SCHEMA_VERSION: Final = 1
EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "email_marketing.campaign.created.v1",
        "email_marketing.campaign.scheduled.v1",
        "email_marketing.campaign.send_queued.v1",
        "email_marketing.campaign.sent.v1",
        "email_marketing.campaign.failed.v1",
        "email_marketing.email.sent.v1",
        "email_marketing.email.delivered.v1",
        "email_marketing.email.opened.v1",
        "email_marketing.email.clicked.v1",
        "email_marketing.email.bounced.v1",
        "email_marketing.email.unsubscribed.v1",
        "email_marketing.consent.changed.v1",
        "email_marketing.suppression.changed.v1",
    }
)

_COMMON_EMAIL_FIELDS = frozenset(
    {
        "campaign_id",
        "recipient_id",
        "attempt_id",
        "gateway_key",
        "provider_message_id",
        "attempt_number",
        "bounce_class",
        "link_url_hash",
        "delivery_status",
    }
)
EVENT_PAYLOAD_FIELDS: Final[Mapping[str, frozenset[str]]] = {
    "email_marketing.campaign.created.v1": frozenset({"campaign_code", "campaign_type", "status"}),
    "email_marketing.campaign.scheduled.v1": frozenset({"scheduled_at", "timezone", "status"}),
    "email_marketing.campaign.send_queued.v1": frozenset(
        {"eligible_recipient_count", "resolved_recipient_count", "template_version", "status"}
    ),
    "email_marketing.campaign.sent.v1": frozenset(
        {"sent_count", "delivered_count", "failed_count", "bounced_count", "status"}
    ),
    "email_marketing.campaign.failed.v1": frozenset({"error_code", "status"}),
    "email_marketing.email.sent.v1": _COMMON_EMAIL_FIELDS,
    "email_marketing.email.delivered.v1": _COMMON_EMAIL_FIELDS,
    "email_marketing.email.opened.v1": _COMMON_EMAIL_FIELDS,
    "email_marketing.email.clicked.v1": _COMMON_EMAIL_FIELDS,
    "email_marketing.email.bounced.v1": _COMMON_EMAIL_FIELDS,
    "email_marketing.email.unsubscribed.v1": _COMMON_EMAIL_FIELDS,
    "email_marketing.consent.changed.v1": frozenset(
        {"consent_record_id", "purpose", "status", "source", "lawful_basis"}
    ),
    "email_marketing.suppression.changed.v1": frozenset({"suppression_id", "active", "scope", "reason", "source"}),
}
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:@+-]{1,255}$")


def _uuid(value: UUID | str, field_name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc


def _identifier(value: object, field_name: str, *, maximum: int = 255) -> str:
    normalized = str(value)
    if len(normalized) > maximum or not _SAFE_IDENTIFIER.fullmatch(normalized):
        raise ValueError(f"{field_name} must be a bounded safe identifier")
    return normalized


def _json_value(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("event decimals must be finite")
        return str(value)
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            raise ValueError("event datetimes must be timezone-aware")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("event floats must be finite")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    raise TypeError(f"event value of type {type(value).__name__} is not serializable")


def publish_domain_event(
    tenant_id: UUID | str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID | str,
    *,
    actor_id: UUID | str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    job_id: UUID | str | None = None,
    occurred_at: datetime | None = None,
    payload: Mapping[str, object] | None = None,
) -> OutboxEvent:
    """Persist one schema-validated event in the caller's transaction."""

    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported email-marketing event type: {event_type}")
    if not aggregate_type or len(aggregate_type) > 100 or not _SAFE_IDENTIFIER.fullmatch(aggregate_type):
        raise ValueError("aggregate_type must be a bounded safe identifier")
    supplied = dict(payload or {})
    unsafe = set(supplied) - EVENT_PAYLOAD_FIELDS[event_type]
    if unsafe:
        raise ValueError(f"event payload contains non-allowlisted keys: {', '.join(sorted(unsafe))}")

    tenant = _uuid(tenant_id, "tenant_id")
    aggregate = _uuid(aggregate_id, "aggregate_id")
    task = get_task_context()
    correlation = _identifier(correlation_id or get_correlation_id() or uuid.uuid4(), "correlation_id", maximum=64)
    cause = causation_id or (task.causation_id if task else None)
    safe_cause = _identifier(cause, "causation_id", maximum=128) if cause else None
    resolved_job = job_id or (task.job_id if task else None)
    safe_job = str(_uuid(resolved_job, "job_id")) if resolved_job else None
    safe_actor = _identifier(actor_id, "actor_id") if actor_id is not None else None
    timestamp = occurred_at or timezone.now()
    if timezone.is_naive(timestamp):
        raise ValueError("occurred_at must be timezone-aware")
    event_id = uuid.uuid4()
    envelope = {
        "event_id": str(event_id),
        "schema_id": event_type,
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_version": 1,
        "event_type": event_type,
        "module": "email_marketing",
        "tenant_id": str(tenant),
        "aggregate_type": aggregate_type,
        "aggregate_id": str(aggregate),
        "actor_id": safe_actor,
        "correlation_id": correlation,
        "causation_id": safe_cause,
        "job_id": safe_job,
        "occurred_at": timestamp.isoformat(),
        "payload": {key: _json_value(value) for key, value in supplied.items()},
    }
    return OutboxEvent.objects.create(
        id=event_id,
        tenant_id=tenant,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate,
        event_type=event_type,
        payload=envelope,
    )


__all__ = [
    "EVENT_PAYLOAD_FIELDS",
    "EVENT_SCHEMA_VERSION",
    "EVENT_TYPES",
    "publish_domain_event",
]
