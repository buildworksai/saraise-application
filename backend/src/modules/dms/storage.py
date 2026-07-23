"""Bounded, integrity-preserving storage boundary for immutable DMS versions.

The adapter deliberately exposes opaque object keys rather than paths or URLs.
It performs content inspection, hashing, and byte accounting while the storage
backend consumes the upload, so an upload is never buffered in application
memory merely to calculate its metadata.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Final, Mapping, Protocol, runtime_checkable

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, default_storage
from django.utils import timezone

from src.core.observability import get_correlation_id

logger = logging.getLogger("saraise.dms.storage")


class StorageError(RuntimeError):
    """Base class for explicit storage-boundary failures."""


class StorageValidationError(StorageError, ValueError):
    """The supplied content failed size or content validation."""


class StorageIntegrityError(StorageError):
    """Stored bytes are missing or do not match immutable metadata."""


class StorageUnavailableError(StorageError):
    """The configured storage dependency could not complete an operation."""


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Server-measured metadata for one durably saved opaque object."""

    key: str
    size_bytes: int
    checksum_sha256: str
    mime_type: str


@dataclass(frozen=True, slots=True)
class StorageHealth:
    """Sanitized storage readiness evidence."""

    healthy: bool
    status: str
    latency_ms: float
    detail: str
    cleanup_ok: bool = True


@runtime_checkable
class DocumentStoragePort(Protocol):
    """Versioned binary storage surface consumed by DMS services."""

    backend_name: str

    def save(
        self,
        key: str,
        stream: BinaryIO,
        *,
        declared_size: int | None = None,
        max_size_bytes: int | None = None,
        declared_mime_type: str | None = None,
    ) -> StoredObject:
        """Stream one object to its immutable key and return measured metadata."""

    def open(self, key: str) -> BinaryIO:
        """Open an opaque object for binary streaming."""

    def exists(self, key: str) -> bool:
        """Return whether an opaque object exists."""

    def delete(self, key: str) -> None:
        """Delete an opaque object, primarily for transaction compensation."""

    def health_probe(self) -> StorageHealth:
        """Prove save/open/read/delete readiness with a randomized object."""


def build_storage_key(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    *,
    at: datetime | None = None,
) -> str:
    """Build the stable opaque key required by the public storage contract."""

    tenant_uuid = _uuid(tenant_id, "tenant_id")
    document_uuid = _uuid(document_id, "document_id")
    version_uuid = _uuid(version_id, "version_id")
    moment = at or timezone.now()
    return f"tenants/{tenant_uuid}/dms/{moment.year:04d}/{moment.month:02d}/" f"{document_uuid}/{version_uuid}"


# Backward-compatible descriptive alias used by early service implementations.
generate_storage_key = build_storage_key


def _uuid(value: object, field: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a valid UUID") from exc


def _policy_for_key(key: str | None = None) -> dict[str, object]:
    from .services import DEFAULT_DMS_CONFIGURATION, DmsConfigurationService

    if key and key.startswith("tenants/"):
        parts = key.split("/", maxsplit=2)
        try:
            tenant_id = uuid.UUID(parts[1])
        except (IndexError, ValueError):
            tenant_id = None
        if tenant_id is not None:
            return DmsConfigurationService.runtime_values(tenant_id)
    return DmsConfigurationService._copy(DEFAULT_DMS_CONFIGURATION)


def _validate_key(key: str, policy: Mapping[str, object] | None = None) -> str:
    effective = policy or _policy_for_key(key)
    if not isinstance(key, str) or not key or len(key) > effective["storage_key_max_length"]:
        raise StorageValidationError("Storage key must be a non-empty bounded string.")
    path = PurePosixPath(key)
    raw_parts = key.split("/")
    if path.is_absolute() or "\\" in key or "\x00" in key or any(part in {"", ".", ".."} for part in raw_parts):
        raise StorageValidationError("Storage key is not a valid opaque relative key.")
    return key


_OFFICE_MIME_BY_EXTENSION: Final[dict[str, str]] = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
_OFFICE_ARCHIVE_MARKER: Final[dict[str, bytes]] = {
    ".docx": b"word/",
    ".xlsx": b"xl/",
    ".pptx": b"ppt/",
}


def _normalized_declared_mime(value: object | None) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).split(";", maxsplit=1)[0].strip().lower()
    if normalized in {"application/octet-stream", "binary/octet-stream", "application/x-msdownload"}:
        raise StorageValidationError("Ambiguous or executable content types are not accepted.")
    return normalized


def _looks_like_text(sample: bytes, policy: Mapping[str, object]) -> bool:
    if not sample or b"\x00" in sample:
        return False
    try:
        decoded = sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    disallowed = sum(1 for character in decoded if ord(character) < 32 and character not in "\n\r\t\f\b")
    ratio_limit = (len(decoded) * policy["max_control_character_ratio_percent"]) // 100
    return disallowed <= max(policy["min_control_characters"], ratio_limit)


