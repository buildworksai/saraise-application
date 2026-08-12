from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from src.core.health import HealthCheckResult

from ..adapter_registry import (
    AdapterAlreadyRegistered,
    AdapterNotRegistered,
    BackupRecoveryCatalogAdapter,
    LocalFilesystemStorageRecoveryAdapter,
    ProviderConfigurationError,
    ProviderOperationError,
    ResiliencePolicy,
    _active_policy,
    _Registry,
    _status,
    get_evidence_enricher,
    get_extension_action,
    get_metrics_collector,
    get_provider_health_probe,
    get_readiness_rule,
    get_report_exporter,
    register_evidence_enricher,
    register_metrics_collector,
    register_provider_health_probe,
    register_readiness_rule,
    register_report_exporter,
)
from ..ports import (
    BackupArtifactDescriptor,
    BackupStatus,
    BackupType,
    RestoreEnvironment,
    RestoreMode,
    RestoreProviderReceipt,
    RestoreTarget,
)
from ..ports import ScopeType as PortScopeType


def descriptor(**overrides: object) -> BackupArtifactDescriptor:
    now = timezone.now()
    values = {
        "backup_job_id": uuid.uuid4(),
        "backup_archive_id": None,
        "adapter_key": LocalFilesystemStorageRecoveryAdapter.key,
        "artifact_locator_ref": "artifact.bin",
        "encryption_key_ref": None,
        "scope_type": PortScopeType.FILES,
        "scope_ref": "artifact.bin",
        "backup_type": BackupType.FULL,
        "data_cutoff_at": now - timedelta(minutes=1),
        "captured_at": now,
        "expires_at": now + timedelta(days=1),
        "size_bytes": 7,
        "checksum_algorithm": "sha256",
        "checksum_digest": "0" * 64,
        "provider_acknowledgement": "ack",
    }
    values.update(overrides)
    return BackupArtifactDescriptor(**values)


def test_internal_registry_rejects_bad_keys_duplicates_and_missing_entries() -> None:
    registry: _Registry[object] = _Registry("provider")
    value = object()

    assert registry.register(" Provider ", value) is value
    assert registry.keys() == ("provider",)
    with pytest.raises(AdapterAlreadyRegistered):
        registry.register("provider", object())
    replacement = object()
    assert registry.register("provider", replacement, replace=True) is replacement
    assert registry.unregister("provider") is replacement
    assert registry.unregister("provider") is None
    with pytest.raises(AdapterNotRegistered):
        registry.get("provider")
    with pytest.raises(ValueError):
        registry.register("x" * 121, object())


@pytest.mark.parametrize(
    "registrar,getter",
    [
        (register_evidence_enricher, lambda value: value("event")),
        (register_report_exporter, lambda value: value({"report": True})),
        (register_readiness_rule, lambda value: value(uuid.uuid4())),
        (register_provider_health_probe, lambda value: value()),
        (register_metrics_collector, lambda value: value()),
    ],
)
def test_extension_registrars_require_callable_values(registrar, getter) -> None:
    with pytest.raises(TypeError):
        registrar("bad", object())

    called: list[object] = []

    def handler(*args):
        called.extend(args)
        if registrar is register_provider_health_probe:
            return HealthCheckResult(True)
        if registrar is register_report_exporter:
            return b"report"
        return {"ok": True}

    registered = registrar("custom", handler, replace=True)
    result = getter(registered)
    if registrar is register_provider_health_probe:
        assert isinstance(result, HealthCheckResult)
        assert result.healthy is True
    else:
        assert result in ({"ok": True}, b"report", None)
    if registrar in (register_evidence_enricher, register_report_exporter, register_readiness_rule):
        assert called


def test_extension_getters_return_registered_handlers_without_invocation() -> None:
    def evidence(*args, **kwargs):
        del args, kwargs
        return {"safe": True}

    def exporter(*args, **kwargs):
        del args, kwargs
        return b"safe"

    def readiness(*args, **kwargs):
        del args, kwargs
        return {"ready": True}

    def health():
        return HealthCheckResult(True)

    def metrics():
        return None

    register_evidence_enricher("getter-evidence", evidence, replace=True)
    register_report_exporter("getter-export", exporter, replace=True)
    register_readiness_rule("getter-readiness", readiness, replace=True)
    register_provider_health_probe("getter-health", health, replace=True)
    register_metrics_collector("getter-metrics", metrics, replace=True)

    assert get_evidence_enricher("getter-evidence")() == {"safe": True}
    assert get_report_exporter("getter-export")() == b"safe"
    assert get_readiness_rule("getter-readiness")() == {"ready": True}
    assert get_provider_health_probe("getter-health")().healthy is True
    assert get_metrics_collector("getter-metrics")() is None
    with pytest.raises(AdapterNotRegistered):
        get_extension_action("missing-action")


