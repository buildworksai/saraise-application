from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from src.core.health import HealthCheckResult

from ..adapter_registry import register_backup_catalog, register_storage_adapter
from ..models import (
    RecoveryPointStatus,
    RestoreRunStatus,
    RunbookActionType,
    RunbookStatus,
    ScopeType,
)
from ..ports import (
    ArtifactValidationResult,
    BackupArtifactDescriptor,
    BackupRequestReceipt,
    BackupScheduleSnapshot,
    BackupStatus,
    BackupStatusSnapshot,
    BackupType,
    RestoreCompensationResult,
    RestorePreflightResult,
    RestoreProviderReceipt,
    RestoreVerificationResult,
)
from ..ports import ScopeType as PortScopeType
from ..services import (
    BackupExecutionFacade,
    BackupRequestCommand,
    DomainConflict,
    RecoveryObjectiveService,
    RecoveryPointService,
    RestoreRunCommand,
    RestoreService,
    RunbookCommand,
    RunbookService,
    RunbookStepCommand,
)
from .factories import recovery_point_factory

pytest_plugins = ["src.core.testing"]


class Catalog:
    def __init__(self, descriptor: BackupArtifactDescriptor) -> None:
        self.descriptor = descriptor
        self.receipt = BackupRequestReceipt(descriptor.backup_job_id, BackupStatus.COMPLETED, "request-1")

    def request_backup(self, tenant_id, actor_id, **kwargs):
        del tenant_id, actor_id, kwargs
        return self.receipt

    def get_backup_status(self, tenant_id, backup_job_id):
        del tenant_id
        return BackupStatusSnapshot(backup_job_id, BackupStatus.COMPLETED, timezone.now())

    def describe_completed_artifact(self, tenant_id, backup_job_id):
        del tenant_id
        assert backup_job_id == self.descriptor.backup_job_id
        return self.descriptor

    def validate_schedule(self, tenant_id, backup_schedule_id):
        del tenant_id
        return BackupScheduleSnapshot(backup_schedule_id, True, BackupType.FULL, "daily")


class Storage:
    def validate_artifact(self, tenant_id, descriptor, *, idempotency_key):
        del tenant_id, descriptor, idempotency_key
        return ArtifactValidationResult(True, True, True, True, True, {"checked": True})

    def restore(self, tenant_id, descriptor, target, *, idempotency_key):
        del tenant_id, descriptor, target, idempotency_key
        return RestoreProviderReceipt(
            "provider-op-1",
            True,
            True,
            {"target_ref": "sandbox", "checksum_digest": "a" * 64, "size_bytes": 4},
        )

    def validate_restore_target(self, tenant_id, descriptor, target, *, idempotency_key):
        del tenant_id, idempotency_key
        capacity_valid = descriptor.size_bytes is not None and descriptor.size_bytes >= 0
        compatibility_valid = target.mode.value in {"full", "selective"}
        target_available = bool(target.target_ref.strip())
        return RestorePreflightResult(
            capacity_valid,
            compatibility_valid,
            target_available,
            {
                "descriptor_size_known": descriptor.size_bytes is not None,
                "target_reference_present": target_available,
                "restore_mode": target.mode.value,
            },
        )

    def verify_restore(self, tenant_id, receipt, *, idempotency_key):
        del tenant_id, receipt, idempotency_key
        return RestoreVerificationResult(True, {"verified": True})

    def compensate_restore(self, tenant_id, receipt, *, idempotency_key):
        del tenant_id, idempotency_key
        compensated = receipt.accepted and receipt.completed
        return RestoreCompensationResult(
            compensated,
            {"provider_operation_acknowledged": compensated},
            "" if compensated else "provider_operation_incomplete",
        )

    def health(self):
        return HealthCheckResult(True)


