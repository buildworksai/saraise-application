"""Durable MDM handler registration, execution, failure, and isolation tests."""

from __future__ import annotations

import uuid

import pytest

from src.core.async_jobs.models import JobStatus, JobTransition, OutboxEvent
from src.core.async_jobs.services import (
    JobExecutionError,
    enqueue,
    execute,
    get_handler,
    transition,
)
from src.core.observability import get_task_context
from src.core.tenancy import get_current_tenant_id
from src.modules.master_data_management import jobs
from src.modules.master_data_management.models import MatchCandidate
from src.modules.master_data_management.services import (
    DEDUPLICATION_SCAN_COMMAND,
    QUALITY_SCAN_COMMAND,
    DataQualityService,
    MatchingService,
)

from .factories import actor_id, make_entity, make_entity_type, make_matching_rule

pytestmark = pytest.mark.django_db


def test_handlers_are_explicitly_registered_without_silent_replacement() -> None:
    jobs.register_handlers()
    assert set(jobs.REGISTERED_COMMANDS) == {
        QUALITY_SCAN_COMMAND,
        DEDUPLICATION_SCAN_COMMAND,
    }
    assert get_handler(QUALITY_SCAN_COMMAND) is jobs.quality_scan_handler
    assert get_handler(DEDUPLICATION_SCAN_COMMAND) is jobs.deduplication_scan_handler


def test_quality_job_runs_in_persisted_tenant_and_uses_job_idempotency() -> None:
    tenant = uuid.uuid4()
    actor = actor_id()
    entity_type = make_entity_type(tenant)
    make_entity(tenant, entity_type=entity_type)
    job = DataQualityService.enqueue_quality_scan(
        tenant,
        actor,
        entity_type_id=entity_type.id,
        idempotency_key="quality-job",
    )

    completed = execute(job.id, tenant)

    assert completed.status == JobStatus.SUCCEEDED
    assert completed.result == {
        "job_id": str(job.id),
        "entity_type_id": str(entity_type.id),
        "entity_count": 1,
        "evaluated_count": 0,
        "not_evaluated_count": 1,
        "issue_count": 0,
    }
    assert completed.attempts == 1
    assert list(
        JobTransition.objects.for_tenant(tenant)
        .filter(job=job)
        .values_list("to_status", flat=True)
    ) == [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.SUCCEEDED]
    # At-least-once redelivery returns durable evidence without evaluating twice.
    replay = execute(job.id, tenant)
    assert replay.id == completed.id and replay.attempts == 1


def test_deduplication_job_blocks_compares_creates_once_and_reuses_on_redelivery() -> None:
    tenant = uuid.uuid4()
    actor = actor_id()
    entity_type = make_entity_type(tenant)
    first = make_entity(tenant, entity_type=entity_type, data={"email": "SAME@example.test", "city": "Pune"})
    second = make_entity(tenant, entity_type=entity_type, data={"email": "same@example.test", "city": "Pune"})
    make_entity(tenant, entity_type=entity_type, data={"email": "other@example.test", "city": "Mumbai"})
    rule = make_matching_rule(
        tenant,
        entity_type=entity_type,
        algorithm="normalized",
        field_weights={"email": "1.0000"},
        blocking_fields=["city"],
        review_threshold="0.7000",
        auto_confirm_threshold="0.9500",
    )
    job = MatchingService.enqueue_deduplication_scan(
        tenant,
        actor,
        entity_type_id=entity_type.id,
        rule_ids=[rule.id],
        idempotency_key="dedup-job",
    )

    completed = execute(job.id, tenant)

    assert completed.status == JobStatus.SUCCEEDED
    assert completed.result["compared_pair_count"] == 1
    assert completed.result["created_candidate_count"] == 1
    candidate = MatchCandidate.objects.for_tenant(tenant).get()
    assert {candidate.left_entity_id, candidate.right_entity_id} == {first.id, second.id}
    assert candidate.status == "confirmed"
    assert len(candidate.transition_history) == 1
    assert (
        candidate.transition_history[0]["metadata"]["correlation_id"]
        == job.correlation_id
    )
    assert OutboxEvent.objects.for_tenant(tenant).filter(
        event_type="mdm.match_candidate.created",
        aggregate_id=candidate.id,
    ).count() == 1
    replay = execute(job.id, tenant)
    assert replay.attempts == 1
    assert MatchCandidate.objects.for_tenant(tenant).count() == 1