def test_status_normalization_rejects_unrecognized_provider_status() -> None:
    assert _status(BackupStatus.COMPLETED) is BackupStatus.COMPLETED
    assert _status("failed") is BackupStatus.FAILED
    with pytest.raises(ProviderOperationError):
        _status("finished")


def test_local_filesystem_adapter_fails_closed_for_unconfigured_or_escaping_paths(tmp_path) -> None:
    adapter = LocalFilesystemStorageRecoveryAdapter(storage_root=None, restore_root=tmp_path)
    with pytest.raises(ProviderConfigurationError):
        adapter.validate_artifact(uuid.uuid4(), descriptor(), idempotency_key="verify")

    root = tmp_path / "root"
    root.mkdir()
    adapter = LocalFilesystemStorageRecoveryAdapter(storage_root=root, restore_root=tmp_path)
    with pytest.raises(ProviderOperationError):
        adapter.validate_artifact(
            uuid.uuid4(),
            descriptor(artifact_locator_ref="../escape.bin"),
            idempotency_key="verify",
        )
    with pytest.raises(ProviderOperationError):
        adapter.validate_artifact(
            uuid.uuid4(),
            descriptor(checksum_algorithm="md5"),
            idempotency_key="verify",
        )

    missing = adapter.validate_artifact(uuid.uuid4(), descriptor(), idempotency_key="verify")
    assert missing.valid is False
    assert missing.error_code == "artifact_missing"


class BadCatalogService:
    def describe_completed_artifact(self, tenant_id, backup_job_id):
        del tenant_id, backup_job_id
        return {"backup_job_id": "not-a-uuid"}


class NoCatalogCapability:
    pass


def test_backup_recovery_catalog_adapter_normalizes_provider_failures() -> None:
    adapter = BackupRecoveryCatalogAdapter(BadCatalogService())
    with pytest.raises(ProviderOperationError):
        adapter.describe_completed_artifact(uuid.uuid4(), uuid.uuid4())

    missing = BackupRecoveryCatalogAdapter(NoCatalogCapability())
    with pytest.raises(ProviderConfigurationError):
        missing.request_backup(
            uuid.uuid4(),
            uuid.uuid4(),
            backup_type=BackupType.FULL,
            scope_type=PortScopeType.TENANT,
            scope_ref="tenant",
            idempotency_key="request",
        )


class LegacyCatalogService:
    def __init__(self, storage_location: str, *, status=BackupStatus.COMPLETED, description="tenant:primary") -> None:
        self.backup_id = uuid.uuid4()
        self.schedule_id = uuid.uuid4()
        self.storage_location = storage_location
        self.status = status
        self.description = description

    def create_backup_job(self, **kwargs):
        self.created_kwargs = kwargs
        return SimpleNamespace(id=self.backup_id, status=BackupStatus.PENDING)

    def get_backup_job(self, backup_job_id, tenant_id):
        del backup_job_id, tenant_id
        return SimpleNamespace(
            id=self.backup_id,
            status=self.status,
            end_time=timezone.now(),
            completed_at=timezone.now(),
            error_code="",
            description=self.description,
            storage_location=self.storage_location,
            backup_type=BackupType.FULL,
        )

    def get_backup_schedule(self, backup_schedule_id, tenant_id):
        del backup_schedule_id, tenant_id
        return SimpleNamespace(
            id=self.schedule_id,
            is_active=True,
            backup_type=BackupType.INCREMENTAL,
            frequency="daily",
        )


