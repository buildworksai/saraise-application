"""Provider boundary, bounded-streaming, and non-leakage tests."""

from __future__ import annotations

import io
import subprocess
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.modules.document_intelligence.adapters import (
    MAX_DOCUMENT_BYTES,
    ClassificationResult,
    ClassificationScoreResult,
    DocumentDescriptor,
    InvalidProviderOutput,
    LocalTesseractOCRAdapter,
    OCRPageResult,
    OCRRequest,
    OCRResult,
    ProviderUnavailable,
    RegisteredProviderResolver,
    TemplateMatchResult,
    TrainingResult,
)
from src.modules.document_intelligence.events import publish_domain_event

from .factories import DeterministicClassifierAdapter, DeterministicOCRAdapter


class BoundedReadStream:
    """A non-seekable source that rejects attempts to materialize the body."""

    def __init__(self, size: int) -> None:
        self.remaining = size
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        if size < 0 or size > LocalTesseractOCRAdapter.CHUNK_SIZE:
            raise AssertionError("adapter attempted an unbounded read")
        self.read_sizes.append(size)
        length = min(self.remaining, size)
        self.remaining -= length
        return b"x" * length


def _valid_tsv() -> bytes:
    return (
        "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "1\t1\t0\t0\t1200\t1600\t-1\t\n"
        "5\t1\t10\t10\t100\t20\t95\tInvoice\n"
        "5\t1\t120\t10\t100\t20\t85\t1234\n"
    ).encode()


def test_local_ocr_streams_in_bounded_chunks_and_parses_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    source = BoundedReadStream(LocalTesseractOCRAdapter.CHUNK_SIZE * 2 + 17)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=_valid_tsv()),
    )
    adapter = LocalTesseractOCRAdapter(executable="/bin/sh")

    result = adapter.extract(source, OCRRequest("text", "tesseract"), "ignored-local-key")

    assert all(0 < size <= LocalTesseractOCRAdapter.CHUNK_SIZE for size in source.read_sizes)
    assert len(source.read_sizes) >= 3
    assert result.raw_text == "Invoice 1234"
    assert result.pages[0].width == 1200
    assert result.pages[0].height == 1600
    assert result.confidence == Decimal("0.9000")


def test_local_ocr_rejects_oversized_stream_before_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    process = pytest.MonkeyPatch()
    called = False

    def forbidden_run(*args: object, **kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("provider process must not run")

    monkeypatch.setattr(subprocess, "run", forbidden_run)
    adapter = LocalTesseractOCRAdapter(executable="/bin/sh")
    with pytest.raises(InvalidProviderOutput, match="50 MiB"):
        adapter.extract(
            BoundedReadStream(MAX_DOCUMENT_BYTES + 1),
            OCRRequest("text", "tesseract"),
            "oversized",
        )
    assert called is False
    process.undo()


def test_local_ocr_timeout_is_mapped_without_provider_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired("tesseract", 300, output=b"secret OCR output")

    monkeypatch.setattr(subprocess, "run", timeout)
    adapter = LocalTesseractOCRAdapter(executable="/bin/sh")
    from src.modules.document_intelligence.adapters import DependencyTimeout

    with pytest.raises(DependencyTimeout, match="timed out") as caught:
        adapter.extract(io.BytesIO(b"image"), OCRRequest("text", "tesseract"), "timeout")
    assert "secret OCR output" not in str(caught.value)


@pytest.mark.parametrize(
    "builder",
    [
        lambda: OCRPageResult(0, 100, 100, Decimal("0.5")),
        lambda: OCRPageResult(1, 100, 100, Decimal("NaN")),
        lambda: OCRResult((), Decimal("0.5"), 1, raw_text=""),
        lambda: ClassificationScoreResult("Invalid Category", Decimal("0.5")),
        lambda: ClassificationResult(
            (
                ClassificationScoreResult("invoice", Decimal("0.4")),
                ClassificationScoreResult("receipt", Decimal("0.9")),
            ),
            1,
        ),
        lambda: TrainingResult("local", "artifact", "not-a-checksum", Decimal("0.9")),
        lambda: TemplateMatchResult(None, Decimal("0.2")),
    ],
)
def test_provider_dtos_reject_malformed_or_unproven_results(builder: object) -> None:
    with pytest.raises(InvalidProviderOutput):
        builder()  # type: ignore[operator]


def test_document_descriptor_rejects_unsupported_mime_oversize_and_versionless_metadata() -> None:
    common = {
        "document_id": uuid.uuid4(),
        "document_version_id": uuid.uuid4(),
        "checksum": "a" * 64,
        "content_handle": "opaque",
    }
    with pytest.raises(ValueError, match="MIME"):
        DocumentDescriptor(**common, mime_type="text/plain", byte_size=12)
    with pytest.raises(ValueError, match="50 MiB"):
        DocumentDescriptor(**common, mime_type="application/pdf", byte_size=MAX_DOCUMENT_BYTES + 1)
    with pytest.raises(ValueError, match="checksum"):
        DocumentDescriptor(**{**common, "checksum": ""}, mime_type="application/pdf", byte_size=12)


def test_provider_registry_has_explicit_collision_and_no_fallback() -> None:
    registry = RegisteredProviderResolver()
    ocr = DeterministicOCRAdapter()
    classifier = DeterministicClassifierAdapter()
    registry.register_ocr("local", ocr)
    registry.register_classifier("classifier", classifier)

    assert registry.resolve_ocr(uuid.uuid4(), "local") is ocr
    assert registry.resolve_classifier(uuid.uuid4(), "classifier") is classifier
    with pytest.raises(ValueError, match="already registered"):
        registry.register_ocr("local", ocr)
    with pytest.raises(ProviderUnavailable, match="not configured"):
        registry.resolve_ocr(uuid.uuid4(), "unknown")


@pytest.mark.django_db
def test_event_payload_allowlist_prevents_content_or_credentials_from_reaching_outbox() -> None:
    secret = "signed-url-and-ocr-text"
    with pytest.raises(ValueError, match="non-allowlisted"):
        publish_domain_event(
            uuid.uuid4(),
            "document_intelligence.extraction.completed",
            "document_extraction",
            uuid.uuid4(),
            actor_id=uuid.uuid4(),
            payload={"status": "completed", "raw_text": secret},
        )
