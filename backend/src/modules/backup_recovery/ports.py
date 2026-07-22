"""Provider-neutral contracts for backup capture and catalog consumers."""

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
class BackupCaptureRequest:
    operation_id: UUID
    tenant_id: UUID
    backup_job_id: UUID
    backup_type: BackupType
    scope_type: ScopeType
    scope_ref: str
    locator_prefix_ref: str
    encryption_key_ref: str = ""


@dataclass(frozen=True, slots=True)
class BackupCaptureReceipt:
    operation_id: str
    accepted: bool
    completed: bool
    artifact_locator_ref: str
    size_bytes: int
    checksum_algorithm: str
    checksum_digest: str
    provider_acknowledgement: str
    data_cutoff_at: datetime
    captured_at: datetime
    evidence: Mapping[str, object] = field(default_factory=dict)
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class ProviderCancellationReceipt:
    operation_id: str
    acknowledged: bool
    evidence: Mapping[str, object] = field(default_factory=dict)
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class ArtifactVerificationReceipt:
    operation_id: str
    checksum_matches: bool
    artifact_available: bool
    encryption_metadata_valid: bool
    provider_acknowledged: bool
    evidence: Mapping[str, object] = field(default_factory=dict)
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class ProviderPurgeReceipt:
    operation_id: str
    acknowledged: bool
    purged_at: datetime | None
    evidence: Mapping[str, object] = field(default_factory=dict)
    error_code: str = ""


@runtime_checkable
class BackupCatalogPort(Protocol):
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

    def describe_completed_artifact(self, tenant_id: UUID, backup_job_id: UUID) -> BackupArtifactDescriptor: ...

    def validate_schedule(self, tenant_id: UUID, backup_schedule_id: UUID) -> BackupScheduleSnapshot: ...


@runtime_checkable
class BackupCaptureAdapter(Protocol):
    def capture(self, request: BackupCaptureRequest) -> BackupCaptureReceipt: ...

    def cancel(self, operation_id: str, *, idempotency_key: str) -> ProviderCancellationReceipt: ...

    def verify(self, descriptor: BackupArtifactDescriptor, *, idempotency_key: str) -> ArtifactVerificationReceipt: ...

    def purge(self, descriptor: BackupArtifactDescriptor, *, idempotency_key: str) -> ProviderPurgeReceipt: ...

    def health(self) -> HealthCheckResult: ...


__all__ = [
    "ArtifactVerificationReceipt",
    "BackupArtifactDescriptor",
    "BackupCaptureAdapter",
    "BackupCaptureReceipt",
    "BackupCaptureRequest",
    "BackupCatalogPort",
    "BackupRequestReceipt",
    "BackupScheduleSnapshot",
    "BackupStatus",
    "BackupStatusSnapshot",
    "BackupType",
    "HealthCheckResult",
    "ProviderCancellationReceipt",
    "ProviderPurgeReceipt",
    "ScopeType",
]