def test_legacy_backup_catalog_adapter_normalizes_receipts_status_artifacts_and_schedules(tmp_path, settings) -> None:
    storage_root = tmp_path / "legacy-storage"
    storage_root.mkdir()
    artifact = storage_root / "tenant" / "artifact.bin"
    artifact.parent.mkdir()
    payload = b"legacy catalog payload"
    artifact.write_bytes(payload)
    settings.BDR_LOCAL_STORAGE_ROOT = str(storage_root)

    service = LegacyCatalogService("tenant/artifact.bin")
    adapter = BackupRecoveryCatalogAdapter(service)
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    receipt = adapter.request_backup(
        tenant_id,
        actor_id,
        backup_type=BackupType.FULL,
        scope_type=PortScopeType.TENANT,
        scope_ref=" primary ",
        idempotency_key="legacy-request",
    )
    status_snapshot = adapter.get_backup_status(tenant_id, service.backup_id)
    descriptor_result = adapter.describe_completed_artifact(tenant_id, service.backup_id)
    schedule = adapter.validate_schedule(tenant_id, service.schedule_id)

    assert receipt.backup_job_id == service.backup_id
    assert service.created_kwargs["description"] == "tenant:primary"
    assert status_snapshot.status == BackupStatus.COMPLETED
    assert descriptor_result.size_bytes == len(payload)
    assert descriptor_result.checksum_digest == hashlib.sha256(payload).hexdigest()
    assert descriptor_result.artifact_locator_ref == "tenant/artifact.bin"
    assert schedule.active is True
    assert schedule.backup_type == BackupType.INCREMENTAL


def test_legacy_backup_catalog_adapter_fails_closed_for_unprovable_artifacts(tmp_path, settings) -> None:
    storage_root = tmp_path / "legacy-storage"
    storage_root.mkdir()
    artifact = storage_root / "tenant" / "artifact.bin"
    artifact.parent.mkdir()
    artifact.write_bytes(b"payload")
    settings.BDR_LOCAL_STORAGE_ROOT = str(storage_root)

    incomplete = BackupRecoveryCatalogAdapter(LegacyCatalogService("tenant/artifact.bin", status=BackupStatus.RUNNING))
    with pytest.raises(ProviderOperationError, match="not provider-confirmed complete"):
        incomplete.describe_completed_artifact(uuid.uuid4(), uuid.uuid4())

    bad_scope = BackupRecoveryCatalogAdapter(LegacyCatalogService("tenant/artifact.bin", description="bad-scope"))
    with pytest.raises(ProviderOperationError, match="scope provenance"):
        bad_scope.describe_completed_artifact(uuid.uuid4(), uuid.uuid4())

    escaping = BackupRecoveryCatalogAdapter(LegacyCatalogService("../artifact.bin"))
    with pytest.raises(ProviderOperationError, match="confined"):
        escaping.describe_completed_artifact(uuid.uuid4(), uuid.uuid4())

    settings.BDR_LOCAL_STORAGE_ROOT = ""
    with pytest.raises(ProviderConfigurationError, match="storage root"):
        BackupRecoveryCatalogAdapter(LegacyCatalogService("tenant/artifact.bin")).describe_completed_artifact(
            uuid.uuid4(), uuid.uuid4()
        )


def test_local_filesystem_adapter_validates_and_restores_with_bound_policy(tmp_path) -> None:
    storage_root = tmp_path / "storage"
    restore_root = tmp_path / "restore"
    storage_root.mkdir()
    restore_root.mkdir()
    artifact = storage_root / "artifact.bin"
    payload = b"tenant backup payload"
    artifact.write_bytes(payload)
    checksum = hashlib.sha256(payload).hexdigest()
    adapter = LocalFilesystemStorageRecoveryAdapter(storage_root=storage_root, restore_root=restore_root)
    artifact_descriptor = descriptor(size_bytes=len(payload), checksum_digest=checksum)
    target = RestoreTarget(
        environment=RestoreEnvironment.ISOLATED,
        target_ref="tenant-a/restored.bin",
        mode=RestoreMode.FULL,
    )
    policy = ResiliencePolicy(
        timeout_seconds=1.0,
        max_attempts=1,
        initial_backoff_seconds=0.01,
        max_backoff_seconds=0.01,
        jitter_seconds=0.01,
        circuit_failure_threshold=2,
        circuit_reset_seconds=1.0,
        checksum_chunk_bytes=4,
        local_filesystem_restore_modes=frozenset({"full"}),
    )

    token = _active_policy.set(policy)
    try:
        validation = adapter.validate_artifact(uuid.uuid4(), artifact_descriptor, idempotency_key="validate")
        preflight = adapter.validate_restore_target(
            uuid.uuid4(), artifact_descriptor, target, idempotency_key="preflight"
        )
        receipt = adapter.restore(uuid.uuid4(), artifact_descriptor, target, idempotency_key="restore")
        second_receipt = adapter.restore(uuid.uuid4(), artifact_descriptor, target, idempotency_key="restore")
        verification = adapter.verify_restore(uuid.uuid4(), receipt, idempotency_key="verify")
        compensation = adapter.compensate_restore(uuid.uuid4(), receipt, idempotency_key="compensate")
        absent_compensation = adapter.compensate_restore(uuid.uuid4(), receipt, idempotency_key="compensate")
    finally:
        _active_policy.reset(token)

    assert validation.valid is True
    assert validation.evidence["size_bytes"] == len(payload)
    assert preflight.capacity_valid is True
    assert preflight.compatibility_valid is True
    assert preflight.target_available is True
    assert receipt.completed is True
    assert second_receipt.evidence["checksum_digest"] == checksum
    assert verification.verified is True
    assert compensation.evidence == {"target_removed": True}
    assert absent_compensation.evidence == {"target_absent": True}