def inspect_content(
    sample: bytes,
    *,
    filename: str = "",
    declared_mime_type: str | None = None,
    policy: Mapping[str, object] | None = None,
) -> str:
    """Return a server-inspected MIME type or reject unsafe/ambiguous bytes."""

    if not isinstance(sample, bytes) or not sample:
        raise StorageValidationError("Empty files are not accepted.")
    effective = policy or _policy_for_key()
    signatures = tuple(bytes.fromhex(value) for value in effective["blocked_file_signatures"])
    if any(sample.startswith(signature) for signature in signatures):
        raise StorageValidationError("Executable content is not accepted.")

    declared = _normalized_declared_mime(declared_mime_type)
    suffix = Path(filename).suffix.lower()
    if sample.startswith(b"%PDF-"):
        observed = "application/pdf"
    elif sample.startswith(b"\x89PNG\r\n\x1a\n"):
        observed = "image/png"
    elif sample.startswith(b"\xff\xd8\xff"):
        observed = "image/jpeg"
    elif sample.startswith((b"GIF87a", b"GIF89a")):
        observed = "image/gif"
    elif sample.startswith((b"II*\x00", b"MM\x00*")):
        observed = "image/tiff"
    elif sample.startswith(b"PK\x03\x04"):
        observed = _OFFICE_MIME_BY_EXTENSION.get(suffix, "")
        marker = _OFFICE_ARCHIVE_MARKER.get(suffix, b"")
        if not observed or declared != observed or b"[Content_Types].xml" not in sample or marker not in sample:
            raise StorageValidationError("Ambiguous archive content is not accepted.")
    elif _looks_like_text(sample, effective):
        declared_is_text = bool(
            declared and (declared.startswith("text/") or declared in {"application/json", "application/xml"})
        )
        observed = declared if declared_is_text and declared is not None else "text/plain"
        stripped = sample.lstrip()
        if observed == "application/json" and not stripped.startswith((b"{", b"[")):
            raise StorageValidationError("Declared and inspected content types do not match.")
        if observed in {"application/xml", "text/xml"} and not stripped.startswith(b"<"):
            raise StorageValidationError("Declared and inspected content types do not match.")
    else:
        raise StorageValidationError("The server could not identify a permitted content type.")

    allowed = frozenset(str(item).lower() for item in effective["permitted_mime_types"])
    if not allowed:
        raise StorageUnavailableError("Permitted MIME policy is unavailable.")
    if observed not in allowed:
        raise StorageValidationError("This content type is not permitted.")
    if declared and declared != observed:
        text_compatible = declared.startswith("text/") and observed.startswith("text/")
        xml_compatible = {declared, observed} <= {"application/xml", "text/xml"}
        if not (text_compatible or xml_compatible):
            raise StorageValidationError("Declared and inspected content types do not match.")
    return observed


class _ValidatedHashingUpload:
    """Single-pass Django storage content object with bounded reads."""

    def __init__(
        self,
        stream: BinaryIO,
        *,
        declared_size: int | None,
        max_size_bytes: int,
        declared_mime_type: str | None,
        policy: Mapping[str, object] | None = None,
    ) -> None:
        self._stream = stream
        self._declared_size = declared_size
        self._maximum = max_size_bytes
        self._declared_mime = declared_mime_type
        self._policy = policy or _policy_for_key()
        self._hash = hashlib.sha256()
        self._size = 0
        self._consumed = False
        self.mime_type: str | None = None
        self.complete = False
        self.name = str(getattr(stream, "name", "upload"))

    @property
    def size_bytes(self) -> int:
        return self._size

    @property
    def checksum_sha256(self) -> str:
        return self._hash.hexdigest()

    def chunks(self, chunk_size: int | None = None) -> Iterator[bytes]:
        if self._consumed:
            raise StorageValidationError("Upload streams may only be consumed once.")
        self._consumed = True
        configured_chunk = int(self._policy["storage_stream_chunk_size"])
        size = min(chunk_size or configured_chunk, configured_chunk)
        inspection_buffer = bytearray()
        iterator = self._source_chunks(size)
        try:
            for raw in iterator:
                if not isinstance(raw, (bytes, bytearray, memoryview)):
                    raise StorageValidationError("Upload stream must yield bytes.")
                chunk = bytes(raw)
                if not chunk:
                    continue
                if self.mime_type is None:
                    inspection_bytes = int(self._policy["content_inspection_window_bytes"])
                    needed = inspection_bytes - len(inspection_buffer)
                    inspection_buffer.extend(chunk[:needed])
                    remainder = chunk[needed:]
                    if len(inspection_buffer) < inspection_bytes:
                        continue
                    self.mime_type = inspect_content(
                        bytes(inspection_buffer),
                        filename=self.name,
                        declared_mime_type=self._declared_mime,
                        policy=self._policy,
                    )
                    yield self._measure(bytes(inspection_buffer))
                    inspection_buffer.clear()
                    if remainder:
                        yield self._measure(remainder)
                    continue
                yield self._measure(chunk)
        finally:
            close = getattr(iterator, "close", None)
            if callable(close):
                close()
        if self.mime_type is None:
            self.mime_type = inspect_content(
                bytes(inspection_buffer),
                filename=self.name,
                declared_mime_type=self._declared_mime,
                policy=self._policy,
            )
            yield self._measure(bytes(inspection_buffer))
        if self._size == 0:
            raise StorageValidationError("Empty files are not accepted.")
        if self._declared_size is not None and self._size != self._declared_size:
            raise StorageValidationError("Declared upload size does not match measured bytes.")
        self.complete = True

    def _measure(self, chunk: bytes) -> bytes:
        self._size += len(chunk)
        if self._size > self._maximum:
            raise StorageValidationError("Upload exceeds the permitted byte limit.")
        if self._declared_size is not None and self._size > self._declared_size:
            raise StorageValidationError("Declared upload size does not match measured bytes.")
        self._hash.update(chunk)
        return chunk

    def _source_chunks(self, chunk_size: int) -> Iterator[bytes]:
        chunks = getattr(self._stream, "chunks", None)
        if callable(chunks):
            yield from chunks(chunk_size=chunk_size)
            return
        while True:
            chunk = self._stream.read(chunk_size)
            if not chunk:
                return
            yield chunk


