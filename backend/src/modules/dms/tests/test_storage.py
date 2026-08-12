"""Executable contract tests for bounded DMS binary storage."""

from __future__ import annotations

import hashlib
import io
import uuid
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest
from django.core.files.storage import Storage

from src.modules.dms import storage as storage_module
from src.modules.dms.storage import (
    DjangoStorageAdapter,
    StorageHealth,
    StorageIntegrityError,
    StorageUnavailableError,
    StorageValidationError,
    StoredObject,
    build_storage_key,
    configure_document_storage,
    get_document_storage,
    inspect_content,
    register_storage_backend,
)


class TrackingBytesIO(io.BytesIO):
    def __init__(self, initial_bytes: bytes, read_sizes: list[int | None]) -> None:
        super().__init__(initial_bytes)
        self._read_sizes = read_sizes

    def read(self, size: int | None = -1) -> bytes:
        self._read_sizes.append(size)
        return super().read(size)


class MemoryStorage(Storage):
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_save = False
        self.fail_open = False
        self.fail_exists = False
        self.fail_delete = False
        self.rename_to: str | None = None
        self.open_modes: list[str] = []
        self.checked_names: list[str] = []
        self.saved_names: list[str] = []
        self.saved_content_names: list[str] = []
        self.deleted_names: list[str] = []
        self.read_sizes: list[int | None] = []

    def exists(self, name: str) -> bool:
        self.checked_names.append(name)
        if self.fail_exists:
            raise OSError("private storage error")
        return name in self.objects

    def _save(self, name: str, content: object) -> str:
        if self.fail_save:
            raise OSError("private storage error")
        chunks = getattr(content, "chunks")
        saved_name = self.rename_to or name
        self.saved_names.append(saved_name)
        self.saved_content_names.append(str(getattr(content, "name", "")))
        self.objects[saved_name] = b"".join(chunks())
        return saved_name

    def _open(self, name: str, mode: str = "rb") -> io.BytesIO:
        self.open_modes.append(mode)
        if self.fail_open:
            raise OSError("private storage error")
        return TrackingBytesIO(self.objects[name], self.read_sizes)

    def delete(self, name: str) -> None:
        if self.fail_delete:
            raise OSError("private storage error")
        self.deleted_names.append(name)
        self.objects.pop(name, None)


class PartialConsumeStorage(MemoryStorage):
    def _save(self, name: str, content: object) -> str:
        chunks = getattr(content, "chunks")
        iterator = chunks()
        self.objects[name] = next(iterator)
        return name


class GenericFailingSaveStorage(MemoryStorage):
    def __init__(self) -> None:
        super().__init__()
        self.checked_keys: list[object] = []

    def _save(self, name: str, content: object) -> str:
        del name, content
        raise RuntimeError("private storage error")

    def exists(self, name: str) -> bool:
        self.checked_keys.append(name)
        return False


class CorruptingSaveStorage(MemoryStorage):
    def _save(self, name: str, content: object) -> str:
        saved_name = super()._save(name, content)
        self.objects[saved_name] = b"corrupt"
        return saved_name


class NamelessStorageAdapter:
    def save(
        self,
        key: str,
        stream: object,
        *,
        declared_size: int | None = None,
        max_size_bytes: int | None = None,
        declared_mime_type: str | None = None,
    ) -> StoredObject:
        del key, stream, declared_size, max_size_bytes, declared_mime_type
        raise AssertionError("not used")

    def open(self, key: str) -> io.BytesIO:
        del key
        raise AssertionError("not used")

    def exists(self, key: str) -> bool:
        del key
        return False

    def delete(self, key: str) -> None:
        del key

    def health_probe(self) -> StorageHealth:
        return StorageHealth(healthy=False, status="unused", latency_ms=0, detail="unused")