@pytest.fixture
def domain_ports():
    tenant_id = uuid.uuid4()
    now = timezone.now()
    descriptor = BackupArtifactDescriptor(
        backup_job_id=uuid.uuid4(),
        backup_archive_id=None,
        adapter_key="test-storage",
        artifact_locator_ref="artifact.bin",
        encryption_key_ref=None,
        scope_type=PortScopeType.TENANT,
        scope_ref="primary",
        backup_type=BackupType.FULL,
        data_cutoff_at=now - timedelta(minutes=5),
        captured_at=now,
        expires_at=now + timedelta(days=30),
        size_bytes=4,
        checksum_algorithm="sha256",
        checksum_digest="a" * 64,
        provider_acknowledgement="ack-1",
    )
    catalog = Catalog(descriptor)
    register_backup_catalog("default", catalog, replace=True)
    register_storage_adapter("test-storage", Storage(), replace=True)
    return tenant_id, descriptor, catalog


@pytest.mark.django_db
def test_request_backup_is_durable_and_idempotent(domain_ports):
    tenant_id, descriptor, _ = domain_ports
    actor = uuid.uuid4()
    command = BackupRequestCommand("full", "tenant", "primary", "request-1")
    first = BackupExecutionFacade().request_backup(tenant_id, actor, command).unwrap()
    second = BackupExecutionFacade().request_backup(tenant_id, actor, command).unwrap()
    assert first.backup_job_id == descriptor.backup_job_id
    assert second.backup_job_id == first.backup_job_id


@pytest.mark.django_db
def test_register_and_verify_recovery_point(domain_ports):
    tenant_id, descriptor, _ = domain_ports
    point = BackupExecutionFacade().register_recovery_point(tenant_id, uuid.uuid4(), descriptor.backup_job_id)
    job = RecoveryPointService().request_verification(tenant_id, uuid.uuid4(), point.id, "verify-1")
    verified = RecoveryPointService().execute_verification(tenant_id, point.id, job.id)
    assert verified.status == RecoveryPointStatus.AVAILABLE
    assert verified.verified_at is not None


@pytest.mark.django_db
def test_recovery_point_verification_appends_correlation_bearing_evidence(domain_ports):
    tenant_id, descriptor, _ = domain_ports
    actor_id = uuid.uuid4()
    point = BackupExecutionFacade().register_recovery_point(tenant_id, actor_id, descriptor.backup_job_id)

    first_job = RecoveryPointService().request_verification(tenant_id, actor_id, point.id, "append-evidence-1")
    first_result = RecoveryPointService().execute_verification(tenant_id, point.id, first_job.id)
    first_event = first_result.verification_events.get(sequence=1)
    first_snapshot = dict(first_event.evidence)
    second_job = RecoveryPointService().request_verification(tenant_id, actor_id, point.id, "append-evidence-2")
    second_result = RecoveryPointService().execute_verification(tenant_id, point.id, second_job.id)

    events = list(second_result.verification_events.order_by("sequence"))
    assert [event.sequence for event in events] == [1, 2]
    assert all(event.actor_id == actor_id for event in events)
    assert all(isinstance(event.correlation_id, uuid.UUID) for event in events)
    assert events[0].evidence == first_snapshot
    assert second_result.latest_verification_evidence_id == events[1].id


@pytest.mark.django_db
def test_recovery_point_tenant_isolation(domain_ports):
    tenant_id, descriptor, _ = domain_ports
    point = BackupExecutionFacade().register_recovery_point(tenant_id, uuid.uuid4(), descriptor.backup_job_id)
    with pytest.raises(Exception, match="not found"):
        RecoveryPointService().get_recovery_point(uuid.uuid4(), point.id)


@pytest.mark.django_db
def test_expire_recovery_point_rejects_future_retention(domain_ports):
    tenant_id, _, _ = domain_ports
    point = recovery_point_factory(
        tenant_id=tenant_id, adapter_key="test-storage", status=RecoveryPointStatus.AVAILABLE
    )
    with pytest.raises(DomainConflict, match="expiry"):
        RecoveryPointService().expire_recovery_point(tenant_id, uuid.uuid4(), point.id, "expire-1")


