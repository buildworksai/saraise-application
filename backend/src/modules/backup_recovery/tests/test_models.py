"""Persistence and transition invariants for the backup catalog."""

from __future__ import annotations

import uuid
from datetime import time, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.utils import timezone

from src.core.state_machine import GuardFailedError, IllegalTransitionError, TerminalStateError
from src.core.tenancy import TenantScopedModel
from src.modules.backup_recovery.factories import (
    completed_job_with_archive_factory,
    job_factory,
    retention_policy_factory,
    schedule_factory,
    storage_target_factory,
    verification_factory,
)
from src.modules.backup_recovery.models import (
    BackupArchive,
    BackupJob,
    BackupJobStatus,
    BackupStorageTarget,
    VerificationStatus,
)
from src.modules.backup_recovery.state_machines import JOB_STATE_MACHINE, VERIFICATION_STATE_MACHINE

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


def test_all_entities_have_uuid_identity_and_canonical_tenant_base(tenant_id: uuid.UUID) -> None:
    target = storage_target_factory(tenant_id)
    policy = retention_policy_factory(tenant_id)
    schedule = schedule_factory(tenant_id, storage_target=target, retention_policy=policy)
    job = job_factory(tenant_id, storage_target=target)
    _, archive = completed_job_with_archive_factory(tenant_id)
    verification = verification_factory(tenant_id, archive=archive)
    for entity in (target, policy, schedule, job, archive, verification):
        assert isinstance(entity, TenantScopedModel)
        assert isinstance(entity.id, uuid.UUID)
        assert isinstance(entity.tenant_id, uuid.UUID)
        assert entity._meta.get_field("tenant_id").db_index is True


def test_soft_delete_manager_hides_but_audit_manager_retains(tenant_id: uuid.UUID) -> None:
    target = storage_target_factory(tenant_id)
    target.is_deleted = True
    target.deleted_at = timezone.now()
    target.is_active = False
    target.is_default = False
    target.save()
    assert not BackupStorageTarget.objects.filter(pk=target.pk).exists()
    assert BackupStorageTarget.all_with_deleted.get(pk=target.pk) == target


def test_soft_delete_timestamps_are_consistent(tenant_id: uuid.UUID) -> None:
    target = storage_target_factory(tenant_id)
    target.is_deleted = True
    with pytest.raises(ValidationError, match="deleted_at"):
        target.save()


def test_target_name_and_default_are_unique_per_active_tenant(tenant_id: uuid.UUID) -> None:
    storage_target_factory(tenant_id, name="Primary", is_default=True)
    with pytest.raises(ValidationError):
        storage_target_factory(tenant_id, name="Primary")
    with pytest.raises(ValidationError):
        storage_target_factory(tenant_id, name="Secondary", is_default=True)
    storage_target_factory(uuid.uuid4(), name="Primary", is_default=True)


@pytest.mark.parametrize("adapter_key", ["UPPER", "space key", "leading-", "provider?"])
def test_target_adapter_key_and_secret_references_are_rejected(tenant_id: uuid.UUID, adapter_key: str) -> None:
    with pytest.raises(ValidationError):
        storage_target_factory(tenant_id, adapter_key=adapter_key)
    with pytest.raises(ValidationError, match="credentials"):
        storage_target_factory(tenant_id, locator_prefix_ref="s3://user:password@example/bucket")


@pytest.mark.parametrize(
    ("retention", "archive_after", "keep"),
    [(0, None, 3), (3651, None, 3), (30, 30, 3), (30, 31, 3), (30, None, 0)],
)
def test_retention_bounds(tenant_id: uuid.UUID, retention: int, archive_after: int | None, keep: int) -> None:
    with pytest.raises(ValidationError):
        retention_policy_factory(
            tenant_id,
            retention_days=retention,
            archive_after_days=archive_after,
            keep_last_successful=keep,
        )


@pytest.mark.parametrize(
    ("frequency", "schedule_time", "weekday", "monthday", "valid"),
    [
        ("hourly", None, None, None, True),
        ("hourly", time(1), None, None, False),
        ("daily", time(1), None, None, True),
        ("daily", None, None, None, False),
        ("weekly", time(1), 6, None, True),
        ("weekly", time(1), 7, None, False),
        ("monthly", time(1), None, 28, True),
        ("monthly", time(1), None, 29, False),
    ],
)
def test_schedule_frequency_fields(
    tenant_id: uuid.UUID,
    frequency: str,
    schedule_time: time | None,
    weekday: int | None,
    monthday: int | None,
    valid: bool,
) -> None:
    create = lambda: schedule_factory(  # noqa: E731
        tenant_id,
        frequency=frequency,
        schedule_time=schedule_time,
        day_of_week=weekday,
        day_of_month=monthday,
    )
    if valid:
        assert create().frequency == frequency
    else:
        with pytest.raises(ValidationError):
            create()