def test_storage_contract_metadata_is_immutable_slotted_and_namespaced():
    stored = StoredObject(key="safe/key", size_bytes=5, checksum_sha256="abc", mime_type="text/plain")
    health = StorageHealth(healthy=True, status="healthy", latency_ms=1.5, detail="ready")

    assert storage_module.logger.name == "saraise.dms.storage"
    assert DjangoStorageAdapter.backend_name == "django"
    assert not hasattr(stored, "__dict__")
    assert not hasattr(health, "__dict__")
    with pytest.raises(FrozenInstanceError):
        stored.size_bytes = 6  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        health.status = "degraded"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("sample", "filename", "declared", "expected"),
    [
        (b"%PDF-1.7\nbody", "report.pdf", "application/pdf", "application/pdf"),
        (b"\x89PNG\r\n\x1a\nbody", "image.png", "image/png", "image/png"),
        (b"\xff\xd8\xffbody", "photo.jpg", "image/jpeg", "image/jpeg"),
        (b"GIF89abody", "chart.gif", "image/gif", "image/gif"),
        (b"GIF87abody", "legacy.gif", "image/gif", "image/gif"),
        (b"II*\x00body", "scan.tif", "image/tiff", "image/tiff"),
        (b"MM\x00*body", "scan.tif", "image/tiff", "image/tiff"),
        (b'{"safe": true}', "data.json", "application/json", "application/json"),
        (b'["safe"]', "data.json", "application/json", "application/json"),
        (b"<safe/>", "data.xml", "application/xml", "application/xml"),
        (b"<safe/>", "data.xml", "text/xml", "text/xml"),
        (b"plain text", "note.txt", "text/markdown", "text/markdown"),
        (
            b"PK\x03\x04[Content_Types].xml word/document.xml",
            "letter.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            b"PK\x03\x04[Content_Types].xml xl/workbook.xml",
            "ledger.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (
            b"PK\x03\x04[Content_Types].xml ppt/presentation.xml",
            "briefing.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
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
        (b"not-xml", "data.xml", "text/xml"),
        (b"%PDF-1.7", "fake.png", "image/png"),
        (b"PK\x03\x04not-office", "archive.zip", "application/zip"),
        (
            b"PK\x03\x04[Content_Types].xml xl/workbook.xml",
            "ledger.xlsx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        (
            b"PK\x03\x04[Content_Types].xml xl/workbook.xml",
            "letter.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            b"PK\x03\x04[Content_Types].xml word/document.xml",
            "ledger.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (
            b"PK\x03\x04[Content_Types].xml word/document.xml",
            "briefing.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        (b"plain", "plain.txt", "binary/octet-stream"),
        (b"plain", "plain.txt", "application/x-msdownload"),
        (b"plain\x00text", "plain.txt", "text/plain"),
        (b"plain", "plain.txt", "application/pdf"),
        (b"plain", "plain.txt", "application/octet-stream"),
    ],
)
def test_content_inspection_rejects_unsafe_or_ambiguous_bytes(sample, filename, declared):
    with pytest.raises(StorageValidationError):
        inspect_content(sample, filename=filename, declared_mime_type=declared)


def test_content_inspection_enforces_configured_mime_policy():
    policy = storage_module._policy_for_key()
    constrained = dict(policy)
    constrained["permitted_mime_types"] = []
    with pytest.raises(StorageUnavailableError) as unavailable_error:
        inspect_content(b"plain", filename="note.txt", declared_mime_type="text/plain", policy=constrained)
    assert str(unavailable_error.value) == "Permitted MIME policy is unavailable."

    constrained["permitted_mime_types"] = ["application/pdf"]
    with pytest.raises(StorageValidationError) as validation_error:
        inspect_content(b"plain", filename="note.txt", declared_mime_type="text/plain", policy=constrained)
    assert str(validation_error.value) == "This content type is not permitted."


def test_content_inspection_accepts_text_at_configured_control_character_boundary():
    policy = dict(storage_module._policy_for_key())
    policy["max_control_character_ratio_percent"] = 5
    policy["min_control_characters"] = 0
    sample = (b"\x01" * 5) + (b"a" * 95)

    assert inspect_content(sample, filename="note.txt", declared_mime_type="text/plain", policy=policy) == "text/plain"


def test_content_inspection_normalizes_declared_mime_parameters():
    observed = inspect_content(
        b"plain text",
        filename="note.txt",
        declared_mime_type="text/plain; charset=utf-8",
    )

    assert observed == "text/plain"


def test_content_inspection_rejects_invalid_utf8_text():
    with pytest.raises(StorageValidationError) as exc_info:
        inspect_content(b"\xffinvalid", filename="note.txt", declared_mime_type="text/plain")

    assert str(exc_info.value) == "The server could not identify a permitted content type."


@pytest.mark.parametrize(
    ("sample", "filename", "declared_mime_type"),
    [
        (b"not-json", "data.json", "application/json"),
        (b"not-xml", "data.xml", "application/xml"),
        (b"not-xml", "data.xml", "text/xml"),
    ],
)
def test_content_inspection_reports_exact_declared_mismatch_error(sample, filename, declared_mime_type):
    with pytest.raises(StorageValidationError) as exc_info:
        inspect_content(sample, filename=filename, declared_mime_type=declared_mime_type)

    assert str(exc_info.value) == "Declared and inspected content types do not match."


def test_content_inspection_reports_exact_signature_mismatch_error():
    with pytest.raises(StorageValidationError) as exc_info:
        inspect_content(b"%PDF-1.7", filename="fake.png", declared_mime_type="image/png")

    assert str(exc_info.value) == "Declared and inspected content types do not match."


def test_content_inspection_accepts_text_at_configured_minimum_control_boundary():
    policy = dict(storage_module._policy_for_key())
    policy["max_control_character_ratio_percent"] = 0
    policy["min_control_characters"] = 2
    sample = (b"\x01" * 2) + (b"a" * 98)

    assert inspect_content(sample, filename="note.txt", declared_mime_type="text/plain", policy=policy) == "text/plain"


def test_content_inspection_rejects_text_above_configured_control_ratio():
    policy = dict(storage_module._policy_for_key())
    policy["max_control_character_ratio_percent"] = 5
    policy["min_control_characters"] = 0
    sample = (b"\x01" * 6) + (b"a" * 94)

    with pytest.raises(StorageValidationError):
        inspect_content(sample, filename="note.txt", declared_mime_type="text/plain", policy=policy)


@pytest.mark.parametrize(
    "declared_mime_type",
    ["application/octet-stream", "binary/octet-stream", "application/x-msdownload"],
)
def test_content_inspection_reports_exact_ambiguous_mime_error(declared_mime_type):
    with pytest.raises(StorageValidationError) as exc_info:
        inspect_content(b"plain", filename="note.txt", declared_mime_type=declared_mime_type)

    assert str(exc_info.value) == "Ambiguous or executable content types are not accepted."


def test_content_inspection_reports_exact_empty_file_error():
    with pytest.raises(StorageValidationError) as exc_info:
        inspect_content(b"", filename="empty.txt", declared_mime_type="text/plain")

    assert str(exc_info.value) == "Empty files are not accepted."


def test_content_inspection_rejects_non_bytes_without_type_leakage():
    with pytest.raises(StorageValidationError) as exc_info:
        inspect_content("plain", filename="note.txt", declared_mime_type="text/plain")  # type: ignore[arg-type]

    assert str(exc_info.value) == "Empty files are not accepted."


def test_content_inspection_reports_exact_executable_signature_error():
    with pytest.raises(StorageValidationError) as exc_info:
        inspect_content(b"MZunsafe", filename="malware.exe", declared_mime_type=None)

    assert str(exc_info.value) == "Executable content is not accepted."


def test_content_inspection_reports_exact_ambiguous_archive_error():
    with pytest.raises(StorageValidationError) as exc_info:
        inspect_content(
            b"PK\x03\x04[Content_Types].xml xl/workbook.xml",
            filename="ledger.xlsx",
            declared_mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

    assert str(exc_info.value) == "Ambiguous archive content is not accepted."


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("max_control_character_ratio_percent", "10"),
        ("min_control_characters", True),
    ],
)
def test_content_inspection_rejects_non_integer_policy_values(key, value):
    policy = storage_module._policy_for_key()
    corrupted = dict(policy)
    corrupted[key] = value

    with pytest.raises(StorageUnavailableError) as exc_info:
        inspect_content(b"plain", filename="note.txt", declared_mime_type="text/plain", policy=corrupted)
    assert str(exc_info.value) == f"DMS policy value {key!r} must be an integer."