@pytest.mark.django_db
def test_runbook_publish_clone_and_restore(domain_ports):
    tenant_id, descriptor, _ = domain_ports
    actor = uuid.uuid4()
    point = BackupExecutionFacade().register_recovery_point(tenant_id, actor, descriptor.backup_job_id)
    verify_job = RecoveryPointService().request_verification(tenant_id, actor, point.id, "publish-point")
    point = RecoveryPointService().execute_verification(tenant_id, point.id, verify_job.id)
    service = RunbookService()
    runbook = service.create_runbook(
        tenant_id,
        actor,
        RunbookCommand(
            name="Primary recovery",
            slug="primary-recovery",
            description="Verified tenant recovery",
            scope_type=ScopeType.TENANT,
            scope_ref="primary",
            adapter_key="test-storage",
            rpo_target_seconds=3600,
            rto_target_seconds=7200,
            owner_id=actor,
        ),
    )
    service.create_step(
        tenant_id,
        actor,
        RunbookStepCommand(
            runbook.id,
            "validate",
            1,
            "Validate artifact",
            "",
            RunbookActionType.VALIDATE_RECOVERY_POINT,
            {"require_checksum": True, "require_encryption": True},
            300,
            0,
            "stop",
        ),
    )
    published = service.publish(tenant_id, actor, runbook.id, "publish-1")
    assert published.status == RunbookStatus.PUBLISHED
    clone = service.clone_version(tenant_id, actor, published.id)
    assert clone.version == 2 and clone.status == RunbookStatus.DRAFT

    restore = RestoreService().create_restore_run(
        tenant_id,
        actor,
        RestoreRunCommand(
            recovery_point_id=point.id,
            runbook_id=published.id,
            target_environment="isolated",
            target_ref="sandbox",
            restore_mode="full",
            selected_components=(),
            idempotency_key="restore-1",
        ),
    )
    RestoreService().validate_restore(tenant_id, restore.id, restore.async_job_id)
    job = RestoreService().execute_restore(tenant_id, actor, restore.id, "execute-1")
    completed = RestoreService().execute_restore_job(tenant_id, restore.id, job.id)
    assert completed.status == RestoreRunStatus.SUCCEEDED
    assert completed.verification_evidence["verified"] is True


@pytest.mark.django_db
def test_production_restore_requires_approval(domain_ports):
    tenant_id, descriptor, _ = domain_ports
    point = BackupExecutionFacade().register_recovery_point(tenant_id, uuid.uuid4(), descriptor.backup_job_id)
    verify_job = RecoveryPointService().request_verification(tenant_id, uuid.uuid4(), point.id, "production-point")
    point = RecoveryPointService().execute_verification(tenant_id, point.id, verify_job.id)
    with pytest.raises(Exception, match="approval"):
        RestoreService().create_restore_run(
            tenant_id,
            uuid.uuid4(),
            RestoreRunCommand(point.id, "production", "prod", "full", (), "restore-prod"),
        )


@pytest.mark.django_db
def test_objective_threshold_equality_is_compliant(domain_ports):
    tenant_id, descriptor, _ = domain_ports
    point = BackupExecutionFacade().register_recovery_point(tenant_id, uuid.uuid4(), descriptor.backup_job_id)
    verify_job = RecoveryPointService().request_verification(tenant_id, uuid.uuid4(), point.id, "objective-point")
    point = RecoveryPointService().execute_verification(tenant_id, point.id, verify_job.id)
    run = RestoreService().create_restore_run(
        tenant_id,
        uuid.uuid4(),
        RestoreRunCommand(point.id, "isolated", "objective", "full", (), "objective-1"),
    )
    run.started_at = point.data_cutoff_at + timedelta(seconds=60)
    run.completed_at = run.started_at + timedelta(seconds=60)
    run.save(update_fields=["started_at", "completed_at", "updated_at"])
    measurement = RecoveryObjectiveService().calculate_restore_objectives(tenant_id, run.id)
    assert measurement.rpo_seconds == 60
    assert measurement.rto_seconds == 60