def test_local_filesystem_adapter_reports_restore_receipt_and_target_failures(tmp_path) -> None:
    storage_root = tmp_path / "storage"
    restore_root = tmp_path / "restore"
    storage_root.mkdir()
    restore_root.mkdir()
    artifact = storage_root / "artifact.bin"
    artifact.write_bytes(b"original")
    checksum = hashlib.sha256(b"original").hexdigest()
    adapter = LocalFilesystemStorageRecoveryAdapter(storage_root=storage_root, restore_root=restore_root)
    artifact_descriptor = descriptor(size_bytes=8, checksum_digest=checksum)
    target = RestoreTarget(
        environment=RestoreEnvironment.ISOLATED,
        target_ref="tenant-a/restored.bin",
        mode=RestoreMode.SELECTIVE,
    )
    disabled_policy = ResiliencePolicy(
        timeout_seconds=1.0,
        max_attempts=1,
        initial_backoff_seconds=0.01,
        max_backoff_seconds=0.01,
        jitter_seconds=0.01,
        circuit_failure_threshold=2,
        circuit_reset_seconds=1.0,
        checksum_chunk_bytes=8,
        local_filesystem_restore_modes=frozenset({"full"}),
    )

    token = _active_policy.set(disabled_policy)
    try:
        with pytest.raises(ProviderOperationError, match="disabled"):
            adapter.restore(uuid.uuid4(), artifact_descriptor, target, idempotency_key="restore")
    finally:
        _active_policy.reset(token)

    incomplete = RestoreProviderReceipt(operation_id="op", accepted=True, completed=False, evidence={})
    invalid = RestoreProviderReceipt(operation_id="op", accepted=True, completed=True, evidence={})
    assert (
        adapter.verify_restore(uuid.uuid4(), incomplete, idempotency_key="verify").error_code == "restore_not_completed"
    )
    assert (
        adapter.verify_restore(uuid.uuid4(), invalid, idempotency_key="verify").error_code == "invalid_provider_receipt"
    )
    with pytest.raises(ProviderOperationError, match="lacks compensation evidence"):
        adapter.compensate_restore(uuid.uuid4(), invalid, idempotency_key="compensate")

    destination = restore_root / "tenant-a" / "restored.bin"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"different")
    receipt = RestoreProviderReceipt(
        operation_id="op",
        accepted=True,
        completed=True,
        evidence={"target_ref": "tenant-a/restored.bin", "checksum_digest": checksum},
    )
    assert (
        adapter.verify_restore(uuid.uuid4(), receipt, idempotency_key="verify").error_code
        == "restore_checksum_mismatch"
    )
    with pytest.raises(ProviderOperationError, match="changed after provider operation"):
        adapter.compensate_restore(uuid.uuid4(), receipt, idempotency_key="compensate")


def test_local_filesystem_health_reports_unconfigured_available_and_circuit_open(tmp_path) -> None:
    assert LocalFilesystemStorageRecoveryAdapter().health().healthy is False

    storage_root = tmp_path / "storage"
    restore_root = tmp_path / "restore"
    storage_root.mkdir()
    restore_root.mkdir()
    healthy = LocalFilesystemStorageRecoveryAdapter(storage_root=storage_root, restore_root=restore_root).health()
    assert healthy.healthy is True
    assert healthy.details["adapter"] == LocalFilesystemStorageRecoveryAdapter.key

    class OpenBreaker:
        @property
        def state(self):
            return SimpleNamespace(value="open")

        def call(self, operation):
            del operation
            from src.core.resilience.circuit_breaker import CircuitBreakerError

            raise CircuitBreakerError("local-filesystem", 0.0)

    open_result = LocalFilesystemStorageRecoveryAdapter(
        storage_root=storage_root,
        restore_root=restore_root,
        breaker=OpenBreaker(),
    ).health()
    assert open_result.healthy is False
    assert open_result.details == {"adapter": LocalFilesystemStorageRecoveryAdapter.key, "circuit_state": "open"}