@pytest.mark.parametrize("value", ["text/plain", b"text/plain", object()])
def test_content_inspection_rejects_non_sequence_mime_policy(value):
    policy = storage_module._policy_for_key()
    corrupted = dict(policy)
    corrupted["permitted_mime_types"] = value

    with pytest.raises(StorageUnavailableError) as exc_info:
        inspect_content(b"plain", filename="note.txt", declared_mime_type="text/plain", policy=corrupted)
    assert str(exc_info.value) == "DMS policy value 'permitted_mime_types' must be a sequence."


def test_storage_key_is_stable_opaque_and_uuid_validated():
    tenant_id, document_id, version_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    key = build_storage_key(
        tenant_id,
        document_id,
        version_id,
        at=datetime(2026, 7, 22, tzinfo=timezone.utc),
    )
    assert key == f"tenants/{tenant_id}/dms/2026/07/{document_id}/{version_id}"
    with pytest.raises(ValueError) as tenant_error:
        build_storage_key("invalid", document_id, version_id)  # type: ignore[arg-type]
    assert str(tenant_error.value) == "tenant_id must be a valid UUID"
    with pytest.raises(ValueError) as document_error:
        build_storage_key(tenant_id, "invalid", version_id)  # type: ignore[arg-type]
    assert str(document_error.value) == "document_id must be a valid UUID"
    with pytest.raises(ValueError) as version_error:
        build_storage_key(tenant_id, document_id, "invalid")  # type: ignore[arg-type]
    assert str(version_error.value) == "version_id must be a valid UUID"


def test_policy_for_key_falls_back_for_malformed_tenant_key(monkeypatch):
    def runtime_values(runtime_tenant_id: uuid.UUID) -> dict[str, object]:
        raise AssertionError(f"unexpected tenant runtime lookup for {runtime_tenant_id!r}")

    monkeypatch.setattr(
        "src.modules.dms.services.DmsConfigurationService.runtime_values",
        staticmethod(runtime_values),
    )

    policy = storage_module._policy_for_key("tenants/not-a-uuid/dms/object")

    assert policy == storage_module._policy_for_key()


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
    assert backend.open_modes == ["rb"]
    adapter.delete(stored.key)
    assert not adapter.exists(stored.key)


def test_adapter_uses_stream_name_for_office_content_inspection():
    body = b"PK\x03\x04[Content_Types].xml word/document.xml"
    stream = io.BytesIO(body)
    stream.name = "letter.docx"  # type: ignore[attr-defined]
    stream.content_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )  # type: ignore[attr-defined]

    stored = DjangoStorageAdapter(MemoryStorage()).save("safe/key", stream)

    assert stored.mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert stored.size_bytes == len(body)


