"""Service-level contracts for durable asynchronous jobs."""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import transaction
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, ImmutableTransitionError, JobStatus, JobTransition, OutboxEvent
from src.core.async_jobs.services import (
    ConcurrentJobTransition,
    HandlerAlreadyRegistered,
    HandlerNotRegistered,
    InvalidJobTransition,
    JobAlreadyRunning,
    JobExecutionError,
    enqueue,
    execute,
    get_handler,
    recover_stale_jobs,
    register_handler,
    transition,
    unregister_handler,
)


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def actor_id() -> uuid.UUID:
    return uuid.uuid4()


def enqueue_job(tenant_id: uuid.UUID, actor_id: uuid.UUID, *, key: str = "invoice-42") -> AsyncJob:
    return enqueue(
        tenant_id=tenant_id,
        actor_id=actor_id,
        command="invoices.recalculate",
        payload={"invoice_id": "42"},
        idempotency_key=key,
    )


@pytest.mark.django_db
def test_enqueue_atomically_creates_job_transition_and_outbox(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    job = enqueue_job(tenant_id, actor_id)

    assert AsyncJob.objects.get(id=job.id) == job
    assert job.tenant_id == tenant_id
    assert job.status == JobStatus.QUEUED
    assert job.attempts == 0
    assert job.correlation_id
    assert JobTransition.objects.filter(job=job).values_list("from_status", "to_status").get() == (
        "",
        JobStatus.QUEUED,
    )
    event = OutboxEvent.objects.get(aggregate_id=job.id)
    assert event.tenant_id == tenant_id
    assert event.payload["job_id"] == str(job.id)
    assert event.payload["tenant_id"] == str(tenant_id)


@pytest.mark.django_db(transaction=True)
def test_enqueue_rolls_back_both_rows_when_outbox_creation_fails(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    with patch.object(OutboxEvent.objects, "create", side_effect=RuntimeError("storage unavailable")):
        with pytest.raises(RuntimeError, match="storage unavailable"):
            enqueue_job(tenant_id, actor_id)

    assert AsyncJob.objects.count() == 0
    assert JobTransition.objects.count() == 0
    assert OutboxEvent.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_enqueue_participates_in_callers_transaction(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    class ForceRollback(Exception):
        pass

    with pytest.raises(ForceRollback):
        with transaction.atomic():
            enqueue_job(tenant_id, actor_id)
            raise ForceRollback

    assert AsyncJob.objects.count() == 0
    assert JobTransition.objects.count() == 0
    assert OutboxEvent.objects.count() == 0


@pytest.mark.django_db
def test_duplicate_idempotency_key_returns_same_job_without_duplicate_outbox(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    first = enqueue_job(tenant_id, actor_id)
    second = enqueue(
        tenant_id,
        actor_id,
        "different.command",
        {"different": True},
        "invoice-42",
    )

    assert second.id == first.id
    assert second.command == "invoices.recalculate"
    assert AsyncJob.objects.count() == 1
    assert JobTransition.objects.count() == 1
    assert OutboxEvent.objects.count() == 1


@pytest.mark.django_db
def test_idempotency_key_is_scoped_per_tenant(actor_id: uuid.UUID) -> None:
    first = enqueue_job(uuid.uuid4(), actor_id, key="shared-key")
    second = enqueue_job(uuid.uuid4(), actor_id, key="shared-key")

    assert first.id != second.id
    assert AsyncJob.objects.count() == 2
    assert OutboxEvent.objects.count() == 2


@pytest.mark.django_db
def test_enqueue_validates_inputs(tenant_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    with pytest.raises(ValueError, match="command"):
        enqueue(tenant_id, actor_id, " ", {}, "key")
    with pytest.raises(ValueError, match="idempotency_key"):
        enqueue(tenant_id, actor_id, "command", {}, " ")
    with pytest.raises(ValueError, match="tenant_id"):
        enqueue("not-a-uuid", actor_id, "command", {}, "key")
    with pytest.raises(TypeError, match="payload"):
        enqueue(tenant_id, actor_id, "command", [], "key")  # type: ignore[arg-type]


@pytest.mark.django_db
def test_illegal_transition_is_rejected_without_audit_mutation(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    job = enqueue_job(tenant_id, actor_id)

    with pytest.raises(InvalidJobTransition, match="Cannot transition"):
        transition(job.id, tenant_id, JobStatus.SUCCEEDED)

    job.refresh_from_db()
    assert job.status == JobStatus.QUEUED
    assert job.transitions.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "terminal_status",
    [JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.TIMED_OUT],
)
def test_terminal_states_are_immutable(
    terminal_status: str,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    job = enqueue_job(tenant_id, actor_id, key=f"terminal-{terminal_status}")
    if terminal_status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.TIMED_OUT}:
        transition(job.id, tenant_id, JobStatus.RUNNING)
    transition(job.id, tenant_id, terminal_status)

    with pytest.raises(InvalidJobTransition, match="immutable"):
        transition(job.id, tenant_id, JobStatus.RUNNING)


@pytest.mark.django_db
def test_expected_status_prevents_lost_transition(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    job = enqueue_job(tenant_id, actor_id)

    with pytest.raises(ConcurrentJobTransition, match="Expected"):
        transition(job.id, tenant_id, JobStatus.RUNNING, expected_status=JobStatus.RETRYING)


@pytest.mark.django_db
def test_transition_history_rejects_instance_and_bulk_mutation(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    job = enqueue_job(tenant_id, actor_id)
    history = job.transitions.get()
    history.reason = "rewritten"

    with pytest.raises(ImmutableTransitionError, match="append-only"):
        history.save()
    with pytest.raises(ImmutableTransitionError, match="append-only"):
        history.delete()
    with pytest.raises(ImmutableTransitionError, match="append-only"):
        JobTransition.objects.filter(id=history.id).update(reason="rewritten")
    with pytest.raises(ImmutableTransitionError, match="append-only"):
        JobTransition.objects.filter(id=history.id).delete()


def test_handler_registry_requires_explicit_replacement() -> None:
    command = f"test.{uuid.uuid4()}"

    @register_handler(command)
    def first(job: AsyncJob) -> dict[str, bool]:
        return {"first": True}

    assert get_handler(command) is first
    with pytest.raises(HandlerAlreadyRegistered):
        register_handler(command, lambda job: {"second": True})

    replacement = lambda job: {"replacement": True}  # noqa: E731
    register_handler(command, replacement, replace=True)
    assert unregister_handler(command) is replacement
    with pytest.raises(HandlerNotRegistered):
        get_handler(command)


@pytest.mark.django_db
def test_execute_runs_registered_handler_and_redelivery_is_idempotent(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    command = f"test.{uuid.uuid4()}"
    calls: list[uuid.UUID] = []

    @register_handler(command)
    def handler(job: AsyncJob) -> dict[str, str]:
        calls.append(job.id)
        assert job.status == JobStatus.RUNNING
        return {"processed": str(job.id)}

    try:
        job = enqueue(tenant_id, actor_id, command, {"value": 7}, "execution")
        completed = execute(job.id, tenant_id)
        redelivered = execute(job.id, tenant_id)
    finally:
        unregister_handler(command)

    assert completed.status == JobStatus.SUCCEEDED
    assert completed.result == {"processed": str(job.id)}
    assert redelivered.id == completed.id
    assert calls == [job.id]
    assert completed.transitions.count() == 3


@pytest.mark.django_db
def test_execute_fails_explicitly_without_handler(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    job = enqueue_job(tenant_id, actor_id)

    with pytest.raises(HandlerNotRegistered):
        execute(job.id, tenant_id)

    job.refresh_from_db()
    assert job.status == JobStatus.QUEUED


@pytest.mark.django_db
def test_execute_records_handler_failure(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    command = f"test.{uuid.uuid4()}"

    def handler(job: AsyncJob) -> None:
        raise OSError("downstream offline")

    register_handler(command, handler)
    try:
        job = enqueue(tenant_id, actor_id, command, {}, "failure")
        with pytest.raises(JobExecutionError) as error:
            execute(job.id, tenant_id)
    finally:
        unregister_handler(command)

    assert isinstance(error.value.__cause__, OSError)
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert job.error_message == "downstream offline"
    assert job.completed_at is not None


@pytest.mark.django_db
def test_execute_rejects_overlapping_delivery(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    job = enqueue_job(tenant_id, actor_id)
    transition(job.id, tenant_id, JobStatus.RUNNING)

    with pytest.raises(JobAlreadyRunning):
        execute(job.id, tenant_id)


@pytest.mark.django_db
def test_recover_stale_jobs_is_tenant_scoped(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    stale = enqueue_job(tenant_id, actor_id, key="stale")
    fresh = enqueue_job(tenant_id, actor_id, key="fresh")
    other_tenant = enqueue_job(uuid.uuid4(), actor_id, key="other")
    for job in (stale, fresh, other_tenant):
        transition(job.id, job.tenant_id, JobStatus.RUNNING)
    AsyncJob.objects.filter(id__in=[stale.id, other_tenant.id]).update(updated_at=timezone.now() - timedelta(hours=2))

    recovered = recover_stale_jobs(tenant_id, stale_before=timezone.now() - timedelta(hours=1))

    assert [job.id for job in recovered] == [stale.id]
    stale.refresh_from_db()
    fresh.refresh_from_db()
    other_tenant.refresh_from_db()
    assert stale.status == JobStatus.RETRYING
    assert fresh.status == JobStatus.RUNNING
    assert other_tenant.status == JobStatus.RUNNING
    retry_event = OutboxEvent.objects.get(aggregate_id=stale.id, event_type="async_job.retry_requested")
    assert retry_event.tenant_id == tenant_id


@pytest.mark.django_db(transaction=True)
def test_retry_transition_rolls_back_if_retry_outbox_write_fails(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    job = enqueue_job(tenant_id, actor_id)
    transition(job.id, tenant_id, JobStatus.RUNNING)
    transition_count = JobTransition.objects.filter(job=job).count()

    with patch.object(OutboxEvent.objects, "create", side_effect=RuntimeError("outbox unavailable")):
        with pytest.raises(RuntimeError, match="outbox unavailable"):
            transition(job.id, tenant_id, JobStatus.RETRYING)

    job.refresh_from_db()
    assert job.status == JobStatus.RUNNING
    assert JobTransition.objects.filter(job=job).count() == transition_count
    assert not OutboxEvent.objects.filter(aggregate_id=job.id, event_type="async_job.retry_requested").exists()
