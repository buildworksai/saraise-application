from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.core.async_jobs.models import AsyncJob, JobStatus
from src.core.async_jobs.services import HandlerNotRegistered, JobExecutionError
from src.core.async_jobs.services import enqueue as enqueue_job
from src.core.async_jobs.services import execute, get_handler
from src.core.observability import get_task_context
from src.core.tenancy import MissingTenantContext
from src.modules.backup_disaster_recovery import services
from src.modules.backup_disaster_recovery.tasks import (
    BACKUP_REQUEST_COMMAND,
    RECOVERY_POINT_VERIFY_COMMAND,
    backup_request_worker,
    recovery_point_verify_worker,
)

pytestmark = pytest.mark.django_db


def test_worker_requires_tenant_context() -> None:
    with pytest.raises(MissingTenantContext):
        backup_request_worker(job_id=uuid4())  # type: ignore[call-arg]


def test_missing_handler_fails_explicitly() -> None:
    with pytest.raises(HandlerNotRegistered):
        get_handler(f"backup_disaster_recovery.missing.{uuid4()}")


def test_worker_propagates_correlation_actor_and_job_context(monkeypatch) -> None:
    tenant_id = uuid4()
    actor_id = uuid4()
    captured = {}

    class Facade:
        def execute_backup_request(self, received_tenant, received_job):
            captured["tenant_id"] = received_tenant
            captured["job_id"] = received_job
            captured["context"] = get_task_context()
            return SimpleNamespace(id=uuid4(), status="pending", backup_job_id=uuid4())

    monkeypatch.setattr(services, "BackupExecutionFacade", Facade)
    job = enqueue_job(tenant_id, actor_id, BACKUP_REQUEST_COMMAND, {}, f"request-{uuid4()}")

    result = backup_request_worker(tenant_id=tenant_id, job_id=job.id)

    assert result["status"] == "pending"
    assert captured["tenant_id"] == tenant_id
    assert captured["job_id"] == job.id
    assert captured["context"].tenant_id == tenant_id
    assert captured["context"].actor_id == str(actor_id)
    assert captured["context"].job_id == str(job.id)


def test_core_redelivery_does_not_repeat_terminal_side_effect(monkeypatch) -> None:
    tenant_id = uuid4()
    calls = []

    class Facade:
        def execute_backup_request(self, received_tenant, received_job):
            calls.append((received_tenant, received_job))
            return SimpleNamespace(id=uuid4(), status="pending", backup_job_id=uuid4())

    monkeypatch.setattr(services, "BackupExecutionFacade", Facade)
    job = enqueue_job(tenant_id, uuid4(), BACKUP_REQUEST_COMMAND, {}, f"request-{uuid4()}")
    first = execute(job.id, tenant_id)
    second = execute(job.id, tenant_id)

    assert first.status == JobStatus.SUCCEEDED
    assert second.status == JobStatus.SUCCEEDED
    assert calls == [(tenant_id, job.id)]


def test_handler_persists_failure_before_raising(monkeypatch) -> None:
    tenant_id = uuid4()
    calls = []

    class Facade:
        def execute_backup_request(self, received_tenant, received_job):
            calls.append((received_tenant, received_job))
            raise TimeoutError("provider timed out")

    monkeypatch.setattr(services, "BackupExecutionFacade", Facade)
    job = enqueue_job(tenant_id, uuid4(), BACKUP_REQUEST_COMMAND, {}, f"request-{uuid4()}")
    with pytest.raises(JobExecutionError):
        execute(job.id, tenant_id)
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert job.completed_at is not None
    redelivered = execute(job.id, tenant_id)
    assert redelivered.status == JobStatus.FAILED
    assert calls == [(tenant_id, job.id)]


def test_worker_rejects_missing_entity_identifier(monkeypatch) -> None:
    tenant_id = uuid4()

    class RecoveryService:
        def execute_verification(self, *args):
            raise AssertionError("service must not be called")

    monkeypatch.setattr(services, "RecoveryPointService", RecoveryService)
    job = enqueue_job(tenant_id, uuid4(), RECOVERY_POINT_VERIFY_COMMAND, {}, f"verify-{uuid4()}")
    with pytest.raises(ValueError, match="recovery_point_id"):
        recovery_point_verify_worker(tenant_id=tenant_id, job_id=job.id)


def test_worker_rejects_cross_tenant_job() -> None:
    tenant_id = uuid4()
    job = enqueue_job(tenant_id, uuid4(), BACKUP_REQUEST_COMMAND, {}, f"request-{uuid4()}")
    with pytest.raises(ValueError, match="does not exist for tenant"):
        backup_request_worker(tenant_id=uuid4(), job_id=job.id)
    assert AsyncJob.objects.get(id=job.id).status == JobStatus.QUEUED
