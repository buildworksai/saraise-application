"""Duplicate-safe provider registries and the open-source local adapter."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import threading
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Generic, TypeVar, cast
from uuid import UUID

from django.conf import settings
from django.utils import timezone

from src.core.health import HealthCheckResult
from src.core.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerError

from .ports import (
    ArtifactValidationResult,
    BackupArtifactDescriptor,
    BackupCatalogPort,
    BackupRequestReceipt,
    BackupScheduleSnapshot,
    BackupStatus,
    BackupStatusSnapshot,
    BackupType,
    RestoreMode,
    RestoreProviderReceipt,
    RestoreTarget,
    RestoreVerificationResult,
    ScopeType,
    StorageRecoveryAdapter,
)

T = TypeVar("T")


class AdapterRegistryError(RuntimeError):
    """Base error for extension registration and lookup."""


class AdapterAlreadyRegistered(AdapterRegistryError):
    """Raised when import order would otherwise replace an adapter."""


class AdapterNotRegistered(AdapterRegistryError):
    """Raised when a required integration is unavailable."""


class ProviderConfigurationError(AdapterRegistryError):
    """Raised when a provider cannot operate with its current configuration."""


class ProviderOperationError(AdapterRegistryError):
    """Raised for a stable, sanitized provider failure."""


class _Registry(Generic[T]):
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._entries: dict[str, T] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _key(key: str) -> str:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("registration key must be a non-empty string")
        normalized = key.strip().lower()
        if len(normalized) > 120:
            raise ValueError("registration key must not exceed 120 characters")
        return normalized

    def register(self, key: str, value: T, *, replace: bool = False) -> T:
        normalized = self._key(key)
        with self._lock:
            if normalized in self._entries and not replace:
                raise AdapterAlreadyRegistered(f"{self.kind} {normalized!r} is already registered")
            self._entries[normalized] = value
        return value

    def get(self, key: str) -> T:
        normalized = self._key(key)
        with self._lock:
            try:
                return self._entries[normalized]
            except KeyError as exc:
                raise AdapterNotRegistered(f"{self.kind} {normalized!r} is not registered") from exc

    def keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._entries))

    def unregister(self, key: str) -> T | None:
        """Remove a registration for controlled tests and application shutdown."""
        with self._lock:
            return self._entries.pop(self._key(key), None)


_backup_catalogs: _Registry[BackupCatalogPort] = _Registry("backup catalog")
_storage_adapters: _Registry[StorageRecoveryAdapter] = _Registry("storage adapter")
_extension_actions: _Registry[Callable[..., object]] = _Registry("extension action")
_evidence_enrichers: _Registry[Callable[..., Mapping[str, object]]] = _Registry("evidence enricher")
_report_exporters: _Registry[Callable[..., bytes]] = _Registry("report exporter")
_readiness_rules: _Registry[Callable[..., object]] = _Registry("readiness rule")
_provider_health_probes: _Registry[Callable[[], HealthCheckResult]] = _Registry("provider health probe")
_metrics_collectors: _Registry[Callable[[], None]] = _Registry("metrics collector")


def register_backup_catalog(
    key: str,
    adapter: BackupCatalogPort,
    *,
    replace: bool = False,
) -> BackupCatalogPort:
    if not isinstance(adapter, BackupCatalogPort):
        raise TypeError("adapter must implement BackupCatalogPort")
    return _backup_catalogs.register(key, adapter, replace=replace)


def get_backup_catalog(key: str = "default") -> BackupCatalogPort:
    return _backup_catalogs.get(key)


def register_storage_adapter(
    key: str,
    adapter: StorageRecoveryAdapter,
    *,
    replace: bool = False,
) -> StorageRecoveryAdapter:
    if not isinstance(adapter, StorageRecoveryAdapter):
        raise TypeError("adapter must implement StorageRecoveryAdapter")
    return _storage_adapters.register(key, adapter, replace=replace)


def get_storage_adapter(key: str) -> StorageRecoveryAdapter:
    return _storage_adapters.get(key)


def list_storage_adapters() -> tuple[str, ...]:
    return _storage_adapters.keys()


def unregister_backup_catalog(key: str) -> BackupCatalogPort | None:
    return _backup_catalogs.unregister(key)


def unregister_storage_adapter(key: str) -> StorageRecoveryAdapter | None:
    return _storage_adapters.unregister(key)


def register_extension_action(
    key: str,
    handler: Callable[..., object],
    *,
    replace: bool = False,
) -> Callable[..., object]:
    if not callable(handler):
        raise TypeError("extension action must be callable")
    return _extension_actions.register(key, handler, replace=replace)


def get_extension_action(key: str) -> Callable[..., object]:
    return _extension_actions.get(key)


def _register_callable(
    registry: _Registry[T],
    key: str,
    value: T,
    *,
    replace: bool,
) -> T:
    if not callable(value):
        raise TypeError("extension must be callable")
    return registry.register(key, value, replace=replace)


def register_evidence_enricher(key: str, value: T, *, replace: bool = False) -> T:
    return _register_callable(_evidence_enrichers, key, value, replace=replace)  # type: ignore[arg-type,return-value]


def register_report_exporter(key: str, value: T, *, replace: bool = False) -> T:
    return _register_callable(_report_exporters, key, value, replace=replace)  # type: ignore[arg-type,return-value]


def register_readiness_rule(key: str, value: T, *, replace: bool = False) -> T:
    return _register_callable(_readiness_rules, key, value, replace=replace)  # type: ignore[arg-type,return-value]


def register_provider_health_probe(key: str, value: T, *, replace: bool = False) -> T:
    return _register_callable(  # type: ignore[arg-type,return-value]
        _provider_health_probes, key, value, replace=replace
    )


def register_metrics_collector(key: str, value: T, *, replace: bool = False) -> T:
    return _register_callable(_metrics_collectors, key, value, replace=replace)  # type: ignore[arg-type,return-value]


def get_evidence_enricher(key: str) -> Callable[..., Mapping[str, object]]:
    return _evidence_enrichers.get(key)


def get_report_exporter(key: str) -> Callable[..., bytes]:
    return _report_exporters.get(key)


def get_readiness_rule(key: str) -> Callable[..., object]:
    return _readiness_rules.get(key)


def get_provider_health_probe(key: str) -> Callable[[], HealthCheckResult]:
    return _provider_health_probes.get(key)


def get_metrics_collector(key: str) -> Callable[[], None]:
    return _metrics_collectors.get(key)


def _required_text(value: object, field: str, *, maximum: int = 255) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderOperationError(f"{field} is unavailable")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ProviderOperationError(f"{field} exceeds the supported length")
    return normalized


def _uuid(value: object, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProviderOperationError(f"{field} is not a valid UUID") from exc


def _status(value: object) -> BackupStatus:
    if isinstance(value, BackupStatus):
        return value
    try:
        return BackupStatus(str(value))
    except ValueError as exc:
        raise ProviderOperationError("backup catalog returned an unsupported status") from exc


class BackupRecoveryCatalogAdapter:
    """Normalize ``backup_recovery`` service results without importing its ORM.

    A service instance can be injected by paid modules and tests.  Importing the
    legacy service is intentionally lazy so this module never creates a reverse
    model dependency during Django application loading.
    """

    def __init__(self, service: object | None = None) -> None:
        self._service = service

    def _get_service(self) -> object:
        if self._service is None:
            from src.modules.backup_recovery.services import BackupRecoveryService

            self._service = BackupRecoveryService()
        return self._service

    def request_backup(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        *,
        backup_type: BackupType,
        scope_type: ScopeType,
        scope_ref: str,
        idempotency_key: str,
    ) -> BackupRequestReceipt:
        service = self._get_service()
        scope = _required_text(scope_ref, "scope_ref")
        key = _required_text(idempotency_key, "idempotency_key")
        native = getattr(service, "request_backup", None)
        if callable(native):
            raw = native(
                tenant_id,
                actor_id,
                backup_type=backup_type,
                scope_type=scope_type,
                scope_ref=scope,
                idempotency_key=key,
            )
        else:
            create = getattr(service, "create_backup_job", None)
            if not callable(create):
                raise ProviderConfigurationError("backup catalog request capability is unavailable")
            raw = create(
                tenant_id=str(tenant_id),
                backup_type=backup_type.value,
                description=f"{scope_type.value}:{scope}",
                created_by=str(actor_id),
            )
        if isinstance(raw, BackupRequestReceipt):
            return raw
        return BackupRequestReceipt(
            backup_job_id=_uuid(getattr(raw, "id", None), "backup_job_id"),
            status=_status(getattr(raw, "status", None)),
            idempotency_key=key,
        )

    def get_backup_status(self, tenant_id: UUID, backup_job_id: UUID) -> BackupStatusSnapshot:
        service = self._get_service()
        native = getattr(service, "get_backup_status", None)
        if callable(native):
            raw = native(tenant_id, backup_job_id)
        else:
            get_job = getattr(service, "get_backup_job", None)
            if not callable(get_job):
                raise ProviderConfigurationError("backup catalog status capability is unavailable")
            raw = get_job(str(backup_job_id), str(tenant_id))
        if raw is None:
            raise ProviderOperationError("backup job was not found")
        if isinstance(raw, BackupStatusSnapshot):
            return raw
        return BackupStatusSnapshot(
            backup_job_id=_uuid(getattr(raw, "id", None), "backup_job_id"),
            status=_status(getattr(raw, "status", None)),
            completed_at=getattr(raw, "end_time", getattr(raw, "completed_at", None)),
            error_code=(
                _required_text(getattr(raw, "error_code", "") or "none", "error_code", maximum=64)
                if getattr(raw, "error_code", "")
                else ""
            ),
        )

    def describe_completed_artifact(
        self,
        tenant_id: UUID,
        backup_job_id: UUID,
    ) -> BackupArtifactDescriptor:
        service = self._get_service()
        native = getattr(service, "describe_completed_artifact", None)
        if callable(native):
            raw = native(tenant_id, backup_job_id)
        else:
            return self._describe_legacy_artifact(service, tenant_id, backup_job_id)
        if isinstance(raw, BackupArtifactDescriptor):
            return raw
        if not isinstance(raw, Mapping):
            raise ProviderOperationError("backup catalog returned an invalid artifact descriptor")
        try:
            return BackupArtifactDescriptor(
                backup_job_id=_uuid(raw["backup_job_id"], "backup_job_id"),
                backup_archive_id=(
                    _uuid(raw["backup_archive_id"], "backup_archive_id") if raw.get("backup_archive_id") else None
                ),
                adapter_key=_required_text(raw.get("adapter_key"), "adapter_key", maximum=64),
                artifact_locator_ref=_required_text(raw.get("artifact_locator_ref"), "artifact_locator_ref"),
                encryption_key_ref=str(raw["encryption_key_ref"]) if raw.get("encryption_key_ref") else None,
                scope_type=(
                    raw["scope_type"] if isinstance(raw["scope_type"], ScopeType) else ScopeType(str(raw["scope_type"]))
                ),
                scope_ref=_required_text(raw.get("scope_ref"), "scope_ref"),
                backup_type=(
                    raw["backup_type"]
                    if isinstance(raw["backup_type"], BackupType)
                    else BackupType(str(raw["backup_type"]))
                ),
                data_cutoff_at=cast(datetime, raw["data_cutoff_at"]),
                captured_at=cast(datetime, raw["captured_at"]),
                expires_at=cast(datetime | None, raw.get("expires_at")),
                size_bytes=cast(int | None, raw.get("size_bytes")),
                checksum_algorithm=_required_text(raw.get("checksum_algorithm"), "checksum_algorithm", maximum=16),
                checksum_digest=_required_text(raw.get("checksum_digest"), "checksum_digest", maximum=64),
                provider_acknowledgement=_required_text(
                    raw.get("provider_acknowledgement"), "provider_acknowledgement"
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderOperationError("backup catalog returned an invalid artifact descriptor") from exc

    @staticmethod
    def _describe_legacy_artifact(
        service: object,
        tenant_id: UUID,
        backup_job_id: UUID,
    ) -> BackupArtifactDescriptor:
        """Normalize the legacy service only when every required fact is provable."""
        get_job = getattr(service, "get_backup_job", None)
        if not callable(get_job):
            raise ProviderConfigurationError("backup catalog artifact capability is unavailable")
        job = get_job(str(backup_job_id), str(tenant_id))
        if job is None:
            raise ProviderOperationError("backup job was not found")
        if _status(getattr(job, "status", None)) is not BackupStatus.COMPLETED:
            raise ProviderOperationError("backup artifact is not provider-confirmed complete")

        description = _required_text(getattr(job, "description", None), "backup scope")
        if ":" not in description:
            raise ProviderOperationError("backup scope provenance is unavailable")
        raw_scope_type, raw_scope_ref = description.split(":", 1)
        try:
            scope_type = ScopeType(raw_scope_type)
        except ValueError as exc:
            raise ProviderOperationError("backup scope provenance is invalid") from exc
        scope_ref = _required_text(raw_scope_ref, "scope_ref")

        locator_ref = _required_text(getattr(job, "storage_location", None), "artifact locator")
        storage_root_value = getattr(settings, "BDR_LOCAL_STORAGE_ROOT", None)
        if not storage_root_value:
            raise ProviderConfigurationError("local filesystem storage root is not configured")
        storage_root = Path(storage_root_value).expanduser()
        artifact_path = LocalFilesystemStorageRecoveryAdapter._confined(
            storage_root,
            locator_ref,
            "artifact locator",
        )
        if not artifact_path.is_file():
            raise ProviderOperationError("completed backup artifact is unavailable")
        checksum, size = LocalFilesystemStorageRecoveryAdapter._checksum(artifact_path)
        reported_size = getattr(job, "backup_size_bytes", None)
        if reported_size is not None and reported_size != size:
            raise ProviderOperationError("completed backup artifact size does not match catalog evidence")

        captured_at = getattr(job, "end_time", None)
        if not isinstance(captured_at, datetime):
            raise ProviderOperationError("backup completion timestamp is unavailable")
        raw_backup_type = getattr(job, "backup_type", None)
        try:
            backup_type = raw_backup_type if isinstance(raw_backup_type, BackupType) else BackupType(raw_backup_type)
        except (TypeError, ValueError) as exc:
            raise ProviderOperationError("backup type provenance is invalid") from exc
        return BackupArtifactDescriptor(
            backup_job_id=_uuid(getattr(job, "id", None), "backup_job_id"),
            backup_archive_id=None,
            adapter_key=LocalFilesystemStorageRecoveryAdapter.key,
            artifact_locator_ref=Path(locator_ref).as_posix(),
            encryption_key_ref=None,
            scope_type=scope_type,
            scope_ref=scope_ref,
            backup_type=backup_type,
            data_cutoff_at=captured_at,
            captured_at=captured_at,
            expires_at=None,
            size_bytes=size,
            checksum_algorithm="sha256",
            checksum_digest=checksum,
            provider_acknowledgement=f"completed:{backup_job_id}:{checksum}",
        )

    def validate_schedule(self, tenant_id: UUID, backup_schedule_id: UUID) -> BackupScheduleSnapshot:
        service = self._get_service()
        native = getattr(service, "validate_schedule", None)
        if callable(native):
            raw = native(tenant_id, backup_schedule_id)
        else:
            get_schedule = getattr(service, "get_backup_schedule", None)
            if not callable(get_schedule):
                raise ProviderConfigurationError("backup schedule capability is unavailable")
            raw = get_schedule(str(backup_schedule_id), str(tenant_id))
        if raw is None:
            raise ProviderOperationError("backup schedule was not found")
        if isinstance(raw, BackupScheduleSnapshot):
            return raw
        return BackupScheduleSnapshot(
            backup_schedule_id=_uuid(getattr(raw, "id", None), "backup_schedule_id"),
            active=bool(getattr(raw, "is_active", False)),
            backup_type=(
                getattr(raw, "backup_type")
                if isinstance(getattr(raw, "backup_type", None), BackupType)
                else BackupType(str(getattr(raw, "backup_type", "")))
            ),
            frequency=_required_text(getattr(raw, "frequency", None), "frequency", maximum=64),
        )


class LocalFilesystemStorageRecoveryAdapter:
    """Constrained OSS provider with streaming checksums and atomic restores."""

    key = "local-filesystem"

    def __init__(
        self,
        *,
        storage_root: str | Path | None = None,
        restore_root: str | Path | None = None,
        breaker: CircuitBreaker[object] | None = None,
    ) -> None:
        configured_storage = storage_root or getattr(settings, "BDR_LOCAL_STORAGE_ROOT", None)
        configured_restore = restore_root or getattr(settings, "BDR_LOCAL_RESTORE_ROOT", None)
        self._storage_root = Path(configured_storage).expanduser() if configured_storage else None
        self._restore_root = Path(configured_restore).expanduser() if configured_restore else None
        self._breaker = breaker or CircuitBreaker("bdr.local-filesystem", failure_threshold=3, reset_timeout=30)

    @property
    def circuit_state(self) -> str:
        return self._breaker.state.value

    @staticmethod
    def _confined(root: Path | None, reference: str, field: str) -> Path:
        if root is None:
            raise ProviderConfigurationError(f"local filesystem {field} root is not configured")
        ref = _required_text(reference, field)
        candidate_ref = Path(ref)
        if candidate_ref.is_absolute() or ".." in candidate_ref.parts:
            raise ProviderOperationError(f"{field} must be a confined relative reference")
        try:
            resolved_root = root.resolve(strict=True)
        except OSError as exc:
            raise ProviderConfigurationError(f"local filesystem {field} root is unavailable") from exc
        try:
            candidate = (resolved_root / candidate_ref).resolve(strict=False)
        except OSError as exc:
            raise ProviderOperationError(f"{field} could not be resolved") from exc
        if candidate != resolved_root and resolved_root not in candidate.parents:
            raise ProviderOperationError(f"{field} escapes its configured root")
        return candidate

    @staticmethod
    def _checksum(path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
        except OSError as exc:
            raise ProviderOperationError("local filesystem artifact could not be read") from exc
        return digest.hexdigest(), size

    def _artifact(self, descriptor: BackupArtifactDescriptor) -> Path:
        if descriptor.adapter_key != self.key:
            raise ProviderOperationError("artifact belongs to a different storage adapter")
        if descriptor.checksum_algorithm != "sha256":
            raise ProviderOperationError("unsupported checksum algorithm")
        return self._confined(self._storage_root, descriptor.artifact_locator_ref, "artifact locator")

    def validate_artifact(
        self,
        tenant_id: UUID,
        descriptor: BackupArtifactDescriptor,
        *,
        idempotency_key: str,
    ) -> ArtifactValidationResult:
        del tenant_id
        _required_text(idempotency_key, "idempotency_key")

        def operation() -> ArtifactValidationResult:
            path = self._artifact(descriptor)
            if not path.is_file():
                return ArtifactValidationResult(
                    valid=False,
                    checksum_matches=False,
                    artifact_available=False,
                    encryption_metadata_valid=descriptor.encryption_key_ref is None,
                    provider_acknowledged=False,
                    evidence={"algorithm": "sha256"},
                    error_code="artifact_missing",
                )
            checksum, actual_size = self._checksum(path)
            checksum_matches = checksum == descriptor.checksum_digest
            size_matches = descriptor.size_bytes is None or descriptor.size_bytes == actual_size
            encryption_valid = descriptor.encryption_key_ref is None or bool(descriptor.encryption_key_ref.strip())
            valid = checksum_matches and size_matches and encryption_valid and bool(descriptor.provider_acknowledgement)
            return ArtifactValidationResult(
                valid=valid,
                checksum_matches=checksum_matches,
                artifact_available=True,
                encryption_metadata_valid=encryption_valid,
                provider_acknowledged=bool(descriptor.provider_acknowledgement),
                evidence={"algorithm": "sha256", "size_bytes": actual_size},
                error_code="" if valid else "artifact_integrity_failed",
            )

        return cast(ArtifactValidationResult, self._breaker.call(operation))

    def restore(
        self,
        tenant_id: UUID,
        descriptor: BackupArtifactDescriptor,
        target: RestoreTarget,
        *,
        idempotency_key: str,
    ) -> RestoreProviderReceipt:
        del tenant_id
        key = _required_text(idempotency_key, "idempotency_key")
        if target.mode is not RestoreMode.FULL or target.selected_components:
            raise ProviderOperationError("local filesystem adapter supports full restores only")

        def operation() -> RestoreProviderReceipt:
            source = self._artifact(descriptor)
            if not source.is_file():
                raise ProviderOperationError("artifact is unavailable")
            source_checksum, source_size = self._checksum(source)
            if source_checksum != descriptor.checksum_digest:
                raise ProviderOperationError("artifact checksum mismatch")
            destination = self._confined(self._restore_root, target.target_ref, "restore target")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if not destination.is_file():
                    raise ProviderOperationError("restore target is not a regular file")
                existing_checksum, existing_size = self._checksum(destination)
                if existing_checksum != source_checksum:
                    raise ProviderOperationError("restore target already contains different data")
                return RestoreProviderReceipt(
                    operation_id=hashlib.sha256(key.encode("utf-8")).hexdigest(),
                    accepted=True,
                    completed=True,
                    evidence={
                        "target_ref": target.target_ref,
                        "checksum_digest": existing_checksum,
                        "size_bytes": existing_size,
                    },
                )
            descriptor_fd, temporary_name = tempfile.mkstemp(prefix=".bdr-restore-", dir=destination.parent)
            os.close(descriptor_fd)
            temporary = Path(temporary_name)
            try:
                shutil.copyfile(source, temporary)
                restored_checksum, restored_size = self._checksum(temporary)
                if restored_checksum != source_checksum:
                    raise ProviderOperationError("restored artifact checksum mismatch")
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
            return RestoreProviderReceipt(
                operation_id=hashlib.sha256(key.encode("utf-8")).hexdigest(),
                accepted=True,
                completed=True,
                evidence={
                    "target_ref": target.target_ref,
                    "checksum_digest": source_checksum,
                    "size_bytes": source_size,
                },
            )

        return cast(RestoreProviderReceipt, self._breaker.call(operation))

    def verify_restore(
        self,
        tenant_id: UUID,
        receipt: RestoreProviderReceipt,
        *,
        idempotency_key: str,
    ) -> RestoreVerificationResult:
        del tenant_id
        _required_text(idempotency_key, "idempotency_key")
        if not receipt.accepted or not receipt.completed:
            return RestoreVerificationResult(verified=False, error_code="restore_not_completed")
        target_ref = receipt.evidence.get("target_ref")
        expected_checksum = receipt.evidence.get("checksum_digest")
        if not isinstance(target_ref, str) or not isinstance(expected_checksum, str):
            return RestoreVerificationResult(verified=False, error_code="invalid_provider_receipt")

        def operation() -> RestoreVerificationResult:
            destination = self._confined(self._restore_root, target_ref, "restore target")
            if not destination.is_file():
                return RestoreVerificationResult(verified=False, error_code="restore_missing")
            actual_checksum, size = self._checksum(destination)
            verified = actual_checksum == expected_checksum
            return RestoreVerificationResult(
                verified=verified,
                evidence={"algorithm": "sha256", "size_bytes": size},
                error_code="" if verified else "restore_checksum_mismatch",
            )

        return cast(RestoreVerificationResult, self._breaker.call(operation))

    def health(self) -> HealthCheckResult:
        checked_at = timezone.now()

        def operation() -> HealthCheckResult:
            if self._storage_root is None or self._restore_root is None:
                return HealthCheckResult(
                    healthy=False,
                    message="local filesystem provider is not configured",
                    checked_at=checked_at,
                )
            try:
                storage_root = self._storage_root.resolve(strict=True)
                restore_root = self._restore_root.resolve(strict=True)
            except OSError:
                return HealthCheckResult(False, "local filesystem provider root is unavailable", checked_at)
            healthy = (
                storage_root.is_dir()
                and restore_root.is_dir()
                and os.access(storage_root, os.R_OK)
                and os.access(restore_root, os.R_OK | os.W_OK)
            )
            return HealthCheckResult(
                healthy=healthy,
                message="" if healthy else "local filesystem provider permissions are unavailable",
                checked_at=checked_at,
                details={"adapter": self.key, "circuit_state": self.circuit_state},
            )

        try:
            return cast(HealthCheckResult, self._breaker.call(operation))
        except CircuitBreakerError:
            return HealthCheckResult(
                healthy=False,
                message="storage provider circuit is open",
                checked_at=checked_at,
                details={"adapter": self.key, "circuit_state": "open"},
            )
        except Exception:
            return HealthCheckResult(
                healthy=False,
                message="storage provider probe failed",
                checked_at=checked_at,
                details={"adapter": self.key},
            )


__all__ = [
    "AdapterAlreadyRegistered",
    "AdapterNotRegistered",
    "AdapterRegistryError",
    "BackupRecoveryCatalogAdapter",
    "LocalFilesystemStorageRecoveryAdapter",
    "ProviderConfigurationError",
    "ProviderOperationError",
    "get_backup_catalog",
    "get_evidence_enricher",
    "get_extension_action",
    "get_metrics_collector",
    "get_provider_health_probe",
    "get_readiness_rule",
    "get_report_exporter",
    "get_storage_adapter",
    "list_storage_adapters",
    "register_backup_catalog",
    "register_evidence_enricher",
    "register_extension_action",
    "register_metrics_collector",
    "register_provider_health_probe",
    "register_readiness_rule",
    "register_report_exporter",
    "register_storage_adapter",
    "unregister_backup_catalog",
    "unregister_storage_adapter",
]
