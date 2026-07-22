"""Stable, provider-neutral contracts for disaster-recovery integrations.

The domain deliberately exchanges immutable value objects across module and
provider boundaries.  ORM objects, credentials, and unvalidated provider
payloads are not part of this public extension surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Mapping, Protocol, runtime_checkable
from uuid import UUID

from src.core.health import HealthCheckResult


class BackupType(str, Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    DIFFERENTIAL = "differential"


class ScopeType(str, Enum):
    TENANT = "tenant"
    MODULE = "module"
    DATABASE = "database"
    FILES = "files"


class BackupStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RestoreEnvironment(str, Enum):
    ISOLATED = "isolated"
    STANDBY = "standby"
    PRODUCTION = "production"


class RestoreMode(str, Enum):
    FULL = "full"
    SELECTIVE = "selective"


@dataclass(frozen=True, slots=True)
class BackupRequestReceipt:
    backup_job_id: UUID
    status: BackupStatus
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class BackupStatusSnapshot:
    backup_job_id: UUID
    status: BackupStatus
    completed_at: datetime | None = None
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class BackupArtifactDescriptor:
    backup_job_id: UUID
    backup_archive_id: UUID | None
    adapter_key: str
    artifact_locator_ref: str
    encryption_key_ref: str | None
    scope_type: ScopeType
    scope_ref: str
    backup_type: BackupType
    data_cutoff_at: datetime
    captured_at: datetime
    expires_at: datetime | None
    size_bytes: int | None
    checksum_algorithm: str
    checksum_digest: str
    provider_acknowledgement: str


@dataclass(frozen=True, slots=True)
class BackupScheduleSnapshot:
    backup_schedule_id: UUID
    active: bool
    backup_type: BackupType
    frequency: str


@dataclass(frozen=True, slots=True)
class ArtifactValidationResult:
    valid: bool
    checksum_matches: bool
    artifact_available: bool
    encryption_metadata_valid: bool
    provider_acknowledged: bool
    evidence: Mapping[str, object] = field(default_factory=dict)
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class RestoreTarget:
    environment: RestoreEnvironment
    target_ref: str
    mode: RestoreMode
    selected_components: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RestoreProviderReceipt:
    operation_id: str
    accepted: bool
    completed: bool
    evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RestoreVerificationResult:
    verified: bool
    evidence: Mapping[str, object] = field(default_factory=dict)
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class RestorePreflightResult:
    """Provider evidence required before a restore may mutate its target."""

    capacity_valid: bool
    compatibility_valid: bool
    target_available: bool
    evidence: Mapping[str, object] = field(default_factory=dict)
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class RestoreCompensationResult:
    """Evidence that a failed restore was idempotently compensated."""

    compensated: bool
    evidence: Mapping[str, object] = field(default_factory=dict)
    error_code: str = ""


@runtime_checkable
class BackupCatalogPort(Protocol):
    """Opaque access to backup capture and catalog ownership."""

    def request_backup(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        *,
        backup_type: BackupType,
        scope_type: ScopeType,
        scope_ref: str,
        idempotency_key: str,
    ) -> BackupRequestReceipt: ...

    def get_backup_status(self, tenant_id: UUID, backup_job_id: UUID) -> BackupStatusSnapshot: ...

    def describe_completed_artifact(
        self,
        tenant_id: UUID,
        backup_job_id: UUID,
    ) -> BackupArtifactDescriptor: ...

    def validate_schedule(
        self,
        tenant_id: UUID,
        backup_schedule_id: UUID,
    ) -> BackupScheduleSnapshot: ...


@runtime_checkable
class StorageRecoveryAdapter(Protocol):
    """Provider contract for verifying and restoring immutable artifacts."""

    def validate_artifact(
        self,
        tenant_id: UUID,
        descriptor: BackupArtifactDescriptor,
        *,
        idempotency_key: str,
    ) -> ArtifactValidationResult: ...

    def restore(
        self,
        tenant_id: UUID,
        descriptor: BackupArtifactDescriptor,
        target: RestoreTarget,
        *,
        idempotency_key: str,
    ) -> RestoreProviderReceipt: ...

    def verify_restore(
        self,
        tenant_id: UUID,
        receipt: RestoreProviderReceipt,
        *,
        idempotency_key: str,
    ) -> RestoreVerificationResult: ...

    def health(self) -> HealthCheckResult: ...


@runtime_checkable
class RestorePreflightPort(Protocol):
    """Optional provider capability; absence must surface as unavailable."""

    def validate_restore_target(
        self,
        tenant_id: UUID,
        descriptor: BackupArtifactDescriptor,
        target: RestoreTarget,
        *,
        idempotency_key: str,
    ) -> RestorePreflightResult: ...


@runtime_checkable
class RestoreCompensationPort(Protocol):
    """Optional idempotent cleanup contract for failed verification."""

    def compensate_restore(
        self,
        tenant_id: UUID,
        receipt: RestoreProviderReceipt,
        *,
        idempotency_key: str,
    ) -> RestoreCompensationResult: ...


__all__ = [
    "ArtifactValidationResult",
    "BackupArtifactDescriptor",
    "BackupCatalogPort",
    "BackupRequestReceipt",
    "BackupScheduleSnapshot",
    "BackupStatus",
    "BackupStatusSnapshot",
    "BackupType",
    "HealthCheckResult",
    "RestoreEnvironment",
    "RestoreCompensationPort",
    "RestoreCompensationResult",
    "RestoreMode",
    "RestorePreflightPort",
    "RestorePreflightResult",
    "RestoreProviderReceipt",
    "RestoreTarget",
    "RestoreVerificationResult",
    "ScopeType",
    "StorageRecoveryAdapter",
]
