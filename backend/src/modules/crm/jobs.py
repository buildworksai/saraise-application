"""CRM durable commands, worker entry points, and transactional events."""

from __future__ import annotations

import logging
import math
import re
import uuid
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Final, Iterator, cast
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue, register_handler
from src.core.middleware.correlation import correlation_id_var
from src.core.observability import get_correlation_id, get_task_context
from src.core.tenancy import tenant_context, tenant_context_worker

from .integrations import verify_fulfillment_acknowledgement
from .models import Opportunity, OpportunityStatus

logger = logging.getLogger("saraise.crm.jobs")

STALE_DEAL_COMMAND: Final = "crm.scan_stale_deals"
LEAD_SCORING_COMMAND: Final = "crm.score_lead"
EXTERNAL_ACTIVITY_COMMAND: Final = "crm.sync_external_activity"
FULFILLMENT_ACK_COMMAND: Final = "crm.acknowledge_sales_order"
EVENT_SCHEMA_VERSION: Final[int] = 1
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "crm.lead.created",
        "crm.lead.updated",
        "crm.lead.deleted",
        "crm.lead.contacted",
        "crm.lead.qualified",
        "crm.lead.disqualified",
        "crm.lead.status_changed",
        "crm.lead.scored",
        "crm.lead.converted",
        "crm.account.created",
        "crm.account.updated",
        "crm.account.deleted",
        "crm.account.became_customer",
        "crm.contact.created",
        "crm.contact.updated",
        "crm.contact.deleted",
        "crm.contact.engagement_recalculated",
        "crm.opportunity.created",
        "crm.opportunity.updated",
        "crm.opportunity.deleted",
        "crm.opportunity.stage_changed",
        "crm.opportunity.closed_won",
        "crm.opportunity.closed_lost",
        "crm.opportunity.order_acknowledged",
        "crm.activity.created",
        "crm.activity.updated",
        "crm.activity.deleted",
        "crm.activity.completed",
        "crm.activity.external_synced",
        "crm.stale_deal.detected",
    }
)

# Payload data is allowlisted. Contact fields, activity bodies, prompts,
# credentials, and provider response bodies can never enter the outbox.
SAFE_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "version",
        "changed_fields",
        "source",
        "score",
        "grade",
        "score_source",
        "status",
        "from_status",
        "to_status",
        "from_stage",
        "to_stage",
        "command",
        "transition_key",
        "account_id",
        "contact_id",
        "opportunity_id",
        "amount",
        "currency",
        "close_date",
        "loss_code",
        "activity_type",
        "related_to_type",
        "related_to_id",
        "completed",
        "external_id",
        "engagement_score",
        "stale_days",
        "stale_interval",
        "detected_at",
        "owner_id",
        "order_id",
        "acknowledgement_id",
        "provider",
        "model",
        "evidence_factors",
        "period_days",
        "as_of",
        "conversion_decision",
    }
)


class JobIdempotencyConflict(RuntimeError):
    """Raised when a caller reuses a CRM key for different work."""


def _uuid(value: UUID | str, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field} must be a valid UUID") from exc


def _identifier(value: object, field: str, *, maximum: int = 128) -> str:
    result = str(value)
    if not result or len(result) > maximum or not _SAFE_ID.fullmatch(result):
        raise ValueError(f"{field} must be a bounded safe identifier")
    return result


