"""Executable contract tests for bounded DMS binary storage."""

from __future__ import annotations

import hashlib
import io
import uuid
from datetime import datetime, timezone

import pytest
from django.core.files.storage import Storage

from src.modules.dms import storage as storage_module
from src.modules.dms.storage import (
    DjangoStorageAdapter,
    StorageIntegrityError,
    StorageUnavailableError,
    StorageValidationError,
    build_storage_key,
    configure_document_storage,
    get_document_storage,
    inspect_content,
    register_storage_backend,
)


class MemoryStorage(Storage):
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_save = False
        self.fail_open = False
        self.fail_exists = False
        self.fail_delete = False
        self.rename_to: str | None = None

    def exists(self, name: str) -> bool:
        if self.fail_exists:
            raise OSError("private storage error")
        return name in self.objects

    def _save(self, name: str, content: object) -> str:
        if self.fail_save:
            raise OSError("private storage error")
        chunks = getattr(content, "chunks")
        saved_name = self.rename_to or name
        self.objects[saved_name] = b"".join(chunks())
        return saved_name

    def _open(self, name: str, mode: str = "rb") -> io.BytesIO:
        del mode
        if self.fail_open:
            raise OSError("private storage error")
        return io.BytesIO(self.objects[name])

    def delete(self, name: str) -> None:
        if self.fail_delete:
            raise OSError("private storage error")
        self.objects.pop(name, None)


