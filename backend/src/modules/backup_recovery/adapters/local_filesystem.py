"""Real, provider-neutral local-filesystem backup adapter."""

from __future__ import annotations

import hashlib
import os
import tarfile
import tempfile
from pathlib import Path

from django.utils import timezone

from src.core.health import HealthCheckResult

from ..ports import (
    ArtifactVerificationReceipt,
    BackupArtifactDescriptor,
    BackupCaptureReceipt,
    BackupCaptureRequest,
    ProviderCancellationReceipt,
    ProviderPurgeReceipt,
)


class LocalFilesystemCaptureAdapter:
    """Capture files below an allowed source root into an allowed archive root."""

    adapter_key = "local-filesystem"

    def __init__(self, archive_root: str | Path, *, source_root: str | Path = "/") -> None:
        self.archive_root = Path(archive_root).expanduser().resolve()
        self.source_root = Path(source_root).expanduser().resolve()

    def capture(self, request: BackupCaptureRequest) -> BackupCaptureReceipt:
        source = self._bounded_source(request.scope_ref)
        if not source.exists():
            raise FileNotFoundError("Backup source is unavailable")
        tenant_dir = (self.archive_root / str(request.tenant_id)).resolve()
        self._require_below(tenant_dir, self.archive_root)
        tenant_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = tenant_dir / f"{request.backup_job_id}.tar.gz"
        captured_at = timezone.now()
        with tempfile.NamedTemporaryFile(dir=tenant_dir, delete=False, suffix=".partial") as handle:
            temporary = Path(handle.name)
        try:
            with tarfile.open(temporary, mode="w:gz") as archive:
                archive.add(source, arcname=source.name, recursive=True)
            checksum = _sha256(temporary)
            size = temporary.stat().st_size
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        acknowledgement = f"local:{request.operation_id}:{destination.stat().st_mtime_ns}"
        return BackupCaptureReceipt(
            operation_id=str(request.operation_id),
            accepted=True,
            completed=True,
            artifact_locator_ref=str(destination),
            size_bytes=size,
            checksum_algorithm="sha256",
            checksum_digest=checksum,
            provider_acknowledgement=acknowledgement,
            data_cutoff_at=captured_at,
            captured_at=captured_at,
            evidence={"bytes_written": size, "atomic_commit": True},
        )

    def cancel(self, operation_id: str, *, idempotency_key: str) -> ProviderCancellationReceipt:
        del idempotency_key
        return ProviderCancellationReceipt(
            operation_id=operation_id,
            acknowledged=False,
            error_code="OPERATION_NOT_CANCELLABLE",
            evidence={"adapter": self.adapter_key},
        )

    def verify(self, descriptor: BackupArtifactDescriptor, *, idempotency_key: str) -> ArtifactVerificationReceipt:
        path = self._bounded_archive(descriptor.artifact_locator_ref)
        available = path.is_file()
        actual = _sha256(path) if available else ""
        checksum_matches = available and actual == descriptor.checksum_digest
        return ArtifactVerificationReceipt(
            operation_id=idempotency_key,
            checksum_matches=checksum_matches,
            artifact_available=available,
            encryption_metadata_valid=(not descriptor.encryption_key_ref)
            or bool(descriptor.encryption_key_ref.strip()),
            provider_acknowledged=bool(descriptor.provider_acknowledgement),
            evidence={"algorithm": "sha256", "size_bytes": path.stat().st_size if available else 0},
            error_code="" if checksum_matches else "CHECKSUM_MISMATCH" if available else "ARTIFACT_UNAVAILABLE",
        )

    def purge(self, descriptor: BackupArtifactDescriptor, *, idempotency_key: str) -> ProviderPurgeReceipt:
        path = self._bounded_archive(descriptor.artifact_locator_ref)
        path.unlink(missing_ok=True)
        return ProviderPurgeReceipt(
            operation_id=idempotency_key,
            acknowledged=not path.exists(),
            purged_at=timezone.now() if not path.exists() else None,
            evidence={"removed": not path.exists()},
            error_code="" if not path.exists() else "PROVIDER_PURGE_REJECTED",
        )

    def health(self) -> HealthCheckResult:
        try:
            self.archive_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.NamedTemporaryFile(dir=self.archive_root) as handle:
                handle.write(b"backup-recovery-health")
                handle.flush()
                os.fsync(handle.fileno())
            healthy = os.access(self.archive_root, os.R_OK | os.W_OK | os.X_OK)
            return HealthCheckResult(
                healthy=healthy,
                message="local archive root is available" if healthy else "local archive root is inaccessible",
                details={"adapter": self.adapter_key},
            )
        except OSError:
            return HealthCheckResult(
                healthy=False,
                message="local archive root probe failed",
                details={"adapter": self.adapter_key},
            )

    def _bounded_source(self, value: str) -> Path:
        source = Path(value).expanduser().resolve()
        self._require_below(source, self.source_root)
        return source

    def _bounded_archive(self, value: str) -> Path:
        path = Path(value).expanduser().resolve()
        self._require_below(path, self.archive_root)
        return path

    @staticmethod
    def _require_below(path: Path, root: Path) -> None:
        if path != root and root not in path.parents:
            raise ValueError("Filesystem reference is outside the configured root")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
