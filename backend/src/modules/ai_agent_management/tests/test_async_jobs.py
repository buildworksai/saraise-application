"""Durability and at-least-once semantics for module command jobs."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import transaction
from django.utils import timezone

from src.core.async_jobs.dispatcher import BrokerAcknowledgement, OutboxDispatcher
from src.core.async_jobs.models import AsyncJob, JobStatus, OutboxEvent, OutboxStatus
from src.core.async_jobs.services import (
    InvalidJobTransition,
    enqueue,
    execute,
    recover_stale_jobs,
    register_handler,
    transition,
    unregister_handler,
)


@pytest.mark.django_db
def test_duplicate_enqueue_has_exactly_one_job_transition_and_outbox(tenant_id, actor_id):
    first = enqueue(tenant_id, actor_id, "ai_agent_management.test", {"value": 1}, "duplicate")
    second = enqueue(tenant_id, actor_id, "ai_agent_management.test", {"value": 2}, "duplicate")
    assert first.id == second.id
    assert first.payload == {"value": 1}
    assert first.transitions.count() == 1
    assert OutboxEvent.objects.filter(tenant_id=tenant_id, aggregate_id=first.id).count() == 1


@pytest.mark.django_db(transaction=True)
def test_job_and_outbox_roll_back_together(tenant_id, actor_id):
    with pytest.raises(RuntimeError, match="abort caller transaction"):
        with transaction.atomic():
            enqueue(tenant_id, actor_id, "ai_agent_management.test", {}, "rollback")
            raise RuntimeError("abort caller transaction")
    assert not AsyncJob.objects.filter(tenant_id=tenant_id, idempotency_key="rollback").exists()
    assert not OutboxEvent.objects.filter(tenant_id=tenant_id).exists()


@pytest.mark.django_db
def test_outbox_requires_explicit_positive_broker_acknowledgement(tenant_id, actor_id):
    class RejectingBroker:
        def submit(self, event):
            return BrokerAcknowledgement(accepted=False)

    class AcceptingBroker:
        def submit(self, event):
            return BrokerAcknowledgement(accepted=True, message_id=f"broker:{event.id}")

    job = enqueue(tenant_id, actor_id, "ai_agent_management.test", {}, "ack")
    rejected = OutboxDispatcher(RejectingBroker()).dispatch_pending(batch_size=1)
    assert rejected.failed == 1
    event = OutboxEvent.objects.get(aggregate_id=job.id)
    assert event.status == OutboxStatus.PENDING
    assert not event.dispatched_at

    accepted = OutboxDispatcher(AcceptingBroker()).dispatch_pending(batch_size=1)
    assert accepted.dispatched == 1
    event.refresh_from_db()
    assert event.status == OutboxStatus.DISPATCHED
    assert event.broker_message_id == f"broker:{event.id}"
    assert event.dispatched_at is not None


@pytest.mark.django_db
def test_redelivery_after_success_is_handler_idempotent(tenant_id, actor_id):
    calls = []

    def handler(job):
        calls.append(job.id)
        return {"handled": str(job.id)}

    command = "ai_agent_management.idempotent_handler"
    unregister_handler(command)
    register_handler(command, handler)
    try:
        job = enqueue(tenant_id, actor_id, command, {}, "handler-once")
        completed = execute(job.id, tenant_id)
        redelivered = execute(job.id, tenant_id)
    finally:
        unregister_handler(command)
    assert completed.status == JobStatus.SUCCEEDED
    assert redelivered.id == completed.id
    assert calls == [job.id]


@pytest.mark.django_db
def test_cancellation_is_terminal(tenant_id, actor_id):
    job = enqueue(tenant_id, actor_id, "ai_agent_management.cancel", {}, "cancel")
    cancelled = transition(job.id, tenant_id, JobStatus.CANCELLED, expected_status=JobStatus.QUEUED)
    assert cancelled.status == JobStatus.CANCELLED
    with pytest.raises(InvalidJobTransition):
        transition(job.id, tenant_id, JobStatus.RUNNING)


@pytest.mark.django_db
def test_stale_recovery_is_tenant_scoped_and_emits_retry_outbox(tenant_id, other_tenant_id, actor_id):
    own = enqueue(tenant_id, actor_id, "ai_agent_management.stale", {}, "own-stale")
    other = enqueue(other_tenant_id, actor_id, "ai_agent_management.stale", {}, "other-stale")
    transition(own.id, tenant_id, JobStatus.RUNNING)
    transition(other.id, other_tenant_id, JobStatus.RUNNING)
    stale = timezone.now() - timedelta(hours=1)
    AsyncJob.objects.filter(id__in=(own.id, other.id)).update(updated_at=stale)

    recovered = recover_stale_jobs(tenant_id, stale_before=timezone.now())
    assert [job.id for job in recovered] == [own.id]
    own.refresh_from_db()
    other.refresh_from_db()
    assert own.status == JobStatus.RETRYING
    assert other.status == JobStatus.RUNNING
    assert OutboxEvent.objects.filter(
        tenant_id=tenant_id,
        aggregate_id=own.id,
        event_type="async_job.retry_requested",
    ).exists()
