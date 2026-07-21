from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.test import override_settings
from django.utils import timezone

from src.modules.backup_disaster_recovery.adapter_registry import (
    AdapterAlreadyRegistered,
    AdapterNotRegistered,
    BackupRecoveryCatalogAdapter,
    LocalFilesystemStorageRecoveryAdapter,
    ProviderOperationError,
    get_storage_adapter,
    register_storage_adapter,
    unregister_storage_adapter,
)
from src.modules.backup_disaster_recovery.ports import (
    BackupArtifactDescriptor,
    BackupRequestReceipt,
    BackupStatus,
    BackupType,
    RestoreEnvironment,
    RestoreMode,
    RestoreTarget,
    ScopeType,
)


def _descriptor(content: bytes, *, locator: str = "tenant/artifact.bin") -> BackupArtifactDescriptor:
    now = timezone.now()
    return BackupArtifactDescriptor(
        backup_job_id=uuid4(),
        backup_archive_id=None,
        adapter_key="local-filesystem",
        artifact_locator_ref=locator,
        encryption_key_ref=None,
        scope_type=ScopeType.TENANT,
        scope_ref="tenant",
        backup_type=BackupType.FULL,
        data_cutoff_at=now - timedelta(seconds=1),
        captured_at=now,
        expires_at=now + timedelta(days=30),
        size_bytes=len(content),
        checksum_algorithm="sha256",
        checksum_digest=hashlib.sha256(content).hexdigest(),
        provider_acknowledgement="local-capture",
    )


def test_port_values_are_immutable() -> None:
    receipt = BackupRequestReceipt(uuid4(), BackupStatus.PENDING, "request-1")
    with pytest.raises(FrozenInstanceError):
        receipt.status = BackupStatus.COMPLETED  # type: ignore[misc]


def test_storage_registry_rejects_duplicates_and_missing_entries(tmp_path) -> None:
    key = f"test-{uuid4()}"
    adapter = LocalFilesystemStorageRecoveryAdapter(storage_root=tmp_path, restore_root=tmp_path)
    try:
        assert register_storage_adapter(key, adapter) is adapter
        assert get_storage_adapter(key) is adapter
        with pytest.raises(AdapterAlreadyRegistered):
            register_storage_adapter(key, adapter)
    finally:
        unregister_storage_adapter(key)
    with pytest.raises(AdapterNotRegistered):
        get_storage_adapter(key)


def test_local_adapter_validates_real_checksum_and_missing_artifact(tmp_path) -> None:
    storage = tmp_path / "storage"
    restore = tmp_path / "restore"
    (storage / "tenant").mkdir(parents=True)
    restore.mkdir()
    content = b"authoritative backup bytes"
    (storage / "tenant" / "artifact.bin").write_bytes(content)
    adapter = LocalFilesystemStorageRecoveryAdapter(storage_root=storage, restore_root=restore)

    valid = adapter.validate_artifact(uuid4(), _descriptor(content), idempotency_key="job-1")
    assert valid.valid is True
    assert valid.checksum_matches is True
    assert valid.evidence["size_bytes"] == len(content)

    mismatch = adapter.validate_artifact(uuid4(), _descriptor(b"different"), idempotency_key="job-2")
    assert mismatch.valid is False
    assert mismatch.error_code == "artifact_integrity_failed"

    missing = adapter.validate_artifact(
        uuid4(),
        _descriptor(content, locator="tenant/missing.bin"),
        idempotency_key="job-3",
    )
    assert missing.artifact_available is False
    assert missing.error_code == "artifact_missing"


def test_local_adapter_restores_atomically_and_redelivery_is_idempotent(tmp_path) -> None:
    storage = tmp_path / "storage"
    restore = tmp_path / "restore"
    (storage / "tenant").mkdir(parents=True)
    restore.mkdir()
    content = b"restorable content"
    (storage / "tenant" / "artifact.bin").write_bytes(content)
    adapter = LocalFilesystemStorageRecoveryAdapter(storage_root=storage, restore_root=restore)
    target = RestoreTarget(RestoreEnvironment.ISOLATED, "sandbox/restored.bin", RestoreMode.FULL)

    receipt = adapter.restore(uuid4(), _descriptor(content), target, idempotency_key="durable-job-id")
    redelivered = adapter.restore(uuid4(), _descriptor(content), target, idempotency_key="durable-job-id")
    assert receipt == redelivered
    assert (restore / "sandbox" / "restored.bin").read_bytes() == content
    assert adapter.verify_restore(uuid4(), receipt, idempotency_key="verify-job").verified is True


def test_local_adapter_rejects_path_escape_and_unconfigured_health(tmp_path) -> None:
    storage = tmp_path / "storage"
    restore = tmp_path / "restore"
    storage.mkdir()
    restore.mkdir()
    adapter = LocalFilesystemStorageRecoveryAdapter(storage_root=storage, restore_root=restore)
    with pytest.raises(ProviderOperationError):
        adapter.validate_artifact(uuid4(), _descriptor(b"x", locator="../escape"), idempotency_key="job")

    unavailable = LocalFilesystemStorageRecoveryAdapter(storage_root=None, restore_root=None)
    result = unavailable.health()
    assert result.healthy is False
    assert "not configured" in result.message


class _CatalogService:
    def request_backup(self, tenant_id, actor_id, **kwargs):
        del tenant_id, actor_id, kwargs
        return BackupRequestReceipt(uuid4(), BackupStatus.PENDING, "request-key")

    def get_backup_status(self, tenant_id, backup_job_id):
        del tenant_id
        return type(
            "Status",
            (),
            {"id": backup_job_id, "status": "completed", "completed_at": timezone.now(), "error_code": ""},
        )()


def test_backup_catalog_normalizes_service_results_without_model_imports() -> None:
    adapter = BackupRecoveryCatalogAdapter(_CatalogService())
    receipt = adapter.request_backup(
        uuid4(),
        uuid4(),
        backup_type=BackupType.FULL,
        scope_type=ScopeType.TENANT,
        scope_ref="tenant",
        idempotency_key="request-key",
    )
    assert receipt.status is BackupStatus.PENDING
    snapshot = adapter.get_backup_status(uuid4(), receipt.backup_job_id)
    assert snapshot.status is BackupStatus.COMPLETED


def test_backup_catalog_builds_legacy_descriptor_from_real_completed_artifact(tmp_path) -> None:
    content = b"completed backup"
    (tmp_path / "tenant").mkdir()
    (tmp_path / "tenant" / "backup.bin").write_bytes(content)
    backup_job_id = uuid4()
    job = SimpleNamespace(
        id=backup_job_id,
        status="completed",
        description="tenant:tenant",
        storage_location="tenant/backup.bin",
        backup_size_bytes=len(content),
        end_time=timezone.now(),
        backup_type="full",
    )

    class LegacyService:
        def get_backup_job(self, job_id, tenant_id):
            del tenant_id
            return job if job_id == str(backup_job_id) else None

    adapter = BackupRecoveryCatalogAdapter(LegacyService())
    with override_settings(BDR_LOCAL_STORAGE_ROOT=str(tmp_path)):
        descriptor = adapter.describe_completed_artifact(uuid4(), backup_job_id)
    assert descriptor.artifact_locator_ref == "tenant/backup.bin"
    assert descriptor.checksum_digest == hashlib.sha256(content).hexdigest()
    assert descriptor.size_bytes == len(content)