def test_cross_tenant_relations_are_rejected(tenant_id: uuid.UUID) -> None:
    foreign_target = storage_target_factory(uuid.uuid4())
    policy = retention_policy_factory(tenant_id)
    with pytest.raises(ValidationError, match="same tenant"):
        schedule_factory(tenant_id, storage_target=foreign_target, retention_policy=policy)
    own_target = storage_target_factory(tenant_id)
    foreign_job = job_factory(uuid.uuid4())
    with pytest.raises(ValidationError, match="same tenant"):
        job_factory(tenant_id, storage_target=own_target, retry_of=foreign_job)


def test_incremental_and_differential_require_completed_baseline(tenant_id: uuid.UUID) -> None:
    target = storage_target_factory(tenant_id)
    with pytest.raises(ValidationError, match="baseline"):
        job_factory(tenant_id, storage_target=target, backup_type="incremental")
    pending_base = job_factory(tenant_id, storage_target=target)
    with pytest.raises(ValidationError, match="completed"):
        job_factory(tenant_id, storage_target=target, backup_type="differential", base_job=pending_base)
    complete, _ = completed_job_with_archive_factory(tenant_id)
    assert job_factory(tenant_id, storage_target=complete.storage_target, backup_type="incremental", base_job=complete)


def test_job_state_machine_guards_history_and_terminal_state(tenant_id: uuid.UUID) -> None:
    job = job_factory(tenant_id)
    with pytest.raises(GuardFailedError):
        JOB_STATE_MACHINE.apply(job, "start", transition_key="start-no-claim")
    running = JOB_STATE_MACHINE.apply(
        job,
        "start",
        transition_key="start-1",
        context={"async_job_claimed": True, "adapter_available": True},
    )
    assert running.status == BackupJobStatus.RUNNING
    assert [entry["command"] for entry in running.transition_history] == ["start"]
    with pytest.raises(IllegalTransitionError):
        JOB_STATE_MACHINE.apply(running, "start", transition_key="start-2")
    cancelled = JOB_STATE_MACHINE.apply(
        running,
        "cancel",
        transition_key="cancel-1",
        context={"before_commit": True},
    )
    assert cancelled.status == BackupJobStatus.CANCELLED
    with pytest.raises(TerminalStateError):
        JOB_STATE_MACHINE.apply(cancelled, "start", transition_key="terminal")
    assert len(cancelled.transition_history) == 2


def test_verification_state_machine_and_terminal_immutability(tenant_id: uuid.UUID) -> None:
    verification = verification_factory(tenant_id)
    running = VERIFICATION_STATE_MACHINE.apply(verification, "start", transition_key="verify-start")
    running.checksum_matches = True
    running.artifact_available = True
    running.encryption_metadata_valid = True
    running.provider_acknowledged = True
    running.completed_at = timezone.now()
    running.started_at = running.completed_at - timedelta(seconds=1)
    running.save()
    passed = VERIFICATION_STATE_MACHINE.apply(running, "pass", transition_key="verify-pass")
    assert passed.status == VerificationStatus.PASSED
    passed.error_message = "mutation"
    with pytest.raises(ValidationError, match="append-only"):
        passed.save()


def test_archive_checksum_expiry_and_evidence_immutability(tenant_id: uuid.UUID) -> None:
    now = timezone.now()
    job = job_factory(tenant_id, status="running", started_at=now)
    with pytest.raises(ValidationError, match="Checksum"):
        BackupArchive.objects.create(
            tenant_id=tenant_id,
            backup_job=job,
            adapter_key="local-filesystem",
            artifact_locator_ref="artifact",
            size_bytes=1,
            checksum_digest="ABC",
            provider_acknowledgement="ack",
            data_cutoff_at=now,
            captured_at=now,
            created_by="tester",
        )
    _, archive = completed_job_with_archive_factory(tenant_id, expires_at=now + timedelta(days=1))
    archive.checksum_digest = "f" * 64
    with pytest.raises(ValidationError, match="immutable"):
        archive.save()


def test_archive_and_verification_are_not_deletable_and_relations_are_protected(tenant_id: uuid.UUID) -> None:
    job, archive = completed_job_with_archive_factory(tenant_id)
    verification = verification_factory(tenant_id, archive=archive)
    with pytest.raises(TypeError):
        archive.delete()
    with pytest.raises(TypeError):
        verification.delete()
    # QuerySet deletion bypasses instance delete but database PROTECT still guards evidence.
    with pytest.raises(ProtectedError):
        BackupJob.all_with_deleted.filter(pk=job.pk).delete()
