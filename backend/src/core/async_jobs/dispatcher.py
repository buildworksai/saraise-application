"""Lease-based transactional outbox dispatcher.

Publication is intentionally outside the database transaction. An event is
marked dispatched only after an explicit broker acknowledgement. A worker crash
after acknowledgement but before the status update can publish the event again;
that is the documented at-least-once contract and consumers use the stable
event/job identifiers for idempotency.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from .models import OutboxEvent, OutboxStatus

logger = logging.getLogger("saraise.async_jobs.dispatcher")


@dataclass(frozen=True)
class BrokerAcknowledgement:
    """An explicit broker acknowledgement and optional provider message ID."""

    accepted: bool
    message_id: str = ""


class Broker(Protocol):
    """Minimal extension surface for Celery, Redis, Kafka, or paid adapters."""

    def submit(self, event: OutboxEvent) -> bool | BrokerAcknowledgement:
        """Submit one durable event and return an explicit acknowledgement."""
        ...


@dataclass(frozen=True)
class DispatchResult:
    """Measured outcome of one dispatcher pass."""

    claimed: int
    dispatched: int
    failed: int


class OutboxDispatcher:
    """Claim, publish, acknowledge, and recover transactional outbox events."""

    def __init__(self, broker: Broker, *, lease_seconds: int = 60) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.broker = broker
        self.lease_seconds = lease_seconds

    def _claim_next(self, excluded_ids: set[uuid.UUID]) -> OutboxEvent | None:
        now = timezone.now()
        claim_token = uuid.uuid4()
        claimable = Q(status=OutboxStatus.PENDING, available_at__lte=now) | Q(
            status=OutboxStatus.DISPATCHING,
            claimed_until__lte=now,
        )

        with transaction.atomic():
            queryset = OutboxEvent.objects.filter(claimable).exclude(id__in=excluded_ids).order_by("created_at", "id")
            if connection.features.has_select_for_update_skip_locked:
                queryset = queryset.select_for_update(skip_locked=True)
            else:
                queryset = queryset.select_for_update()
            event = queryset.first()
            if event is None:
                return None
            event.status = OutboxStatus.DISPATCHING
            event.claim_token = claim_token
            event.claimed_until = now + timedelta(seconds=self.lease_seconds)
            event.attempts += 1
            event.last_error = ""
            event.save(
                update_fields=(
                    "status",
                    "claim_token",
                    "claimed_until",
                    "attempts",
                    "last_error",
                    "updated_at",
                )
            )
            return event

    @staticmethod
    def _accepted(acknowledgement: bool | BrokerAcknowledgement) -> tuple[bool, str]:
        if acknowledgement is True:
            return True, ""
        if acknowledgement is False:
            return False, "Broker did not acknowledge the event"
        if isinstance(acknowledgement, BrokerAcknowledgement):
            if acknowledgement.accepted:
                return True, acknowledgement.message_id
            return False, "Broker rejected the event"
        return False, "Broker returned an invalid acknowledgement"

    @staticmethod
    def _mark_dispatched(event: OutboxEvent, message_id: str) -> bool:
        updated = OutboxEvent.objects.filter(
            id=event.id,
            tenant_id=event.tenant_id,
            status=OutboxStatus.DISPATCHING,
            claim_token=event.claim_token,
        ).update(
            status=OutboxStatus.DISPATCHED,
            dispatched_at=timezone.now(),
            broker_message_id=message_id,
            claim_token=None,
            claimed_until=None,
            last_error="",
            updated_at=timezone.now(),
        )
        return updated == 1

    @staticmethod
    def _release(event: OutboxEvent, error: str) -> bool:
        updated = OutboxEvent.objects.filter(
            id=event.id,
            tenant_id=event.tenant_id,
            status=OutboxStatus.DISPATCHING,
            claim_token=event.claim_token,
        ).update(
            status=OutboxStatus.PENDING,
            claim_token=None,
            claimed_until=None,
            last_error=error,
            updated_at=timezone.now(),
        )
        return updated == 1

    def dispatch_pending(self, *, batch_size: int = 100) -> DispatchResult:
        """Dispatch up to ``batch_size`` currently claimable events."""

        if batch_size <= 0:
            raise ValueError("batch_size must be positive")

        claimed = dispatched = failed = 0
        attempted_ids: set[uuid.UUID] = set()
        for _ in range(batch_size):
            event = self._claim_next(attempted_ids)
            if event is None:
                break
            attempted_ids.add(event.id)
            claimed += 1
            try:
                acknowledgement = self.broker.submit(event)
            except Exception as exc:
                self._release(event, f"{type(exc).__name__}: {exc}")
                failed += 1
                logger.exception(
                    "Outbox broker submission failed",
                    extra={
                        "event_id": str(event.id),
                        "tenant_id": str(event.tenant_id),
                        "correlation_id": event.payload.get("correlation_id", ""),
                    },
                )
                continue

            accepted, detail = self._accepted(acknowledgement)
            if accepted and self._mark_dispatched(event, detail):
                dispatched += 1
            else:
                self._release(event, detail or "Event claim was lost before acknowledgement")
                failed += 1

        return DispatchResult(claimed=claimed, dispatched=dispatched, failed=failed)


def dispatch_pending(
    broker: Broker,
    *,
    batch_size: int = 100,
    lease_seconds: int = 60,
) -> DispatchResult:
    """Convenience entry point for schedulers and management commands."""

    return OutboxDispatcher(broker, lease_seconds=lease_seconds).dispatch_pending(batch_size=batch_size)