def _aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or timezone.is_naive(value):
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _json_value(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("event decimals must be finite")
        return str(value)
    if isinstance(value, datetime):
        return _aware(value, "event datetime").isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    raise TypeError(f"event value of type {type(value).__name__} is not serializable")


def publish_crm_event(
    tenant_id: UUID | str,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID | str,
    actor_id: str | UUID | None,
    correlation_id: str | None,
    payload: Mapping[str, object] | None = None,
    causation_id: str | None = None,
    job_id: UUID | str | None = None,
) -> OutboxEvent:
    """Persist a versioned event in the caller's database transaction."""

    tenant = _uuid(tenant_id, "tenant_id")
    aggregate = _uuid(aggregate_id, "aggregate_id")
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported CRM event type: {event_type}")
    if not isinstance(aggregate_type, str) or not aggregate_type or len(aggregate_type) > 100:
        raise ValueError("aggregate_type must be a bounded non-empty string")
    supplied = dict(payload or {})
    unsafe = set(supplied) - SAFE_PAYLOAD_KEYS
    if unsafe:
        raise ValueError(f"CRM event contains non-allowlisted fields: {', '.join(sorted(unsafe))}")

    task = get_task_context()
    correlation = _identifier(correlation_id or get_correlation_id() or uuid.uuid4(), "correlation_id")
    cause = causation_id or (task.causation_id if task else None)
    if cause is not None:
        cause = _identifier(cause, "causation_id")
    resolved_job_id = job_id or (task.job_id if task else None)
    if resolved_job_id is not None:
        resolved_job_id = str(_uuid(resolved_job_id, "job_id"))
    actor = None if actor_id is None else str(actor_id)
    if actor is not None and (not actor.strip() or len(actor) > 255):
        raise ValueError("actor_id must be a bounded non-empty identifier")

    event_id = uuid.uuid4()
    envelope = {
        "event_id": str(event_id),
        "schema_id": f"{event_type}.v{EVENT_SCHEMA_VERSION}",
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_type": event_type,
        "module": "crm",
        "tenant_id": str(tenant),
        "aggregate_type": aggregate_type,
        "aggregate_id": str(aggregate),
        "actor_id": actor,
        "correlation_id": correlation,
        "causation_id": cause,
        "job_id": resolved_job_id,
        "occurred_at": timezone.now().isoformat(),
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


@contextmanager
def _bound_correlation(correlation_id: str) -> Iterator[None]:
    value = _identifier(correlation_id, "correlation_id", maximum=64)
    token = correlation_id_var.set(value)
    try:
        yield
    finally:
        correlation_id_var.reset(token)


def _enqueue_checked(
    tenant_id: UUID,
    *,
    actor_id: str | UUID,
    command: str,
    payload: dict[str, object],
    idempotency_key: str,
    correlation_id: str,
) -> AsyncJob:
    namespaced_key = f"{command}:{idempotency_key.strip()}"
    if not idempotency_key.strip():
        raise ValueError("idempotency_key must not be empty")
    if len(namespaced_key) > 255:
        raise ValueError("namespaced idempotency_key must not exceed 255 characters")
    with tenant_context(tenant_id), _bound_correlation(correlation_id):
        job = enqueue(tenant_id, actor_id, command, payload, namespaced_key)
        if job.command != command or job.payload != payload:
            raise JobIdempotencyConflict("Idempotency key is already associated with different CRM work")
        return job


def enqueue_stale_deal_scan(
    tenant_id: UUID | str,
    *,
    as_of: datetime,
    idempotency_key: str,
    actor_id: str | UUID,
    correlation_id: str,
) -> AsyncJob:
    """Durably enqueue one tenant-bounded stale-deal scan."""

    tenant = _uuid(tenant_id, "tenant_id")
    effective_as_of = _aware(as_of, "as_of")
    return _enqueue_checked(
        tenant,
        actor_id=actor_id,
        command=STALE_DEAL_COMMAND,
        payload={"as_of": effective_as_of.isoformat()},
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )


def enqueue_lead_scoring_job(
    tenant_id: UUID | str,
    *,
    lead_id: UUID | str,
    idempotency_key: str,
    actor_id: str | UUID,
    correlation_id: str,
) -> AsyncJob:
    tenant = _uuid(tenant_id, "tenant_id")
    return _enqueue_checked(
        tenant,
        actor_id=actor_id,
        command=LEAD_SCORING_COMMAND,
        payload={"lead_id": str(_uuid(lead_id, "lead_id"))},
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )


def enqueue_external_activity_job(
    tenant_id: UUID | str,
    *,
    event: Mapping[str, object],
    idempotency_key: str,
    actor_id: str | UUID,
    correlation_id: str,
) -> AsyncJob:
    tenant = _uuid(tenant_id, "tenant_id")
    if not isinstance(event, Mapping):
        raise TypeError("event must be a mapping")
    # Make a JSON-safe detached payload now; never enqueue a mutable caller object.
    safe_event = _json_value(dict(event))
    assert isinstance(safe_event, dict)
    return _enqueue_checked(
        tenant,
        actor_id=actor_id,
        command=EXTERNAL_ACTIVITY_COMMAND,
        payload={"event": safe_event},
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )


def enqueue_fulfillment_acknowledgement_job(
    tenant_id: UUID | str,
    *,
    event: Mapping[str, object],
    idempotency_key: str,
    actor_id: str | UUID,
    correlation_id: str,
) -> AsyncJob:
    """Durably accept only a trusted-bus verified sales-order event."""

    tenant = _uuid(tenant_id, "tenant_id")
    acknowledgement = verify_fulfillment_acknowledgement(event)
    if acknowledgement.tenant_id != tenant:
        raise ValueError("fulfillment acknowledgement belongs to another tenant")
    safe_event = _json_value(dict(event))
    assert isinstance(safe_event, dict)
    return _enqueue_checked(
        tenant,
        actor_id=actor_id,
        command=FULFILLMENT_ACK_COMMAND,
        payload={"event": safe_event},
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )


def _stale_days() -> int:
    value = getattr(settings, "CRM_STALE_DEAL_DAYS", 14)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 365:
        raise ValueError("CRM_STALE_DEAL_DAYS must be an integer from 1 to 365")
    return value


def _reference_time(opportunity: Opportunity) -> datetime:
    value = opportunity.last_activity_at or opportunity.updated_at or opportunity.created_at
    return _aware(value, "opportunity activity timestamp")


def _already_emitted(tenant_id: UUID, opportunity_id: UUID, interval: int) -> bool:
    envelopes = OutboxEvent.objects.filter(
        tenant_id=tenant_id,
        aggregate_type="opportunity",
        aggregate_id=opportunity_id,
        event_type="crm.stale_deal.detected",
    ).values_list("payload", flat=True)
    return any(
        isinstance(envelope, Mapping)
        and isinstance(envelope.get("payload"), Mapping)
        and envelope["payload"].get("stale_interval") == interval
        for envelope in envelopes
    )


@tenant_context_worker
def scan_stale_deals(*, tenant_id: UUID, as_of: datetime) -> dict[str, int]:
    """Emit one durable alert per opportunity and elapsed stale interval."""

    effective_as_of = _aware(as_of, "as_of")
    stale_days = _stale_days()
    cutoff = effective_as_of - timedelta(days=stale_days)
    emitted = 0
    with transaction.atomic():
        candidates = (
            Opportunity.objects.select_for_update()
            .filter(tenant_id=tenant_id, is_deleted=False, status=OpportunityStatus.OPEN)
            .filter(Q(last_activity_at__lt=cutoff) | Q(last_activity_at__isnull=True, updated_at__lt=cutoff))
            .order_by("id")
        )
        for raw_opportunity in candidates.iterator(chunk_size=200):
            opportunity = cast(Opportunity, raw_opportunity)
            elapsed = (effective_as_of - _reference_time(opportunity)).total_seconds()
            interval = math.floor(elapsed / timedelta(days=stale_days).total_seconds())
            if interval < 1 or _already_emitted(tenant_id, opportunity.id, interval):
                continue
            publish_crm_event(
                tenant_id,
                event_type="crm.stale_deal.detected",
                aggregate_type="opportunity",
                aggregate_id=opportunity.id,
                actor_id=None,
                correlation_id=get_correlation_id() or None,
                payload={
                    "stale_days": stale_days,
                    "stale_interval": interval,
                    "detected_at": effective_as_of,
                    "owner_id": opportunity.owner_id,
                    "currency": opportunity.currency,
                    "close_date": opportunity.close_date,
                },
            )
            emitted += 1

    logger.info(
        "crm stale-deal scan completed",
        extra={
            "event": "crm.job.completed",
            "module_name": "crm",
            "operation": "scan_stale_deals",
            "outcome": "succeeded",
            "tenant_id": str(tenant_id),
            "emitted_alert_count": emitted,
        },
    )
    return {"emitted_alerts": emitted}


@tenant_context_worker
def process_lead_scoring_job(*, tenant_id: UUID, lead_id: UUID, job_id: UUID) -> dict[str, object]:
    """Run authoritative provider scoring; unavailable providers fail the job."""

    from .services import LeadService

    job = AsyncJob.objects.get(tenant_id=tenant_id, id=job_id, command=LEAD_SCORING_COMMAND)
    result = LeadService.score_lead(
        tenant_id,
        lead_id=lead_id,
        actor_id=job.actor_id,
        correlation_id=job.correlation_id,
    )
    lead = result.unwrap()
    return {
        "lead_id": str(lead.id),
        "score": lead.score,
        "grade": lead.grade,
        "score_source": lead.score_source,
        "version": lead.version,
    }


@tenant_context_worker
def process_external_activity_event(*, tenant_id: UUID, event: Mapping[str, object], job_id: UUID) -> dict[str, object]:
    """Idempotently synchronize one published external activity event."""

    from .services import ActivityService

    job = AsyncJob.objects.get(tenant_id=tenant_id, id=job_id, command=EXTERNAL_ACTIVITY_COMMAND)
    activity = ActivityService.sync_external_activity(
        tenant_id,
        event=dict(event),
        idempotency_key=str(job.id),
        correlation_id=job.correlation_id,
    )
    return {"activity_id": str(activity.id), "version": activity.version}


@tenant_context_worker
def process_fulfillment_acknowledgement(
    *, tenant_id: UUID, event: Mapping[str, object], job_id: UUID
) -> dict[str, object]:
    """Link a won opportunity only after strict acknowledgement verification."""

    from .services import OpportunityService

    job = AsyncJob.objects.get(tenant_id=tenant_id, id=job_id, command=FULFILLMENT_ACK_COMMAND)
    acknowledgement = verify_fulfillment_acknowledgement(event)
    if acknowledgement.tenant_id != tenant_id:
        raise ValueError("fulfillment acknowledgement belongs to another tenant")
    opportunity = OpportunityService.acknowledge_sales_order(
        tenant_id,
        opportunity_id=acknowledgement.opportunity_id,
        order_id=acknowledgement.external_order_id,
        acknowledgement_id=acknowledgement.acknowledgement_id,
        idempotency_key=str(job.id),
        actor_id=job.actor_id,
        correlation_id=acknowledgement.correlation_id or job.correlation_id,
    )
    return {
        "opportunity_id": str(opportunity.id),
        "order_id": str(opportunity.converted_to_order_id),
        "version": opportunity.version,
    }


@register_handler(STALE_DEAL_COMMAND)  # type: ignore[arg-type]
def _stale_deal_handler(job: AsyncJob) -> dict[str, int]:
    raw_as_of = job.payload.get("as_of")
    if not isinstance(raw_as_of, str):
        raise ValueError("stale-deal command requires as_of")
    as_of = datetime.fromisoformat(raw_as_of.replace("Z", "+00:00"))
    return scan_stale_deals(tenant_id=job.tenant_id, as_of=as_of)


@register_handler(LEAD_SCORING_COMMAND)  # type: ignore[arg-type]
def _lead_scoring_handler(job: AsyncJob) -> dict[str, object]:
    return process_lead_scoring_job(
        tenant_id=job.tenant_id,
        lead_id=_uuid(job.payload.get("lead_id"), "lead_id"),
        job_id=job.id,
    )


@register_handler(EXTERNAL_ACTIVITY_COMMAND)  # type: ignore[arg-type]
def _external_activity_handler(job: AsyncJob) -> dict[str, object]:
    event = job.payload.get("event")
    if not isinstance(event, Mapping):
        raise ValueError("external-activity command requires an event object")
    return process_external_activity_event(tenant_id=job.tenant_id, event=event, job_id=job.id)


@register_handler(FULFILLMENT_ACK_COMMAND)  # type: ignore[arg-type]
def _fulfillment_ack_handler(job: AsyncJob) -> dict[str, object]:
    event = job.payload.get("event")
    if not isinstance(event, Mapping):
        raise ValueError("fulfillment-acknowledgement command requires an event object")
    return process_fulfillment_acknowledgement(tenant_id=job.tenant_id, event=event, job_id=job.id)


__all__ = [
    "EVENT_SCHEMA_VERSION",
    "EVENT_TYPES",
    "EXTERNAL_ACTIVITY_COMMAND",
    "FULFILLMENT_ACK_COMMAND",
    "JobIdempotencyConflict",
    "LEAD_SCORING_COMMAND",
    "SAFE_PAYLOAD_KEYS",
    "STALE_DEAL_COMMAND",
    "enqueue_external_activity_job",
    "enqueue_fulfillment_acknowledgement_job",
    "enqueue_lead_scoring_job",
    "enqueue_stale_deal_scan",
    "process_external_activity_event",
    "process_fulfillment_acknowledgement",
    "process_lead_scoring_job",
    "publish_crm_event",
    "scan_stale_deals",
]