@pytest.mark.parametrize(
    ("sample", "filename", "declared", "expected"),
    [
        (b"%PDF-1.7\nbody", "report.pdf", "application/pdf", "application/pdf"),
        (b"\x89PNG\r\n\x1a\nbody", "image.png", "image/png", "image/png"),
        (b"\xff\xd8\xffbody", "photo.jpg", "image/jpeg", "image/jpeg"),
        (b"GIF89abody", "chart.gif", "image/gif", "image/gif"),
        (b"II*\x00body", "scan.tif", "image/tiff", "image/tiff"),
        (b'{"safe": true}', "data.json", "application/json", "application/json"),
        (b"<safe/>", "data.xml", "text/xml", "text/xml"),
        (b"plain text", "note.txt", "text/markdown", "text/markdown"),
        (
            b"PK\x03\x04[Content_Types].xml word/document.xml",
            "letter.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ],
)
def test_content_inspection_accepts_only_evidenced_types(sample, filename, declared, expected):
    assert inspect_content(sample, filename=filename, declared_mime_type=declared) == expected


@pytest.mark.parametrize(
    ("sample", "filename", "declared"),
    [
        (b"", "empty.txt", "text/plain"),
        (b"MZunsafe", "malware.exe", "application/x-msdownload"),
        (b"\x7fELFunsafe", "payload", None),
        (b"\x00\x01\x02", "unknown.bin", None),
        (b"not-json", "data.json", "application/json"),
        (b"not-xml", "data.xml", "application/xml"),
        (b"%PDF-1.7", "fake.png", "image/png"),
        (b"PK\x03\x04not-office", "archive.zip", "application/zip"),
        (b"plain", "plain.txt", "application/octet-stream"),
    ],
)
def test_content_inspection_rejects_unsafe_or_ambiguous_bytes(sample, filename, declared):
    with pytest.raises(StorageValidationError):
        inspect_content(sample, filename=filename, declared_mime_type=declared)


def test_storage_key_is_stable_opaque_and_uuid_validated():
    tenant_id, document_id, version_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    key = build_storage_key(
        tenant_id,
        document_id,
        version_id,
        at=datetime(2026, 7, 22, tzinfo=timezone.utc),
    )
    assert key == f"tenants/{tenant_id}/dms/2026/07/{document_id}/{version_id}"
    with pytest.raises(ValueError, match="tenant_id"):
        build_storage_key("invalid", document_id, version_id)  # type: ignore[arg-type]


def test_adapter_streams_measures_hashes_opens_and_deletes():
    backend = MemoryStorage()
    adapter = DjangoStorageAdapter(backend)
    body = b"plain text file\n" * 800
    stream = io.BytesIO(body)
    stream.name = "notes.txt"  # type: ignore[attr-defined]
    stored = adapter.save(
        "tenant/object",
        stream,
        declared_size=len(body),
        declared_mime_type="text/plain",
    )
    assert stored.size_bytes == len(body)
    assert stored.checksum_sha256 == hashlib.sha256(body).hexdigest()
    assert stored.mime_type == "text/plain"
    assert adapter.exists(stored.key)
    with adapter.open(stored.key) as handle:
        assert handle.read() == body
    adapter.delete(stored.key)
    assert not adapter.exists(stored.key)


@pytest.mark.parametrize(
    "key",
    ["", "/absolute", "../escape", "a//b", "a/./b", "a/../b", "a\\b", "a\x00b"],
)
def test_adapter_rejects_unsafe_keys(key):
    with pytest.raises(StorageValidationError):
        DjangoStorageAdapter(MemoryStorage()).save(key, io.BytesIO(b"plain"))


def test_adapter_enforces_measured_and_declared_limits(settings):
    settings.DMS_MAX_UPLOAD_BYTES = 5
    adapter = DjangoStorageAdapter(MemoryStorage())
    for declared_size in (True, 0, 6):
        with pytest.raises(StorageValidationError):
            adapter.save("safe/key", io.BytesIO(b"plain"), declared_size=declared_size)
    with pytest.raises(StorageValidationError, match="quota"):
        adapter.save("safe/key", io.BytesIO(b"plain"), max_size_bytes=True)
    settings.DMS_MAX_UPLOAD_BYTES = "invalid"
    with pytest.raises(StorageUnavailableError):
        adapter.save("safe/key", io.BytesIO(b"plain"))


def test_adapter_detects_size_mismatch_and_changed_immutable_key():
    adapter = DjangoStorageAdapter(MemoryStorage())
    with pytest.raises(StorageValidationError, match="measured"):
        adapter.save("safe/key", io.BytesIO(b"plain"), declared_size=4)
    backend = MemoryStorage()
    backend.rename_to = "changed/key"
    with pytest.raises(StorageIntegrityError, match="changed"):
        DjangoStorageAdapter(backend).save("safe/key", io.BytesIO(b"plain"))
    assert "safe/key" not in backend.objects


def test_adapter_wraps_backend_failures_without_leaking_details():
    backend = MemoryStorage()
    adapter = DjangoStorageAdapter(backend)
    backend.fail_save = True
    with pytest.raises(StorageUnavailableError, match="persist") as save_error:
        adapter.save("safe/key", io.BytesIO(b"plain"))
    assert "private" not in str(save_error.value)
    backend.fail_save = False
    backend.objects["safe/key"] = b"plain"
    backend.fail_open = True
    with pytest.raises(StorageUnavailableError, match="unavailable"):
        adapter.open("safe/key")
    backend.fail_open = False
    backend.fail_exists = True
    with pytest.raises(StorageUnavailableError, match="verified"):
        adapter.exists("safe/key")
    backend.fail_exists = False
    backend.fail_delete = True
    with pytest.raises(StorageUnavailableError, match="cleanup"):
        adapter.delete("safe/key")


def test_health_probe_proves_roundtrip_and_reports_cleanup_degradation():
    healthy = DjangoStorageAdapter(MemoryStorage()).health_probe()
    assert healthy.healthy and healthy.status == "healthy" and healthy.cleanup_ok

    cleanup_failure = MemoryStorage()
    cleanup_failure.fail_delete = True
    degraded = DjangoStorageAdapter(cleanup_failure).health_probe()
    assert degraded.healthy and degraded.status == "degraded" and not degraded.cleanup_ok

    unavailable = MemoryStorage()
    unavailable.fail_save = True
    unhealthy = DjangoStorageAdapter(unavailable).health_probe()
    assert not unhealthy.healthy and unhealthy.status == "unhealthy"


def test_storage_registry_preserves_history_and_fails_missing_backends():
    first = DjangoStorageAdapter(MemoryStorage())
    second = DjangoStorageAdapter(MemoryStorage())
    first.backend_name = "archive_one"
    second.backend_name = "archive_two"
    configure_document_storage(first)
    register_storage_backend("archive_two", second)
    assert get_document_storage() is first
    assert get_document_storage("archive_two") is second
    with pytest.raises(ValueError, match="already registered"):
        register_storage_backend("archive_two", second)
    with pytest.raises((TypeError, ValueError)):
        register_storage_backend("bad/name", object())  # type: ignore[arg-type]
    with pytest.raises(StorageUnavailableError, match="not registered"):
        get_document_storage("missing")


def test_single_pass_upload_rejects_non_bytes_and_second_consumption():
    content = storage_module._ValidatedHashingUpload(
        io.BytesIO(b"plain"),
        declared_size=5,
        max_size_bytes=5,
        declared_mime_type="text/plain",
    )
    assert b"".join(content.chunks()) == b"plain"
    with pytest.raises(StorageValidationError, match="only be consumed once"):
        next(content.chunks())

    class InvalidChunks:
        name = "bad.txt"

        def chunks(self, *, chunk_size: int):
            del chunk_size
            yield "not bytes"

    invalid = storage_module._ValidatedHashingUpload(
        InvalidChunks(),  # type: ignore[arg-type]
        declared_size=None,
        max_size_bytes=10,
        declared_mime_type="text/plain",
    )
    with pytest.raises(StorageValidationError, match="yield bytes"):
        list(invalid.chunks())