def test_handler_binds_correlation_tenant_actor_causation_and_job_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = uuid.uuid4()
    actor = actor_id()
    entity_type = make_entity_type(tenant)
    job = enqueue(
        tenant,
        actor,
        QUALITY_SCAN_COMMAND,
        {"entity_type_id": str(entity_type.id)},
        "context-job",
    )
    observed: dict[str, object] = {}

    def execute_scan(
        tenant_id: uuid.UUID,
        actor_id_value: uuid.UUID,
        *,
        entity_type_id: uuid.UUID,
        job_id: uuid.UUID,
    ) -> dict[str, object]:
        observed.update(
            {
                "tenant": get_current_tenant_id(),
                "actor": actor_id_value,
                "type": entity_type_id,
                "job": job_id,
                "task": get_task_context(),
            }
        )
        return {"job_id": str(job_id)}

    monkeypatch.setattr(DataQualityService, "execute_quality_scan", execute_scan)
    result = jobs.quality_scan_handler(job)
    assert result == {"job_id": str(job.id)}
    assert observed["tenant"] == tenant
    assert observed["actor"] == actor
    assert observed["type"] == entity_type.id
    assert observed["job"] == job.id
    task = observed["task"]
    assert task.tenant_id == tenant and task.actor_id == str(actor)  # type: ignore[union-attr]
    assert task.job_id == str(job.id) and task.causation_id == str(job.id)  # type: ignore[union-attr]
    assert get_current_tenant_id() is None and get_task_context() is None


def test_malformed_persisted_payload_is_durably_failed_and_never_reports_success() -> None:
    tenant = uuid.uuid4()
    job = enqueue(
        tenant,
        actor_id(),
        QUALITY_SCAN_COMMAND,
        {"entity_type_id": "not-a-uuid"},
        "malformed-quality-job",
    )
    with pytest.raises(JobExecutionError):
        execute(job.id, tenant)
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert job.completed_at is not None
    assert job.result is None
    assert "entity_type_id must be a valid UUID" in job.error_message
    assert list(job.transitions.values_list("to_status", flat=True)) == [
        JobStatus.QUEUED,
        JobStatus.RUNNING,
        JobStatus.FAILED,
    ]
    # Redelivery of a terminal failure is inert and truthful.
    assert execute(job.id, tenant).status == JobStatus.FAILED


def test_foreign_entity_type_in_persisted_quality_job_fails_without_querying_tenant_b() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    foreign_type = make_entity_type(tenant_b)
    foreign_entity = make_entity(tenant_b, entity_type=foreign_type)
    before = foreign_entity.updated_at
    job = enqueue(
        tenant_a,
        actor_id(),
        QUALITY_SCAN_COMMAND,
        {"entity_type_id": str(foreign_type.id)},
        "cross-tenant-quality-job",
    )
    with pytest.raises(JobExecutionError):
        execute(job.id, tenant_a)
    job.refresh_from_db()
    foreign_entity.refresh_from_db()
    assert job.status == JobStatus.FAILED and job.result is None
    assert foreign_entity.updated_at == before


def test_timeout_retry_and_cancellation_states_are_persisted_truthfully() -> None:
    tenant = uuid.uuid4()
    actor = actor_id()
    cancelled = enqueue(
        tenant,
        actor,
        QUALITY_SCAN_COMMAND,
        {"entity_type_id": str(uuid.uuid4())},
        "cancelled-job",
    )
    transition(
        cancelled.id,
        tenant,
        JobStatus.CANCELLED,
        expected_status=JobStatus.QUEUED,
        error_message="Cancelled by operator",
        reason="Operator cancellation",
    )
    terminal = execute(cancelled.id, tenant)
    assert terminal.status == JobStatus.CANCELLED and terminal.attempts == 0

    timed_out = enqueue(
        tenant,
        actor,
        QUALITY_SCAN_COMMAND,
        {"entity_type_id": str(uuid.uuid4())},
        "timed-out-job",
    )
    transition(timed_out.id, tenant, JobStatus.RUNNING, expected_status=JobStatus.QUEUED)
    transition(
        timed_out.id,
        tenant,
        JobStatus.TIMED_OUT,
        expected_status=JobStatus.RUNNING,
        error_message="Execution deadline exceeded",
        reason="Worker timeout",
    )
    assert execute(timed_out.id, tenant).status == JobStatus.TIMED_OUT

    retry = enqueue(
        tenant,
        actor,
        QUALITY_SCAN_COMMAND,
        {"entity_type_id": str(uuid.uuid4())},
        "retry-job",
    )
    transition(retry.id, tenant, JobStatus.RUNNING, expected_status=JobStatus.QUEUED)
    transition(
        retry.id,
        tenant,
        JobStatus.RETRYING,
        expected_status=JobStatus.RUNNING,
        error_message="Transient storage failure",
        reason="Bounded retry",
    )
    retry.refresh_from_db()
    assert retry.status == JobStatus.RETRYING and retry.error_message == "Transient storage failure"
    assert OutboxEvent.objects.for_tenant(tenant).filter(
        aggregate_id=retry.id,
        event_type="async_job.retry_requested",
    ).exists()