@pytest.mark.parametrize(
    "key",
    ["", "/absolute", "../escape", "a//b", "a/./b", "a/../b", "a\\b", "a\x00b"],
)
def test_adapter_rejects_unsafe_keys(key):
    with pytest.raises(StorageValidationError):
        DjangoStorageAdapter(MemoryStorage()).save(key, io.BytesIO(b"plain"))


def test_adapter_rejects_unsafe_key_with_exact_message():
    with pytest.raises(StorageValidationError) as exc_info:
        DjangoStorageAdapter(MemoryStorage()).save("a/../b", io.BytesIO(b"plain"))

    assert str(exc_info.value) == "Storage key is not a valid opaque relative key."


def test_adapter_rejects_non_string_key_without_type_leakage():
    with pytest.raises(StorageValidationError) as exc_info:
        DjangoStorageAdapter(MemoryStorage()).save(object(), io.BytesIO(b"plain"))  # type: ignore[arg-type]
    assert str(exc_info.value) == "Storage key must be a non-empty bounded string."


def test_adapter_accepts_key_at_configured_maximum_length():
    policy = storage_module._policy_for_key()
    key = "k" * storage_module._policy_int(policy, "storage_key_max_length")
    adapter = DjangoStorageAdapter(MemoryStorage())

    stored = adapter.save(key, io.BytesIO(b"plain"), declared_mime_type="text/plain")

    assert stored.key == key


def test_adapter_enforces_measured_and_declared_limits(settings):
    settings.DMS_MAX_UPLOAD_BYTES = 5
    adapter = DjangoStorageAdapter(MemoryStorage())
    with pytest.raises(StorageValidationError) as bool_declared_error:
        adapter.save("safe/key", io.BytesIO(b"plain"), declared_size=True)
    assert str(bool_declared_error.value) == "Declared upload size must be a byte count."
    bool_sized_stream = io.BytesIO(b"plain")
    bool_sized_stream.size = True  # type: ignore[attr-defined]
    with pytest.raises(StorageValidationError) as bool_inferred_error:
        adapter.save("safe/inferred", bool_sized_stream)
    assert str(bool_inferred_error.value) == "Declared upload size must be a byte count."
    for declared_size in (0, 6):
        with pytest.raises(StorageValidationError) as declared_limit_error:
            adapter.save("safe/key", io.BytesIO(b"plain"), declared_size=declared_size)
        assert str(declared_limit_error.value) == "Declared upload size exceeds the permitted byte limit."
    with pytest.raises(StorageValidationError) as bool_quota_error:
        adapter.save("safe/key", io.BytesIO(b"plain"), max_size_bytes=True)
    assert str(bool_quota_error.value) == "Upload quota must be a positive byte count."
    with pytest.raises(StorageValidationError) as zero_quota_error:
        adapter.save("safe/key", io.BytesIO(b"plain"), max_size_bytes=0)
    assert str(zero_quota_error.value) == "Upload quota must be a positive byte count."
    with pytest.raises(StorageValidationError) as override_limit_error:
        adapter.save("safe/key", io.BytesIO(b"plain"), max_size_bytes=4)
    assert str(override_limit_error.value) == "Upload exceeds the permitted byte limit."
    stored = adapter.save("safe/key", io.BytesIO(b"a"), max_size_bytes=1, declared_mime_type="text/plain")
    assert stored.size_bytes == 1
    declared_one = adapter.save("safe/declared-one", io.BytesIO(b"a"), declared_size=1, declared_mime_type="text/plain")
    assert declared_one.size_bytes == 1
    declared_at_limit = adapter.save(
        "safe/declared-at-limit",
        io.BytesIO(b"plain"),
        declared_size=5,
        declared_mime_type="text/plain",
    )
    assert declared_at_limit.size_bytes == 5
    settings.DMS_MAX_UPLOAD_BYTES = "invalid"
    with pytest.raises(StorageUnavailableError) as invalid_settings_error:
        adapter.save("safe/key", io.BytesIO(b"plain"))
    assert str(invalid_settings_error.value) == "DMS upload limit is not configured correctly."


def test_adapter_enforces_legacy_settings_limit_safe_range(settings):
    policy = storage_module._policy_for_key()
    settings.DMS_MAX_UPLOAD_BYTES = 0
    with pytest.raises(StorageUnavailableError) as zero_error:
        DjangoStorageAdapter(MemoryStorage()).save("safe/key", io.BytesIO(b"a"), declared_mime_type="text/plain")
    assert str(zero_error.value) == "DMS upload limit is outside the governed safe range."

    settings.DMS_MAX_UPLOAD_BYTES = 1
    stored = DjangoStorageAdapter(MemoryStorage()).save("safe/key", io.BytesIO(b"a"), declared_mime_type="text/plain")
    assert stored.size_bytes == 1

    settings.DMS_MAX_UPLOAD_BYTES = storage_module._policy_int(policy, "max_upload_bytes")
    stored = DjangoStorageAdapter(MemoryStorage()).save("safe/key2", io.BytesIO(b"a"), declared_mime_type="text/plain")
    assert stored.size_bytes == 1

    settings.DMS_MAX_UPLOAD_BYTES = storage_module._policy_int(policy, "max_upload_bytes") + 1
    with pytest.raises(StorageUnavailableError) as high_error:
        DjangoStorageAdapter(MemoryStorage()).save("safe/key3", io.BytesIO(b"a"), declared_mime_type="text/plain")
    assert str(high_error.value) == "DMS upload limit is outside the governed safe range."


