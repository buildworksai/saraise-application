from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, JobStatus, JobTransition, OutboxEvent
from src.core.async_jobs.services import enqueue, execute, recover_stale_jobs, transition
from src.core.tenancy import get_current_tenant_id
from src.modules.compliance_management.models import ComplianceFramework, FrameworkSourceKind
from src.modules.compliance_management.tasks import (
    COLLECT_EVIDENCE_COMMAND,
    EXPORT_WORKSPACE_COMMAND,
    IMPORT_FRAMEWORK_COMMAND,
    IMPORT_REQUIREMENTS_COMMAND,
    ComplianceJobPayloadError,
    _actor,
    _export_workspace,
    _json_value,
    _mapping,
    _result_identity,
    _rows,
    _uuid,
    collect_evidence_handler,
    export_workspace_worker,
    import_framework_handler,
    import_requirements_handler,
)


pytestmark = pytest.mark.django_db(transaction=True)


def enqueue_export(tenant_id: uuid.UUID, key: str = "export-1") -> AsyncJob:
    return enqueue(tenant_id, uuid.uuid4(), EXPORT_WORKSPACE_COMMAND, {"options": {}}, key)


def test_enqueue_is_durable_with_outbox_and_idempotent():
    tenant_id = uuid.uuid4()
    first = enqueue_export(tenant_id)
    duplicate = enqueue_export(tenant_id)
    assert duplicate.id == first.id
    assert JobTransition.objects.filter(job=first, to_status=JobStatus.QUEUED).count() == 1
    assert OutboxEvent.objects.filter(aggregate_id=first.id, event_type="async_job.enqueued").count() == 1


def test_export_job_queries_tenant_data_and_persists_real_result():
    tenant_id = uuid.uuid4()
    framework = ComplianceFramework.objects.create(
        tenant_id=tenant_id,
        code="ISO27001",
        name="ISO/IEC 27001",
        version="2022",
        category="security",
        source_kind=FrameworkSourceKind.CUSTOM,
    )
    job = enqueue_export(tenant_id)
    completed = execute(job.id, tenant_id)
    assert completed.status == JobStatus.SUCCEEDED
    assert completed.result["artifact"]["frameworks"][0]["id"] == str(framework.id)
    assert len(completed.result["content_sha256"]) == 64
    # At-least-once redelivery returns the durable outcome without rerunning.
    assert execute(job.id, tenant_id).result == completed.result


def test_export_is_tenant_isolated():
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    ComplianceFramework.objects.create(
        tenant_id=tenant_b,
        code="PRIVATE",
        name="Foreign tenant",
        version="1",
        category="security",
        source_kind=FrameworkSourceKind.CUSTOM,
    )
    completed = execute(enqueue_export(tenant_a).id, tenant_a)
    assert completed.result["artifact"]["frameworks"] == []


def test_invalid_payload_fails_durably_without_success():
    tenant_id = uuid.uuid4()
    job = enqueue(
        tenant_id,
        uuid.uuid4(),
        IMPORT_FRAMEWORK_COMMAND,
        {"package": "not-an-object"},
        "bad-import",
    )
    with pytest.raises(Exception):
        execute(job.id, tenant_id)
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert job.completed_at is not None


def test_cancellation_and_timeout_are_explicit_terminal_outcomes():
    tenant_id = uuid.uuid4()
    cancelled = enqueue_export(tenant_id, "cancel")
    transition(cancelled.id, tenant_id, JobStatus.CANCELLED, expected_status=JobStatus.QUEUED)
    timed_out = enqueue_export(tenant_id, "timeout")
    transition(timed_out.id, tenant_id, JobStatus.RUNNING, expected_status=JobStatus.QUEUED)
    transition(timed_out.id, tenant_id, JobStatus.TIMED_OUT, expected_status=JobStatus.RUNNING)
    assert AsyncJob.objects.get(id=cancelled.id).status == JobStatus.CANCELLED
    assert AsyncJob.objects.get(id=timed_out.id).status == JobStatus.TIMED_OUT


