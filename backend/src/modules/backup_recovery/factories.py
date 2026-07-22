"""Small, explicit test-data factories using only valid production values.

These are functions rather than factory-boy classes so the production package
does not acquire a test-only runtime dependency.
"""

from __future__ import annotations

import uuid
from datetime import time
from typing import Any

from django.utils import timezone

from .models import (
    BackupArchive,
    BackupJob,
    BackupJobStatus,
    BackupRetentionPolicy,
    BackupSchedule,
    BackupStorageTarget,
    BackupVerification,
)


def storage_target_factory(tenant_id: uuid.UUID, **overrides: Any) -> BackupStorageTarget:
    values = {
        "name": f"Local target {uuid.uuid4().hex[:8]}",
        "adapter_key": "local-filesystem",
        "locator_prefix_ref": "backup-root",
        "configuration_ref": "backup-local-default",
        "created_by": "test-suite",
    }
    values.update(overrides)
    return BackupStorageTarget.objects.create(tenant_id=tenant_id, **values)


def retention_policy_factory(tenant_id: uuid.UUID, **overrides: Any) -> BackupRetentionPolicy:
    values = {
        "name": f"Policy {uuid.uuid4().hex[:8]}",
        "retention_days": 30,
        "archive_after_days": 7,
        "keep_last_successful": 3,
        "created_by": "test-suite",
    }
    values.update(overrides)
    return BackupRetentionPolicy.objects.create(tenant_id=tenant_id, **values)


def schedule_factory(tenant_id: uuid.UUID, **overrides: Any) -> BackupSchedule:
    target = overrides.pop("storage_target", None) or storage_target_factory(tenant_id)
    policy = overrides.pop("retention_policy", None) or retention_policy_factory(tenant_id)
    values = {
        "name": f"Daily backup {uuid.uuid4().hex[:8]}",
        "scope_type": "tenant",
        "scope_ref": str(tenant_id),
        "backup_type": "full",
        "frequency": "daily",
        "schedule_time": time(2, 0),
        "timezone": "UTC",
        "storage_target": target,
        "retention_policy": policy,
        "created_by": "test-suite",
    }
    values.update(overrides)
    return BackupSchedule.objects.create(tenant_id=tenant_id, **values)


def job_factory(tenant_id: uuid.UUID, **overrides: Any) -> BackupJob:
    target = overrides.pop("storage_target", None) or storage_target_factory(tenant_id)
    values = {
        "storage_target": target,
        "scope_type": "tenant",
        "scope_ref": str(tenant_id),
        "backup_type": "full",
        "status": BackupJobStatus.PENDING,
        "idempotency_key": f"test:{uuid.uuid4()}",
        "created_by": "test-suite",
    }
    values.update(overrides)
    return BackupJob.objects.create(tenant_id=tenant_id, **values)


def completed_job_with_archive_factory(
    tenant_id: uuid.UUID, **archive_overrides: Any
) -> tuple[BackupJob, BackupArchive]:
    now = timezone.now()
    job = job_factory(tenant_id, status=BackupJobStatus.RUNNING, started_at=now)
    archive_values = {
        "backup_job": job,
        "lifecycle": "available",
        "adapter_key": job.storage_target.adapter_key,
        "artifact_locator_ref": f"artifact-{job.id}",
        "size_bytes": 0,
        "checksum_algorithm": "sha256",
        "checksum_digest": "0" * 64,
        "provider_acknowledgement": f"ack-{job.id}",
        "data_cutoff_at": now,
        "captured_at": now,
        "created_by": "test-suite",
    }
    archive_values.update(archive_overrides)
    job.completed_at = now
    job.data_cutoff_at = now
    job.size_bytes = archive_values["size_bytes"]
    job.save(update_fields=["completed_at", "data_cutoff_at", "size_bytes", "updated_at"])
    archive = BackupArchive.objects.create(tenant_id=tenant_id, **archive_values)
    job.status = BackupJobStatus.COMPLETED
    job.save(update_fields=["status", "updated_at"])
    return job, archive


def verification_factory(tenant_id: uuid.UUID, **overrides: Any) -> BackupVerification:
    archive = overrides.pop("archive", None)
    if archive is None:
        _, archive = completed_job_with_archive_factory(tenant_id)
    values = {
        "archive": archive,
        "idempotency_key": f"verify:{uuid.uuid4()}",
        "created_by": "test-suite",
    }
    values.update(overrides)
    return BackupVerification.objects.create(tenant_id=tenant_id, **values)


__all__ = [
    "completed_job_with_archive_factory",
    "job_factory",
    "retention_policy_factory",
    "schedule_factory",
    "storage_target_factory",
    "verification_factory",
]