def test_validated_upload_tracks_initial_state_and_single_byte_completion():
    upload = storage_module._ValidatedHashingUpload(
        io.BytesIO(b"a"),
        declared_size=1,
        max_size_bytes=1,
        declared_mime_type="text/plain",
    )

    assert upload.name == "upload"
    assert upload.mime_type is None
    assert upload.complete is False
    assert upload._consumed is False

    assert list(upload.chunks()) == [b"a"]

    assert upload.size_bytes == 1
    assert upload.checksum_sha256 == hashlib.sha256(b"a").hexdigest()
    assert upload.mime_type == "text/plain"
    assert upload.complete is True
    with pytest.raises(StorageValidationError) as consumed_error:
        list(upload.chunks())
    assert str(consumed_error.value) == "Upload streams may only be consumed once."


def test_validated_upload_rejects_empty_stream_with_exact_error():
    upload = storage_module._ValidatedHashingUpload(
        io.BytesIO(b""),
        declared_size=None,
        max_size_bytes=1,
        declared_mime_type="text/plain",
    )

    with pytest.raises(StorageValidationError) as empty_error:
        list(upload.chunks())

    assert str(empty_error.value) == "Empty files are not accepted."
    assert upload.complete is False


def test_adapter_uses_tenant_policy_for_tenant_scoped_keys(monkeypatch):
    tenant_id = uuid.uuid4()
    tenant_policy = dict(storage_module._policy_for_key())
    tenant_policy["permitted_mime_types"] = ["application/pdf"]

    def runtime_values(runtime_tenant_id: uuid.UUID) -> dict[str, object]:
        assert runtime_tenant_id == tenant_id
        return tenant_policy

    monkeypatch.setattr(
        "src.modules.dms.services.DmsConfigurationService.runtime_values",
        staticmethod(runtime_values),
    )

    key = build_storage_key(tenant_id, uuid.uuid4(), uuid.uuid4())
    with pytest.raises(StorageValidationError, match="not permitted"):
        DjangoStorageAdapter(MemoryStorage()).save(key, io.BytesIO(b"plain"), declared_mime_type="text/plain")


def test_adapter_ignores_legacy_settings_limit_for_tenant_scoped_keys(settings, monkeypatch):
    tenant_id = uuid.uuid4()
    tenant_policy = dict(storage_module._policy_for_key())
    tenant_policy["max_upload_bytes"] = 64

    monkeypatch.setattr(
        "src.modules.dms.services.DmsConfigurationService.runtime_values",
        staticmethod(lambda runtime_tenant_id: tenant_policy if runtime_tenant_id == tenant_id else {}),
    )
    settings.DMS_MAX_UPLOAD_BYTES = 5

    key = build_storage_key(tenant_id, uuid.uuid4(), uuid.uuid4())
    stored = DjangoStorageAdapter(MemoryStorage()).save(
        key,
        io.BytesIO(b"plain text"),
        declared_mime_type="text/plain",
    )

    assert stored.key == key
    assert stored.size_bytes == len(b"plain text")


def test_adapter_detects_size_mismatch_and_changed_immutable_key():
    adapter = DjangoStorageAdapter(MemoryStorage())
    with pytest.raises(StorageValidationError, match="measured"):
        adapter.save("safe/key", io.BytesIO(b"plain"), declared_size=4)
    sized_stream = io.BytesIO(b"plain")
    sized_stream.size = 4  # type: ignore[attr-defined]
    with pytest.raises(StorageValidationError) as inferred_size_error:
        adapter.save("safe/inferred-size", sized_stream)
    assert str(inferred_size_error.value) == "Declared upload size does not match measured bytes."
    backend = MemoryStorage()
    backend.rename_to = "changed/key"
    with pytest.raises(StorageIntegrityError) as changed_key_error:
        DjangoStorageAdapter(backend).save("safe/key", io.BytesIO(b"plain"))
    assert str(changed_key_error.value) == "Storage backend changed an immutable object key."
    assert "safe/key" not in backend.objects
    assert "changed/key" not in backend.objects


def test_adapter_uses_stream_content_type_when_declared_type_is_absent():
    stream = io.BytesIO(b"plain")
    stream.content_type = "application/pdf"  # type: ignore[attr-defined]

    with pytest.raises(StorageValidationError, match="match"):
        DjangoStorageAdapter(MemoryStorage()).save("safe/key", stream)


