"""Versioned, allowlisted transactional-outbox events for reconciliation."""

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
        "bank_reconciliation.account.created",
        "bank_reconciliation.account.updated",
        "bank_reconciliation.account.archived",
        "bank_reconciliation.statement.import.requested",
        "bank_reconciliation.statement.import.succeeded",
        "bank_reconciliation.statement.import.failed",
        "bank_reconciliation.statement.import.cancelled",
        "bank_reconciliation.statement.created",
        "bank_reconciliation.statement.voided",
        "bank_reconciliation.transaction.created",
        "bank_reconciliation.transaction.updated",
        "bank_reconciliation.transaction.excluded",
        "bank_reconciliation.transaction.restored",
        "bank_reconciliation.rule.created",
        "bank_reconciliation.rule.updated",
        "bank_reconciliation.rule.activated",
        "bank_reconciliation.rule.deactivated",
        "bank_reconciliation.rule.deleted",
        "bank_reconciliation.reconciliation.created",
        "bank_reconciliation.reconciliation.started",
        "bank_reconciliation.reconciliation.review_submitted",
        "bank_reconciliation.reconciliation.returned",
        "bank_reconciliation.reconciliation.finalized",
        "bank_reconciliation.reconciliation.voided",
        "bank_reconciliation.match.proposed",
        "bank_reconciliation.match.confirmed",
        "bank_reconciliation.match.rejected",
        "bank_reconciliation.match.reversed",
        "bank_reconciliation.candidates.generated",
        "bank_reconciliation.reconciliation.report_exported",
    }
)

# Identifiers, totals, lifecycle evidence and stable error codes only. Account
# numbers, transaction text/source data, raw files and counterparty data cannot
# enter the outbox through this API.
SAFE_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "status",
        "from_status",
        "to_status",
        "bank_account_id",
        "statement_id",
        "statement_import_id",
        "reconciliation_id",
        "match_id",
        "rule_id",
        "async_job_id",
        "job_id",
        "file_format",
        "source",
        "rows_received",
        "rows_imported",
        "rows_rejected",
        "failure_code",
        "statement_balance",
        "ledger_balance",
        "matched_amount",
        "unmatched_amount",
        "difference",
        "tolerance",
        "match_type",
        "score",
        "provider_key",
        "provider_version",
        "proposal_count",
        "rule_type",
        "reason_provided",
        "duration_ms",
        "currency",
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
    """Persist one sanitized event inside the caller's database transaction."""
    try:
        tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
        aggregate_uuid = aggregate_id if isinstance(aggregate_id, UUID) else UUID(str(aggregate_id))
        actor_uuid = None if actor_id is None else actor_id if isinstance(actor_id, UUID) else UUID(str(actor_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("event tenant, aggregate and actor identifiers must be UUIDs") from exc
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported bank-reconciliation event type: {event_type}")
    if not aggregate_type or len(aggregate_type) > 100:
        raise ValueError("aggregate_type must be a bounded non-empty string")
    supplied = dict(payload or {})
    unsafe = set(supplied) - SAFE_PAYLOAD_KEYS
    if unsafe:
        raise ValueError(f"event payload contains non-allowlisted keys: {', '.join(sorted(unsafe))}")
    task_context = get_task_context()
    correlation = str(correlation_id or get_correlation_id() or uuid.uuid4())[:64]
    cause = causation_id or (task_context.causation_id if task_context else None)
    event_id = uuid.uuid4()
    envelope = {
        "event_id": str(event_id),
        "schema_version": SCHEMA_VERSION,
        "tenant_id": str(tenant_uuid),
        "aggregate_id": str(aggregate_uuid),
        "aggregate_type": aggregate_type,
        "actor_id": str(actor_uuid) if actor_uuid else None,
        "correlation_id": correlation,
        "causation_id": str(cause)[:128] if cause else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": supplied,
    }
    return OutboxEvent.objects.create(
        id=event_id,
        tenant_id=tenant_uuid,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_uuid,
        event_type=event_type,
        payload=envelope,
    )


__all__ = ["EVENT_TYPES", "SAFE_PAYLOAD_KEYS", "SCHEMA_VERSION", "publish_domain_event"]
