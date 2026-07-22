"""Durable async-job handlers with mandatory tenant worker context."""

from __future__ import annotations

import threading
import uuid
from typing import Any

from django.utils import timezone

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import register_handler
from src.core.tenancy import tenant_context_worker

from .services import BackupArtifactService, BackupRecoveryService, BackupScheduleService, _adapter_for

_registration_lock = threading.Lock()
_registered = False


@tenant_context_worker
def capture_backup(*, tenant_id: uuid.UUID, job_id: uuid.UUID) -> dict[str, object]:
    job = BackupRecoveryService().execute_backup(tenant_id, job_id)
    return {"job_id": str(job.id), "status": job.status}


@tenant_context_worker
def verify_artifact(*, tenant_id: uuid.UUID, verification_id: uuid.UUID) -> dict[str, object]:
    verification = BackupArtifactService().execute_verification(tenant_id, verification_id)
    return {"verification_id": str(verification.id), "status": verification.status}


@tenant_context_worker
def purge_artifact(*, tenant_id: uuid.UUID, archive_id: uuid.UUID, idempotency_key: str) -> dict[str, object]:
    service = BackupArtifactService()
    archive = service.get(tenant_id, archive_id)
    descriptor = BackupRecoveryService().describe_completed_artifact(tenant_id, archive.backup_job_id)
    try:
        receipt = _adapter_for(archive.backup_job.storage_target).purge(descriptor, idempotency_key=idempotency_key)
    except Exception as exc:
        service.record_purge_failed(tenant_id, archive_id, "PROVIDER_FAILURE")
        raise RuntimeError("PROVIDER_FAILURE") from exc
    if not receipt.acknowledged:
        service.record_purge_failed(tenant_id, archive_id, receipt.error_code or "PROVIDER_PURGE_REJECTED")
        raise RuntimeError(receipt.error_code or "PROVIDER_PURGE_REJECTED")
    archive = service.record_purge_completed(tenant_id, archive_id, receipt)
    return {"archive_id": str(archive.id), "lifecycle": archive.lifecycle}


@tenant_context_worker
def process_due_schedules(*, tenant_id: uuid.UUID) -> dict[str, object]:
    jobs = BackupScheduleService().enqueue_due_schedules(tenant_id, now=timezone.now())
    return {"job_ids": [str(job.id) for job in jobs], "enqueued": len(jobs)}


def _required_uuid(payload: dict[str, Any], key: str) -> uuid.UUID:
    value = payload.get(key)
    if value is None:
        raise ValueError(f"Async payload requires {key}")
    return uuid.UUID(str(value))


def _capture_handler(async_job: AsyncJob) -> dict[str, object]:
    return capture_backup(tenant_id=async_job.tenant_id, job_id=_required_uuid(async_job.payload, "job_id"))


def _verify_handler(async_job: AsyncJob) -> dict[str, object]:
    return verify_artifact(
        tenant_id=async_job.tenant_id,
        verification_id=_required_uuid(async_job.payload, "verification_id"),
    )


def _retention_handler(async_job: AsyncJob) -> dict[str, object]:
    return purge_artifact(
        tenant_id=async_job.tenant_id,
        archive_id=_required_uuid(async_job.payload, "archive_id"),
        idempotency_key=str(async_job.id),
    )


def _schedule_handler(async_job: AsyncJob) -> dict[str, object]:
    return process_due_schedules(tenant_id=async_job.tenant_id)


def register_handlers() -> None:
    """Register every command exactly once without silent replacement."""

    global _registered
    with _registration_lock:
        if _registered:
            return
        register_handler("backup_recovery.capture", _capture_handler)
        register_handler("backup_recovery.verify", _verify_handler)
        register_handler("backup_recovery.retention", _retention_handler)
        register_handler("backup_recovery.schedule_due", _schedule_handler)
        _registered = True