def test_adapter_rejects_backend_that_returns_before_consuming_upload():
    backend = PartialConsumeStorage()

    with pytest.raises(StorageValidationError) as exc_info:
        DjangoStorageAdapter(backend).save("safe/key", io.BytesIO(b"plain"), declared_mime_type="text/plain")

    assert str(exc_info.value) == "The server could not inspect uploaded content."
    assert "safe/key" not in backend.objects


def test_adapter_wraps_backend_failures_without_leaking_details():
    backend = MemoryStorage()
    adapter = DjangoStorageAdapter(backend)
    backend.fail_save = True
    with pytest.raises(StorageUnavailableError, match="persist") as save_error:
        adapter.save("safe/key", io.BytesIO(b"plain"))
    assert "private" not in str(save_error.value)
    generic_backend = GenericFailingSaveStorage()
    with pytest.raises(StorageUnavailableError) as generic_save_error:
        DjangoStorageAdapter(generic_backend).save("safe/key", io.BytesIO(b"plain"))
    assert str(generic_save_error.value) == "Storage could not persist the uploaded object."
    assert generic_backend.checked_keys[-1] == "safe/key"
    backend.fail_save = False
    backend.objects["safe/key"] = b"plain"
    backend.fail_open = True
    with pytest.raises(StorageUnavailableError) as open_error:
        adapter.open("safe/key")
    assert str(open_error.value) == "Stored object is unavailable."
    backend.fail_open = False
    backend.fail_exists = True
    with pytest.raises(StorageUnavailableError) as exists_error:
        adapter.exists("safe/key")
    assert str(exists_error.value) == "Stored object availability could not be verified."
    backend.fail_exists = False
    backend.fail_delete = True
    with pytest.raises(StorageUnavailableError) as delete_error:
        adapter.delete("safe/key")
    assert str(delete_error.value) == "Stored object cleanup failed."


def test_adapter_logs_compensation_failures_with_structured_context(caplog):
    backend = MemoryStorage()
    backend.objects["safe/key"] = b"plain"
    backend.fail_delete = True
    caplog.set_level("ERROR", logger=storage_module.logger.name)

    DjangoStorageAdapter(backend)._compensate("safe/key")

    assert caplog.messages == ["DMS storage compensation failed"]
    record = caplog.records[0]
    assert record.event == "dms.storage.compensation"
    assert record.outcome == "failed"
    assert record.duration_ms == 0
    assert hasattr(record, "correlation_id")
    assert not hasattr(record, "XXcorrelation_idXX")
    assert record.exc_info is False


def test_health_probe_proves_roundtrip_and_reports_cleanup_degradation():
    health_backend = MemoryStorage()
    healthy = DjangoStorageAdapter(health_backend).health_probe()
    assert healthy.healthy and healthy.status == "healthy" and healthy.cleanup_ok
    assert healthy.detail == "ready"
    assert 0 <= healthy.latency_ms < 1000
    assert len(health_backend.saved_names) == 1
    assert health_backend.saved_names[0].startswith("system/dms/health/")
    assert health_backend.saved_content_names == ["probe.txt"]
    assert health_backend.open_modes == ["rb"]
    assert health_backend.read_sizes == [
        storage_module._policy_int(storage_module._policy_for_key(), "storage_stream_chunk_size"),
        1,
    ]
    assert health_backend.deleted_names == health_backend.saved_names

    cleanup_failure = MemoryStorage()
    cleanup_failure.fail_delete = True
    degraded = DjangoStorageAdapter(cleanup_failure).health_probe()
    assert degraded.healthy and degraded.status == "degraded" and not degraded.cleanup_ok
    assert degraded.detail == "cleanup_failed"
    assert 0 <= degraded.latency_ms < 1000

    renamed = MemoryStorage()
    renamed.rename_to = "changed/health/key"
    integrity_failure = DjangoStorageAdapter(renamed).health_probe()
    assert not integrity_failure.healthy and integrity_failure.status == "unhealthy"
    assert integrity_failure.detail == "Storage backend changed the randomized health key."
    assert 0 <= integrity_failure.latency_ms < 1000

    corrupt = DjangoStorageAdapter(CorruptingSaveStorage()).health_probe()
    assert not corrupt.healthy and corrupt.status == "unhealthy"
    assert corrupt.detail == "Storage roundtrip integrity check failed."
    assert 0 <= corrupt.latency_ms < 1000

    unavailable = MemoryStorage()
    unavailable.fail_save = True
    unhealthy = DjangoStorageAdapter(unavailable).health_probe()
    assert not unhealthy.healthy and unhealthy.status == "unhealthy"
    assert 0 <= unhealthy.latency_ms < 1000
    assert len(unavailable.checked_names) == 3
    assert unavailable.checked_names == [unavailable.checked_names[0]] * 3


def test_health_probe_reports_failure_latency_in_milliseconds(monkeypatch):
    ticks = iter([10.0, 10.0001234])
    monkeypatch.setattr(storage_module.time, "monotonic", lambda: next(ticks))
    backend = MemoryStorage()
    backend.fail_save = True

    unhealthy = DjangoStorageAdapter(backend).health_probe()

    assert unhealthy.latency_ms == 0.123