class DjangoStorageAdapter:
    """Default adapter around Django's configured storage backend."""

    backend_name = "django"

    def __init__(self, storage: Storage | None = None) -> None:
        self._storage = storage or default_storage

    def save(
        self,
        key: str,
        stream: BinaryIO,
        *,
        declared_size: int | None = None,
        max_size_bytes: int | None = None,
        declared_mime_type: str | None = None,
    ) -> StoredObject:
        policy = _policy_for_key(key)
        key = _validate_key(key, policy)
        configured_limit = int(policy["max_upload_bytes"])
        if not key.startswith("tenants/") and hasattr(settings, "DMS_MAX_UPLOAD_BYTES"):
            try:
                configured_limit = int(settings.DMS_MAX_UPLOAD_BYTES)
            except (TypeError, ValueError) as exc:
                raise StorageUnavailableError("DMS upload limit is not configured correctly.") from exc
            if configured_limit <= 0 or configured_limit > int(policy["max_upload_bytes"]):
                raise StorageUnavailableError("DMS upload limit is outside the governed safe range.")
        if max_size_bytes is not None:
            if isinstance(max_size_bytes, bool) or max_size_bytes <= 0:
                raise StorageValidationError("Upload quota must be a positive byte count.")
            configured_limit = min(configured_limit, int(max_size_bytes))
        if declared_size is None:
            size_attribute = getattr(stream, "size", None)
            declared_size = int(size_attribute) if isinstance(size_attribute, int) else None
        if isinstance(declared_size, bool):
            raise StorageValidationError("Declared upload size must be a byte count.")
        if declared_size is not None and (declared_size <= 0 or declared_size > configured_limit):
            raise StorageValidationError("Declared upload size exceeds the permitted byte limit.")
        declared_mime = declared_mime_type or getattr(stream, "content_type", None)
        content = _ValidatedHashingUpload(
            stream,
            declared_size=declared_size,
            max_size_bytes=configured_limit,
            declared_mime_type=declared_mime,
            policy=policy,
        )
        saved_key: str | None = None
        try:
            saved_key = self._storage.save(key, content)  # type: ignore[arg-type]
            if saved_key != key:
                raise StorageIntegrityError("Storage backend changed an immutable object key.")
            if content.mime_type is None or not content.complete:
                raise StorageValidationError("The server could not inspect uploaded content.")
            return StoredObject(
                key=saved_key,
                size_bytes=content.size_bytes,
                checksum_sha256=content.checksum_sha256,
                mime_type=content.mime_type,
            )
        except StorageError:
            self._compensate(saved_key or key)
            raise
        except Exception as exc:
            self._compensate(saved_key or key)
            raise StorageUnavailableError("Storage could not persist the uploaded object.") from exc

    def _compensate(self, key: str) -> None:
        try:
            if self._storage.exists(key):
                self._storage.delete(key)
        except Exception:
            logger.error(
                "DMS storage compensation failed",
                extra={
                    "event": "dms.storage.compensation",
                    "outcome": "failed",
                    "duration_ms": 0,
                    "correlation_id": get_correlation_id(),
                },
                exc_info=False,
            )

    def open(self, key: str) -> BinaryIO:
        try:
            return self._storage.open(_validate_key(key), mode="rb")  # type: ignore[return-value]
        except Exception as exc:
            raise StorageUnavailableError("Stored object is unavailable.") from exc

    def exists(self, key: str) -> bool:
        try:
            return bool(self._storage.exists(_validate_key(key)))
        except Exception as exc:
            raise StorageUnavailableError("Stored object availability could not be verified.") from exc

    def delete(self, key: str) -> None:
        try:
            self._storage.delete(_validate_key(key))
        except Exception as exc:
            raise StorageUnavailableError("Stored object cleanup failed.") from exc

    def health_probe(self) -> StorageHealth:
        started = time.monotonic()
        key = f"system/dms/health/{uuid.uuid4()}"
        saved_key: str | None = None
        try:
            content = ContentFile(b"dms-storage-ready", name="probe.txt")
            saved_key = self._storage.save(key, content)
            if saved_key != key:
                raise StorageIntegrityError("Storage backend changed the randomized health key.")
            with self._storage.open(saved_key, mode="rb") as handle:
                chunk_size = int(_policy_for_key()["storage_stream_chunk_size"])
                valid = handle.read(chunk_size) == b"dms-storage-ready" and handle.read(1) == b""
            if not valid:
                raise StorageIntegrityError("Storage roundtrip integrity check failed.")
        except Exception:
            cleanup_ok = self._health_cleanup(saved_key or key)
            return StorageHealth(
                healthy=False,
                status="unhealthy",
                latency_ms=round((time.monotonic() - started) * 1000, 3),
                detail="dependency_unavailable",
                cleanup_ok=cleanup_ok,
            )
        cleanup_ok = self._health_cleanup(saved_key)
        status = "healthy" if cleanup_ok else "degraded"
        return StorageHealth(
            healthy=True,
            status=status,
            latency_ms=round((time.monotonic() - started) * 1000, 3),
            detail="ready" if cleanup_ok else "cleanup_failed",
            cleanup_ok=cleanup_ok,
        )

    def _health_cleanup(self, key: str | None) -> bool:
        if not key:
            return True
        try:
            if self._storage.exists(key):
                self._storage.delete(key)
            return not self._storage.exists(key)
        except Exception:
            logger.error(
                "DMS storage health cleanup failed",
                extra={
                    "event": "dms.storage.health_cleanup",
                    "outcome": "failed",
                    "duration_ms": 0,
                    "correlation_id": get_correlation_id(),
                },
                exc_info=False,
            )
            return False


