"""Durable worker, redelivery, cancellation, and outbox recovery tests."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from src.core.async_jobs.dispatcher import BrokerAcknowledgement, OutboxDispatcher
from src.core.async_jobs.models import AsyncJob, JobStatus, OutboxEvent, OutboxStatus
from src.core.async_jobs.services import execute, recover_stale_jobs, transition
from src.core.tenancy import get_current_tenant_id

from ..jobs import execute_instance_handler, expire_tasks_handler
from ..models import WorkflowStepExecution
from ..services import WorkflowDefinitionService, WorkflowExecutionService
from .test_services import action_payload

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db


def started_instance(tenant, actor, *, key="job-workflow", idempotency="job-start"):
    workflow = WorkflowDefinitionService.create_workflow(
        tenant.id, actor, action_payload(key=key)
    )
    workflow = WorkflowDefinitionService.publish_workflow(
        tenant.id, workflow.id, actor, f"publish:{key}"
    )
    return WorkflowExecutionService.start_workflow(
        tenant.id, workflow.id, actor, {}, idempotency
    )


def test_duplicate_delivery_executes_action_once(tenant_a, tenant_a_user) -> None:
    instance = started_instance(tenant_a, tenant_a_user)
    first = execute(instance.async_job_id, tenant_a.id)
    executions = list(WorkflowStepExecution.objects.for_tenant(tenant_a.id).filter(instance=instance))
    assert first.status == JobStatus.SUCCEEDED
    assert len(executions) == 1
    second = execute(instance.async_job_id, tenant_a.id)
    assert second.id == first.id
    assert second.attempts == first.attempts == 1
    assert WorkflowStepExecution.objects.for_tenant(tenant_a.id).filter(instance=instance).count() == 1


def test_cancellation_wins_before_worker_claim(tenant_a, tenant_a_user) -> None:
    instance = started_instance(
        tenant_a, tenant_a_user, key="cancel-race", idempotency="cancel-race-start"
    )
    WorkflowExecutionService.cancel_instance(
        tenant_a.id, instance.id, tenant_a_user, "cancel-before-claim"
    )
    job = execute(instance.async_job_id, tenant_a.id)
    instance.refresh_from_db()
    assert job.status == JobStatus.CANCELLED
    assert instance.state == "cancelled"
    assert WorkflowStepExecution.objects.for_tenant(tenant_a.id).filter(instance=instance).count() == 0


def test_failed_action_is_terminal_and_not_retried_without_evidence(
    tenant_a, tenant_a_user, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.core.api.results import OperationResult

    instance = started_instance(
        tenant_a, tenant_a_user, key="retry-exhaustion", idempotency="retry-exhaustion-start"
    )
    calls = 0

    def unavailable(invocation):
        nonlocal calls
        del invocation
        calls += 1
        return OperationResult.failed(code="PROVIDER_REJECTED", message="Provider rejected the action")

    monkeypatch.setattr("src.modules.workflow_automation.services.execute_registered_action", unavailable)
    job = execute(instance.async_job_id, tenant_a.id)
    instance.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    assert instance.state == "failed"
    assert instance.failure_code == "PROVIDER_REJECTED"
    assert calls == 1
    assert execute(job.id, tenant_a.id).attempts == 1
    assert calls == 1


def test_stale_job_is_recovered_with_retry_outbox(tenant_a, tenant_a_user) -> None:
    instance = started_instance(
        tenant_a, tenant_a_user, key="stale-job", idempotency="stale-job-start"
    )
    job = transition(
        instance.async_job_id,
        tenant_a.id,
        JobStatus.RUNNING,
        expected_status=JobStatus.QUEUED,
        reason="simulated worker claim",
    )
    AsyncJob.objects.for_tenant(tenant_a.id).filter(id=job.id).update(
        updated_at=timezone.now() - timedelta(minutes=10)
    )
    recovered = recover_stale_jobs(
        tenant_a.id, stale_before=timezone.now() - timedelta(minutes=1)
    )
    assert [item.id for item in recovered] == [job.id]
    assert recovered[0].status == JobStatus.RETRYING
    assert OutboxEvent.objects.for_tenant(tenant_a.id).filter(
        aggregate_id=job.id, event_type="async_job.retry_requested"
    ).exists()


def test_worker_installs_tenant_context(
    tenant_a, tenant_a_user, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = started_instance(
        tenant_a, tenant_a_user, key="tenant-context", idempotency="tenant-context-start"
    )
    job = AsyncJob.objects.for_tenant(tenant_a.id).get(id=instance.async_job_id)
    seen = None

    def execute_job(tenant_id, claimed_job):
        nonlocal seen
        seen = get_current_tenant_id()
        assert claimed_job.id == job.id
        return {"instance_id": str(instance.id), "state": "pending"}

    monkeypatch.setattr(WorkflowExecutionService, "execute_instance_job", execute_job)
    result = execute_instance_handler(job)
    assert result["state"] == "pending"
    assert seen == tenant_a.id
    assert get_current_tenant_id() is None


def test_expiry_worker_rejects_malformed_timestamp(tenant_a, tenant_a_user) -> None:
    instance = started_instance(
        tenant_a, tenant_a_user, key="expiry-command", idempotency="expiry-command-start"
    )
    job = AsyncJob.objects.for_tenant(tenant_a.id).get(id=instance.async_job_id)
    job.command = "workflow_automation.expire_tasks"
    job.payload = {"now": "not-a-date"}
    with pytest.raises(ValueError, match="invalid timestamp"):
        expire_tasks_handler(job)


def test_outbox_recovers_after_broker_rejection(tenant_a, tenant_a_user) -> None:
    instance = started_instance(
        tenant_a, tenant_a_user, key="outbox-recovery", idempotency="outbox-recovery-start"
    )
    event = OutboxEvent.objects.for_tenant(tenant_a.id).filter(
        aggregate_id=instance.async_job_id,
        event_type="async_job.enqueued",
    ).get()
    OutboxEvent.objects.exclude(id=event.id).update(
        status=OutboxStatus.DISPATCHED, dispatched_at=timezone.now()
    )

    class Broker:
        accepted = False

        def submit(self, submitted):
            assert submitted.id == event.id
            return BrokerAcknowledgement(self.accepted, "broker-message-1")

    broker = Broker()
    first = OutboxDispatcher(broker).dispatch_pending(batch_size=100)
    event.refresh_from_db()
    assert first.failed >= 1
    assert event.status == OutboxStatus.PENDING
    assert event.last_error

    broker.accepted = True
    second = OutboxDispatcher(broker).dispatch_pending(batch_size=100)
    event.refresh_from_db()
    assert second.dispatched >= 1
    assert event.status == OutboxStatus.DISPATCHED
    assert event.broker_message_id == "broker-message-1"