def test_health_probe_reports_success_latency_in_milliseconds(monkeypatch):
    ticks = iter([20.0, 20.0001234])
    monkeypatch.setattr(storage_module.time, "monotonic", lambda: next(ticks))

    healthy = DjangoStorageAdapter(MemoryStorage()).health_probe()

    assert healthy.healthy
    assert healthy.latency_ms == 0.123


def test_health_cleanup_treats_missing_key_as_noop_success():
    assert DjangoStorageAdapter(MemoryStorage())._health_cleanup(None)


def test_health_cleanup_logs_failures_with_structured_context(caplog):
    backend = MemoryStorage()
    backend.fail_exists = True
    caplog.set_level("ERROR", logger=storage_module.logger.name)

    assert not DjangoStorageAdapter(backend)._health_cleanup("safe/key")

    assert caplog.messages == ["DMS storage health cleanup failed"]
    record = caplog.records[0]
    assert record.event == "dms.storage.health_cleanup"
    assert record.outcome == "failed"
    assert record.duration_ms == 0
    assert hasattr(record, "correlation_id")
    assert not hasattr(record, "XXcorrelation_idXX")
    assert record.exc_info is False


def test_storage_registry_default_resolves_to_django_adapter():
    with storage_module._registry_lock:
        original_backends = dict(storage_module._storage_backends)
        original_default = storage_module._default_backend_name
        storage_module._storage_backends.clear()
        storage_module._default_backend_name = "django"
    try:
        assert storage_module._default_backend_name == "django"
        assert isinstance(get_document_storage(), DjangoStorageAdapter)
        assert isinstance(storage_module._storage_backends["django"], DjangoStorageAdapter)
    finally:
        with storage_module._registry_lock:
            storage_module._storage_backends.clear()
            storage_module._storage_backends.update(original_backends)
            storage_module._default_backend_name = original_default


def test_storage_registry_preserves_history_and_fails_missing_backends():
    first = DjangoStorageAdapter(MemoryStorage())
    second = DjangoStorageAdapter(MemoryStorage())
    replacement = DjangoStorageAdapter(MemoryStorage())
    first.backend_name = "archive_one"
    second.backend_name = "archive_two"
    replacement.backend_name = "archive_two"
    configure_document_storage(first)
    register_storage_backend("archive_two", second)
    hyphenated = DjangoStorageAdapter(MemoryStorage())
    assert register_storage_backend("archive-two", hyphenated) is hyphenated
    assert get_document_storage("archive-two") is hyphenated
    assert get_document_storage() is first
    assert get_document_storage("archive_two") is second
    assert register_storage_backend("archive_two", replacement, replace=True) is replacement
    assert get_document_storage("archive_two") is replacement
    with pytest.raises(ValueError) as duplicate_error:
        register_storage_backend("archive_two", second)
    assert str(duplicate_error.value) == "Storage backend 'archive_two' is already registered."
    with pytest.raises((TypeError, ValueError)):
        register_storage_backend("bad/name", object())  # type: ignore[arg-type]
    with pytest.raises(TypeError) as invalid_adapter_error:
        register_storage_backend("invalid_adapter", object())  # type: ignore[arg-type]
    assert str(invalid_adapter_error.value) == "adapter must implement DocumentStoragePort"
    with pytest.raises(ValueError) as non_string_error:
        register_storage_backend(object(), second)  # type: ignore[arg-type]
    assert str(non_string_error.value) == "Storage backend name must be a bounded slug."
    with pytest.raises(ValueError, match="bounded slug"):
        register_storage_backend("_", second)
    with pytest.raises(ValueError, match="bounded slug"):
        register_storage_backend("-", second)
    with pytest.raises(StorageUnavailableError) as missing_error:
        get_document_storage("missing")
    assert str(missing_error.value) == "Storage backend 'missing' is not registered."


def test_storage_registry_enforces_configured_backend_name_length():
    policy = storage_module._policy_for_key()
    maximum = storage_module._policy_int(policy, "storage_backend_name_max_length")
    adapter = DjangoStorageAdapter(MemoryStorage())

    accepted = "a" * maximum
    rejected = "b" * (maximum + 1)

    assert register_storage_backend(accepted, adapter, replace=True) is adapter
    with pytest.raises(ValueError, match="bounded slug"):
        register_storage_backend(rejected, adapter, replace=True)