_registry_lock = threading.RLock()
_storage_backends: dict[str, DocumentStoragePort] = {}
_default_backend_name = "django"


def register_storage_backend(
    name: str,
    adapter: DocumentStoragePort,
    *,
    replace: bool = False,
) -> DocumentStoragePort:
    """Register a provider-qualified adapter without invalidating old versions."""

    normalized = name.strip().lower() if isinstance(name, str) else ""
    maximum_length = int(_policy_for_key()["storage_backend_name_max_length"])
    if not normalized or len(normalized) > maximum_length or not normalized.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Storage backend name must be a bounded slug.")
    if not isinstance(adapter, DocumentStoragePort):
        raise TypeError("adapter must implement DocumentStoragePort")
    with _registry_lock:
        if normalized in _storage_backends and not replace:
            raise ValueError(f"Storage backend {normalized!r} is already registered.")
        _storage_backends[normalized] = adapter
    return adapter


def configure_document_storage(adapter: DocumentStoragePort, *, name: str | None = None) -> None:
    """Configure the default adapter while retaining provider-qualified history."""

    global _default_backend_name
    backend_name = name or getattr(adapter, "backend_name", "")
    register_storage_backend(backend_name, adapter, replace=True)
    with _registry_lock:
        _default_backend_name = backend_name.strip().lower()


def get_document_storage(name: str | None = None) -> DocumentStoragePort:
    """Resolve the configured adapter or fail explicitly for missing history."""

    requested = (name or _default_backend_name).strip().lower()
    with _registry_lock:
        adapter = _storage_backends.get(requested)
        if adapter is None and requested == "django":
            adapter = DjangoStorageAdapter()
            _storage_backends[requested] = adapter
        if adapter is None:
            raise StorageUnavailableError(f"Storage backend {requested!r} is not registered.")
        return adapter


__all__ = [
    "DjangoStorageAdapter",
    "DocumentStoragePort",
    "StorageError",
    "StorageHealth",
    "StorageIntegrityError",
    "StorageUnavailableError",
    "StorageValidationError",
    "StoredObject",
    "build_storage_key",
    "configure_document_storage",
    "generate_storage_key",
    "get_document_storage",
    "inspect_content",
    "register_storage_backend",
]
