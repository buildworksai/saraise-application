"""Acknowledgement and recovery contracts for the outbox dispatcher."""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from src.core.async_jobs.dispatcher import BrokerAcknowledgement, OutboxDispatcher, dispatch_pending
from src.core.async_jobs.models import OutboxEvent, OutboxStatus
from src.core.async_jobs.services import enqueue


class RecordingBroker:
    def __init__(self, acknowledgement: object = True) -> None:
        self.acknowledgement = acknowledgement
        self.events: list[uuid.UUID] = []

    def submit(self, event: OutboxEvent) -> object:
        self.events.append(event.id)
        if isinstance(self.acknowledgement, Exception):
            raise self.acknowledgement
        return self.acknowledgement


def create_event() -> OutboxEvent:
    job = enqueue(uuid.uuid4(), uuid.uuid4(), "reports.generate", {"report": "sales"}, str(uuid.uuid4()))
    return OutboxEvent.objects.get(aggregate_id=job.id)


@pytest.mark.django_db
def test_dispatcher_marks_dispatched_only_after_acknowledgement() -> None:
    event = create_event()
    broker = RecordingBroker(BrokerAcknowledgement(accepted=True, message_id="broker-123"))

    result = dispatch_pending(broker, batch_size=10)

    assert result.claimed == result.dispatched == 1
    assert result.failed == 0
    event.refresh_from_db()
    assert event.status == OutboxStatus.DISPATCHED
    assert event.dispatched_at is not None
    assert event.broker_message_id == "broker-123"
    assert event.attempts == 1


@pytest.mark.django_db
def test_dispatcher_is_safe_to_rerun_after_acknowledgement() -> None:
    event = create_event()
    broker = RecordingBroker()

    first = dispatch_pending(broker)
    second = dispatch_pending(broker)

    assert first.dispatched == 1
    assert second == type(second)(claimed=0, dispatched=0, failed=0)
    assert broker.events == [event.id]


@pytest.mark.django_db
@pytest.mark.parametrize("acknowledgement", [False, BrokerAcknowledgement(accepted=False), MagicMock()])
def test_dispatcher_leaves_event_pending_without_explicit_acknowledgement(acknowledgement: object) -> None:
    event = create_event()
    broker = RecordingBroker(acknowledgement)

    result = OutboxDispatcher(broker).dispatch_pending(batch_size=10)  # type: ignore[arg-type]

    assert result.claimed == 1
    assert result.dispatched == 0
    assert result.failed == 1
    event.refresh_from_db()
    assert event.status == OutboxStatus.PENDING
    assert event.dispatched_at is None
    assert event.claim_token is None
    assert event.last_error
    assert broker.events == [event.id]


@pytest.mark.django_db
def test_dispatcher_releases_event_after_broker_exception() -> None:
    event = create_event()
    broker = RecordingBroker(ConnectionError("broker offline"))

    result = dispatch_pending(broker)

    assert result.failed == 1
    event.refresh_from_db()
    assert event.status == OutboxStatus.PENDING
    assert event.dispatched_at is None
    assert event.last_error == "ConnectionError: broker offline"


@pytest.mark.django_db
def test_dispatcher_recovers_expired_claim() -> None:
    event = create_event()
    original_token = uuid.uuid4()
    OutboxEvent.objects.filter(id=event.id).update(
        status=OutboxStatus.DISPATCHING,
        claim_token=original_token,
        claimed_until=timezone.now() - timedelta(seconds=1),
    )
    broker = RecordingBroker()

    result = dispatch_pending(broker)

    assert result.dispatched == 1
    event.refresh_from_db()
    assert event.status == OutboxStatus.DISPATCHED
    assert event.claim_token is None
    assert event.attempts == 1


@pytest.mark.django_db
def test_dispatcher_does_not_steal_live_claim() -> None:
    event = create_event()
    OutboxEvent.objects.filter(id=event.id).update(
        status=OutboxStatus.DISPATCHING,
        claim_token=uuid.uuid4(),
        claimed_until=timezone.now() + timedelta(minutes=1),
    )
    broker = RecordingBroker()

    result = dispatch_pending(broker)

    assert result.claimed == 0
    assert broker.events == []
    event.refresh_from_db()
    assert event.status == OutboxStatus.DISPATCHING


def test_dispatcher_validates_configuration() -> None:
    broker = RecordingBroker()
    with pytest.raises(ValueError, match="lease_seconds"):
        OutboxDispatcher(broker, lease_seconds=0)
    with pytest.raises(ValueError, match="batch_size"):
        OutboxDispatcher(broker).dispatch_pending(batch_size=0)