def test_configure_document_storage_uses_adapter_backend_name_and_default_resolution():
    adapter = DjangoStorageAdapter(MemoryStorage())
    adapter.backend_name = "primary_archive"
    configure_document_storage(adapter)
    assert get_document_storage() is adapter
    assert get_document_storage("primary_archive") is adapter
    explicit = DjangoStorageAdapter(MemoryStorage())
    explicit.backend_name = "adapter_archive"
    configure_document_storage(explicit, name="explicit_archive")
    assert get_document_storage() is explicit
    assert get_document_storage("explicit_archive") is explicit
    explicit_replacement = DjangoStorageAdapter(MemoryStorage())
    configure_document_storage(explicit_replacement, name="explicit_archive")
    assert get_document_storage() is explicit_replacement
    assert get_document_storage("explicit_archive") is explicit_replacement
    with pytest.raises(StorageUnavailableError, match="not registered"):
        get_document_storage("adapter_archive")
    with pytest.raises(ValueError) as nameless_error:
        configure_document_storage(NamelessStorageAdapter())  # type: ignore[arg-type]
    assert str(nameless_error.value) == "Storage backend name must be a bounded slug."
    invalid_name_adapter = DjangoStorageAdapter(MemoryStorage())
    invalid_name_adapter.backend_name = object()  # type: ignore[assignment]
    with pytest.raises(ValueError) as invalid_name_error:
        configure_document_storage(invalid_name_adapter)
    assert str(invalid_name_error.value) == "Storage backend name must be a bounded slug."


def test_single_pass_upload_rejects_non_bytes_and_second_consumption():
    content = storage_module._ValidatedHashingUpload(
        io.BytesIO(b"plain"),
        declared_size=5,
        max_size_bytes=5,
        declared_mime_type="text/plain",
    )
    assert b"".join(content.chunks()) == b"plain"
    with pytest.raises(StorageValidationError) as consumed_error:
        next(content.chunks())
    assert str(consumed_error.value) == "Upload streams may only be consumed once."

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
    with pytest.raises(StorageValidationError) as non_bytes_error:
        list(invalid.chunks())
    assert str(non_bytes_error.value) == "Upload stream must yield bytes."


def test_single_pass_upload_skips_empty_chunks_and_continues_after_inspection_window():
    class Chunked:
        name = "note.txt"

        def chunks(self, *, chunk_size: int):
            assert chunk_size == 3
            yield b""
            yield b"pla"
            yield b"in"
            yield b" text"

    policy = dict(storage_module._policy_for_key())
    policy["storage_stream_chunk_size"] = 3
    policy["content_inspection_window_bytes"] = 5
    content = storage_module._ValidatedHashingUpload(
        Chunked(),  # type: ignore[arg-type]
        declared_size=len(b"plain text"),
        max_size_bytes=20,
        declared_mime_type="text/plain",
        policy=policy,
    )

    assert b"".join(content.chunks(chunk_size=10)) == b"plain text"
    assert content.size_bytes == len(b"plain text")
    assert content.mime_type == "text/plain"


def test_single_pass_upload_inspects_only_configured_window_before_streaming_remainder():
    class Chunked:
        name = "note.txt"

        def chunks(self, *, chunk_size: int):
            del chunk_size
            yield b"pl"
            yield b"ain\x00tail"

    policy = dict(storage_module._policy_for_key())
    policy["content_inspection_window_bytes"] = 5
    content = storage_module._ValidatedHashingUpload(
        Chunked(),  # type: ignore[arg-type]
        declared_size=len(b"plain\x00tail"),
        max_size_bytes=20,
        declared_mime_type="text/plain",
        policy=policy,
    )

    assert b"".join(content.chunks()) == b"plain\x00tail"
    assert content.size_bytes == len(b"plain\x00tail")


def test_single_pass_upload_closes_source_iterator_after_validation_failure():
    class ClosingIterator:
        closed = False

        def __iter__(self):
            return self

        def __next__(self):
            return "not bytes"

        def close(self) -> None:
            self.closed = True

    class InvalidChunks:
        name = "bad.txt"

        def __init__(self) -> None:
            self.iterator = ClosingIterator()

        def chunks(self, *, chunk_size: int):
            del chunk_size
            yield from self.iterator

    invalid = InvalidChunks()
    content = storage_module._ValidatedHashingUpload(
        invalid,  # type: ignore[arg-type]
        declared_size=None,
        max_size_bytes=10,
        declared_mime_type="text/plain",
    )

    with pytest.raises(StorageValidationError):
        list(content.chunks())
    assert invalid.iterator.closed


def test_single_pass_upload_reports_exact_size_limit_errors():
    too_large = storage_module._ValidatedHashingUpload(
        io.BytesIO(b"plain"),
        declared_size=None,
        max_size_bytes=4,
        declared_mime_type="text/plain",
    )
    with pytest.raises(StorageValidationError) as limit_error:
        list(too_large.chunks())
    assert str(limit_error.value) == "Upload exceeds the permitted byte limit."

    declared_too_small = storage_module._ValidatedHashingUpload(
        io.BytesIO(b"plain"),
        declared_size=4,
        max_size_bytes=10,
        declared_mime_type="text/plain",
    )
    with pytest.raises(StorageValidationError) as declared_error:
        list(declared_too_small.chunks())
    assert str(declared_error.value) == "Declared upload size does not match measured bytes."

    declared_too_large = storage_module._ValidatedHashingUpload(
        io.BytesIO(b"plain"),
        declared_size=6,
        max_size_bytes=10,
        declared_mime_type="text/plain",
    )
    with pytest.raises(StorageValidationError) as finalized_error:
        list(declared_too_large.chunks())
    assert str(finalized_error.value) == "Declared upload size does not match measured bytes."