def test_stale_running_job_is_recovered_for_retry():
    tenant_id = uuid.uuid4()
    job = enqueue_export(tenant_id, "stale")
    transition(job.id, tenant_id, JobStatus.RUNNING, expected_status=JobStatus.QUEUED)
    AsyncJob.objects.filter(id=job.id).update(updated_at=timezone.now() - timedelta(hours=1))
    recovered = recover_stale_jobs(tenant_id, stale_before=timezone.now() - timedelta(minutes=5))
    assert [item.id for item in recovered] == [job.id]
    assert recovered[0].status == JobStatus.RETRYING
    assert OutboxEvent.objects.filter(aggregate_id=job.id, event_type="async_job.retry_requested").exists()


def test_worker_installs_tenant_context(monkeypatch):
    tenant_id = uuid.uuid4()

    def capture(bound_tenant, job_id, options):
        assert bound_tenant == tenant_id
        assert get_current_tenant_id() == tenant_id
        return {"artifact": {"schema": "test"}, "content_sha256": "a" * 64, "media_type": "application/json"}

    monkeypatch.setattr("src.modules.compliance_management.tasks._export_workspace", capture)
    result = export_workspace_worker(
        tenant_id=tenant_id,
        job_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        correlation_id=str(uuid.uuid4()),
        options={},
    )
    assert result["content_sha256"] == "a" * 64


def test_payload_primitives_validate_types_and_serialize_portably():
    identifier = uuid.uuid4()
    assert _uuid(identifier, "id") == identifier
    assert _mapping({"answer": 42}, "payload") == {"answer": 42}
    assert _rows([{"code": "A"}]) == [{"code": "A"}]
    assert _json_value({"id": identifier, "at": timezone.now(), "days": [identifier]})["id"] == str(identifier)

    for value in (None, "not-a-uuid"):
        with pytest.raises(ComplianceJobPayloadError, match="valid UUID"):
            _uuid(value, "id")
    with pytest.raises(ComplianceJobPayloadError, match="must be an object"):
        _mapping([], "payload")
    with pytest.raises(ComplianceJobPayloadError, match="must be an array"):
        _rows("not rows")
    with pytest.raises(ComplianceJobPayloadError, match=r"rows\[0\]"):
        _rows(["not an object"])


def test_actor_and_result_identity_fail_closed():
    with pytest.raises(ComplianceJobPayloadError, match="actor no longer exists"):
        _actor(uuid.uuid4())
    with pytest.raises(RuntimeError, match="invalid persisted result"):
        _result_identity(object())
    assert _result_identity(SimpleNamespace(id=uuid.uuid4(), status="active"))["status"] == "active"


def test_workspace_export_options_are_validated_and_activity_can_be_excluded():
    tenant_id = uuid.uuid4()
    with pytest.raises(ComplianceJobPayloadError, match="unsupported fields"):
        _export_workspace(tenant_id, uuid.uuid4(), {"unknown": True})
    with pytest.raises(ComplianceJobPayloadError, match="must be a boolean"):
        _export_workspace(tenant_id, uuid.uuid4(), {"include_activity": "yes"})
    result = _export_workspace(tenant_id, uuid.uuid4(), {"include_activity": False})
    assert "activity" not in result["artifact"]


def test_handlers_reject_wrong_commands_and_malformed_payloads():
    tenant_id = uuid.uuid4()
    wrong = enqueue_export(tenant_id, "wrong-handler")
    with pytest.raises(ComplianceJobPayloadError, match=IMPORT_FRAMEWORK_COMMAND):
        import_framework_handler(wrong)

    requirements = enqueue(
        tenant_id,
        uuid.uuid4(),
        IMPORT_REQUIREMENTS_COMMAND,
        {"framework_id": "invalid", "rows": []},
        "bad-requirements",
    )
    with pytest.raises(ComplianceJobPayloadError, match="framework_id"):
        import_requirements_handler(requirements)

    evidence = enqueue(
        tenant_id,
        uuid.uuid4(),
        COLLECT_EVIDENCE_COMMAND,
        {"extension_id": "", "request": {}},
        "bad-evidence",
    )
    with pytest.raises(ComplianceJobPayloadError, match="nonblank"):
        collect_evidence_handler(evidence)
