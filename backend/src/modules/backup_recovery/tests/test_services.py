"""Transactional service, adapter, scheduling, and retention contracts."""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta
from datetime import timezone as datetime_timezone
from pathlib import Path

import pytest
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob

from ..adapter_registry import DuplicateRegistration, ExtensionRegistry
from ..adapters.local_filesystem import LocalFilesystemCaptureAdapter
from ..factories import retention_policy_factory, storage_target_factory
from ..models import BackupArchive, BackupJob
from ..ports import BackupType, ScopeType
from ..services import (
    BackupArtifactService,
    BackupRecoveryService,
    BackupScheduleService,
    DomainConflict,
    RetentionPolicyService,
    StorageTargetService,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


def test_storage_target_crud_default_activation_deletion_and_real_probe(tenant_id, tmp_path):
    service = StorageTargetService()
    first = service.create(
        tenant_id,
        "actor",
        {
            "name": "First",
            "adapter_key": "local-filesystem",
            "locator_prefix_ref": str(tmp_path / "first"),
            "configuration_ref": "local",
            "is_default": True,
        },
    )
    second = service.create(
        tenant_id,
        "actor",
        {
            "name": "Second",
            "adapter_key": "local-filesystem",
            "locator_prefix_ref": str(tmp_path / "second"),
            "configuration_ref": "local",
        },
    )
    assert service.get(tenant_id, first.id) == first
    assert list(service.list(tenant_id, {"is_active": True})) == [first, second]
    second = service.set_default(tenant_id, "actor", second.id)
    first.refresh_from_db()
    assert second.is_default and not first.is_default
    assert service.probe(tenant_id, "actor", second.id).unwrap().healthy
    service.deactivate(tenant_id, "actor", second.id)
    service.activate(tenant_id, "actor", second.id)
    service.delete(tenant_id, "actor", first.id)
    assert not service.list(tenant_id).filter(pk=first.id).exists()


def test_retention_policy_crud_and_preview(tenant_id):
    service = RetentionPolicyService()
    policy = service.create(tenant_id, "actor", {"name": "Standard", "retention_days": 30, "archive_after_days": 7})
    captured = timezone.now()
    preview = service.preview(tenant_id, policy.id, captured_at=captured)
    assert preview.archive_at == captured + timedelta(days=7)
    assert preview.expires_at == captured + timedelta(days=30)
    assert service.update(tenant_id, "actor", policy.id, {"retention_days": 60}).retention_days == 60
    assert not service.deactivate(tenant_id, "actor", policy.id).is_active
    assert service.activate(tenant_id, "actor", policy.id).is_active
    service.delete(tenant_id, "actor", policy.id)


def test_schedule_crud_run_now_due_claim_and_dst_resolution(tenant_id, tmp_path):
    target = storage_target_factory(tenant_id, locator_prefix_ref=str(tmp_path), is_default=True)
    policy = retention_policy_factory(tenant_id)
    service = BackupScheduleService()
    schedule = service.create(
        tenant_id,
        "actor",
        {
            "name": "Daily",
            "scope_type": "files",
            "scope_ref": str(tmp_path),
            "backup_type": "full",
            "frequency": "daily",
            "schedule_time": time(2, 30),
            "timezone": "America/New_York",
            "storage_target": target,
            "retention_policy": policy,
        },
    )
    # 02:30 does not exist on the 2026 spring-forward day; policy advances deterministically.
    after = datetime(2026, 3, 8, 6, 59, tzinfo=datetime_timezone.utc)
    assert service.compute_next_run(schedule, after=after) == datetime(2026, 3, 8, 7, 0, tzinfo=datetime_timezone.utc)
    job = service.run_now(tenant_id, "actor", schedule.id, "manual-run")
    assert job.schedule_id == schedule.id and job.async_job_id is not None
    assert service.get(tenant_id, schedule.id) == schedule
    assert service.list(tenant_id, {"frequency": "daily"}).filter(pk=schedule.id).exists()
    service.deactivate(tenant_id, "actor", schedule.id)
    with pytest.raises(DomainConflict):
        service.run_now(tenant_id, "actor", schedule.id, "inactive")
    service.activate(tenant_id, "actor", schedule.id)
    service.delete(tenant_id, "actor", schedule.id)


def test_backup_request_is_idempotent_and_conflicts_on_changed_payload(tenant_id, tmp_path):
    target = storage_target_factory(tenant_id, locator_prefix_ref=str(tmp_path), is_default=True)
    service = BackupRecoveryService()
    first = service.request_backup(
        tenant_id,
        "actor",
        backup_type="full",
        scope_type="files",
        scope_ref=str(tmp_path),
        idempotency_key="same",
        storage_target_id=target.id,
    )
    duplicate = service.request_backup(
        tenant_id,
        "actor",
        backup_type="full",
        scope_type="files",
        scope_ref=str(tmp_path),
        idempotency_key="same",
        storage_target_id=target.id,
    )
    assert duplicate == first
    assert BackupJob.objects.filter(tenant_id=tenant_id).count() == 1
    assert AsyncJob.objects.filter(tenant_id=tenant_id).count() == 1
    with pytest.raises(DomainConflict):
        service.request_backup(
            tenant_id,
            "actor",
            backup_type="full",
            scope_type="files",
            scope_ref="different",
            idempotency_key="same",
            storage_target_id=target.id,
        )


def test_real_capture_completion_catalog_and_verification(tenant_id, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("durable backup evidence", encoding="utf-8")
    target = storage_target_factory(tenant_id, locator_prefix_ref=str(tmp_path / "archives"), is_default=True)
    service = BackupRecoveryService()
    receipt = service.request_backup(
        tenant_id,
        "actor",
        backup_type=BackupType.FULL,
        scope_type=ScopeType.FILES,
        scope_ref=str(source),
        idempotency_key="capture",
        storage_target_id=target.id,
    )
    completed = service.execute_backup(tenant_id, receipt.backup_job_id)
    assert completed.status == "completed"
    descriptor = service.describe_completed_artifact(tenant_id, completed.id)
    assert descriptor.size_bytes is not None and descriptor.size_bytes > 0
    assert len(descriptor.checksum_digest) == 64
    assert Path(descriptor.artifact_locator_ref).is_file()
    snapshot = service.get_backup_status(tenant_id, completed.id)
    assert snapshot.status.value == "completed"
    verification = BackupArtifactService().request_verification(tenant_id, "actor", completed.archive.id, "verify-once")
    assert verification.async_job_id is not None
    verification = BackupArtifactService().execute_verification(tenant_id, verification.id)
    assert verification.status == "passed"
    completed.archive.refresh_from_db()
    assert completed.archive.integrity_status == "verified"


def test_cancel_retry_description_and_soft_delete(tenant_id, tmp_path):
    target = storage_target_factory(tenant_id, locator_prefix_ref=str(tmp_path), is_default=True)
    service = BackupRecoveryService()
    receipt = service.request_backup(
        tenant_id,
        "actor",
        backup_type="full",
        scope_type="tenant",
        scope_ref=str(tenant_id),
        idempotency_key="cancel-me",
        storage_target_id=target.id,
    )
    job = service.update_job_description(tenant_id, "actor", receipt.backup_job_id, "Before cancellation")
    job = service.cancel_backup(tenant_id, "actor", job.id, "cancel-command")
    assert job.status == "cancelled"
    retried = service.retry_backup(tenant_id, "actor", job.id, "retry-command")
    assert service.get_backup_job(tenant_id, retried.backup_job_id).retry_of_id == job.id
    service.soft_delete_job(tenant_id, "actor", job.id)
    assert not BackupJob.objects.filter(pk=job.id).exists()


def test_retention_expiry_purge_and_failure_evidence(tenant_id, tmp_path):
    source = tmp_path / "artifact.bin"
    source.write_bytes(b"artifact")
    archive_root = tmp_path / "archives"
    target = storage_target_factory(tenant_id, locator_prefix_ref=str(archive_root), is_default=True)
    capture = BackupRecoveryService().request_backup(
        tenant_id,
        "actor",
        backup_type="full",
        scope_type="files",
        scope_ref=str(source),
        idempotency_key="retention",
        storage_target_id=target.id,
    )
    job = BackupRecoveryService().execute_backup(tenant_id, capture.backup_job_id)
    archive = job.archive
    BackupArchive.objects.filter(pk=archive.id).update(expires_at=timezone.now() - timedelta(seconds=1))
    expired = BackupArtifactService().expire_due_artifacts(tenant_id, now=timezone.now())
    assert [item.id for item in expired] == [archive.id]
    async_job = BackupArtifactService().request_purge(tenant_id, archive.id, "purge")
    assert async_job.command == "backup_recovery.retention"
    assert BackupArtifactService().request_purge(tenant_id, archive.id, "purge").id == async_job.id
    failed = BackupArtifactService().record_purge_failed(tenant_id, archive.id, "PROVIDER_TIMEOUT")
    assert failed.lifecycle == "expired" and failed.purge_error_code == "PROVIDER_TIMEOUT"
    descriptor = BackupRecoveryService().describe_completed_artifact(tenant_id, job.id)
    provider_receipt = LocalFilesystemCaptureAdapter(archive_root).purge(descriptor, idempotency_key=str(async_job.id))
    purged = BackupArtifactService().record_purge_completed(tenant_id, archive.id, provider_receipt)
    assert purged.lifecycle == "purged" and purged.purged_at is not None


def test_registry_duplicate_and_missing_adapter_fail_closed():
    registry = ExtensionRegistry[object]()
    value = object()
    registry.register("adapter", value)
    with pytest.raises(DuplicateRegistration):
        registry.register("adapter", object())
    assert registry.register("adapter", value, replace=True) is value
    with pytest.raises(Exception, match="currently unavailable"):
        registry.get("missing")
