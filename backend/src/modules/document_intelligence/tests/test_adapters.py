"""Executable contract tests for concrete local document adapters."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import uuid
from collections import Counter
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import BinaryIO, cast

import pytest
from django.utils import timezone

from src.modules.document_intelligence.adapters import (
    MAX_DOCUMENT_BYTES,
    ClassificationResult,
    ClassificationScoreResult,
    DependencyCircuitOpen,
    DependencyHealth,
    DependencyTimeout,
    DocumentDescriptor,
    InvalidProviderOutput,
    LocalNaiveBayesClassifierAdapter,
    LocalTesseractOCRAdapter,
    OCRPageResult,
    OCRRequest,
    OCRResult,
    ProviderUnavailable,
    RegisteredProviderResolver,
    ResilienceExecutor,
    ResiliencePolicy,
    TrainingResult,
    configure_adapters,
    get_dms_gateway,
    get_provider_resolver,
)


class TenantContentGateway:
    """DMS test double that enforces tenant ownership on every read."""

    def __init__(self, tenant_id: uuid.UUID, documents: dict[tuple[uuid.UUID, uuid.UUID], bytes]) -> None:
        self.tenant_id = tenant_id
        self.documents = documents
        self.available = True
        self.opened: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]] = []

    def get_document(
        self,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
    ) -> DocumentDescriptor:
        if tenant_id != self.tenant_id:
            raise KeyError("tenant mismatch")
        content = self.documents[(document_id, document_version_id)]
        return DocumentDescriptor(
            document_id,
            document_version_id,
            "image/png",
            len(content),
            hashlib.sha256(content).hexdigest(),
            "opaque-test-handle",
            1,
        )

    def open_content(
        self,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
    ) -> BinaryIO:
        if tenant_id != self.tenant_id:
            raise KeyError("tenant mismatch")
        self.opened.append((tenant_id, document_id, document_version_id))
        return io.BytesIO(self.documents[(document_id, document_version_id)])

    def health(self) -> DependencyHealth:
        return DependencyHealth(self.available, "ready" if self.available else "unavailable", timezone.now())


def _training_graph() -> tuple[
    uuid.UUID,
    TenantContentGateway,
    list[dict[str, str]],
]:
    tenant_id = uuid.uuid4()
    documents: dict[tuple[uuid.UUID, uuid.UUID], bytes] = {}
    items: list[dict[str, str]] = []
    for category, signature in (("invoice", b"INVOICE TOTAL TAX NUMBER "), ("receipt", b"RECEIPT CASH CHANGE STORE ")):
        for index in range(5):
            document_id = uuid.uuid4()
            version_id = uuid.uuid4()
            documents[(document_id, version_id)] = signature * (20 + index)
            items.append(
                {
                    "document_id": str(document_id),
                    "document_version_id": str(version_id),
                    "category": category,
                }
            )
    return tenant_id, TenantContentGateway(tenant_id, documents), items


def test_document_descriptor_enforces_exact_fifty_mib_size_boundary() -> None:
    checksum = hashlib.sha256(b"boundary").hexdigest()

    descriptor = DocumentDescriptor(
        uuid.uuid4(),
        uuid.uuid4(),
        "image/png",
        50 * 1024 * 1024,
        checksum,
        "opaque-test-handle",
        1,
    )

    assert descriptor.byte_size == 50 * 1024 * 1024
    with pytest.raises(ValueError, match="50 MiB"):
        DocumentDescriptor(
            uuid.uuid4(),
            uuid.uuid4(),
            "image/png",
            50 * 1024 * 1024 + 1,
            checksum,
            "opaque-test-handle",
            1,
        )


def test_local_classifier_trains_classifies_and_validates_real_artifact(tmp_path: Path) -> None:
    tenant_id, gateway, items = _training_graph()
    adapter = LocalNaiveBayesClassifierAdapter(
        tenant_id=tenant_id,
        dms_gateway=gateway,
        artifact_root=tmp_path,
    )

    trained = adapter.train(items, "2026.1", "provider-idempotency")

    assert isinstance(trained, TrainingResult)
    assert trained.provider_key == "local_naive_bayes"
    assert trained.artifact_ref.startswith("local://")
    assert trained.accuracy >= Decimal("0.8000")
    assert adapter.validate_artifact(trained.artifact_ref, trained.artifact_checksum) is True
    # Training performs one feature pass and one measured accuracy pass.
    assert len(gateway.opened) == len(items) * 2

    result = adapter.classify(
        io.BytesIO(b"INVOICE NUMBER TOTAL TAX " * 30),
        SimpleNamespace(
            artifact_ref=trained.artifact_ref,
            artifact_checksum=trained.artifact_checksum,
        ),
        "classify-idempotency",
    )
    assert isinstance(result, ClassificationResult)
    assert result.scores[0].category == "invoice"
    assert result.scores[0].confidence >= result.scores[1].confidence
    assert result.processing_time_ms > 0


def test_local_classifier_stage_publish_and_abort_artifact_lifecycle(tmp_path: Path) -> None:
    tenant_id, gateway, items = _training_graph()
    adapter = LocalNaiveBayesClassifierAdapter(
        tenant_id=tenant_id,
        dms_gateway=gateway,
        artifact_root=tmp_path,
    )

    staged = adapter.stage_training(items, "2026.staged", "stage")
    artifact_id = uuid.UUID(staged.artifact_ref.removeprefix("local://"))
    tenant_dir = tmp_path / str(tenant_id)
    staged_path = tenant_dir / f".{artifact_id}.staged"
    published_path = tenant_dir / f"{artifact_id}.json"

    assert staged_path.exists()
    assert not published_path.exists()
    assert adapter.validate_artifact(staged.artifact_ref, staged.artifact_checksum) is True

    adapter.publish_artifact(staged.artifact_ref, staged.artifact_checksum)

    assert published_path.exists()
    assert not staged_path.exists()
    assert adapter.validate_artifact(staged.artifact_ref, staged.artifact_checksum) is True

    staged_for_abort = adapter.stage_training(items, "2026.abort", "stage")
    abort_id = uuid.UUID(staged_for_abort.artifact_ref.removeprefix("local://"))
    abort_staged_path = tenant_dir / f".{abort_id}.staged"
    assert abort_staged_path.exists()

    adapter.abort_artifact(staged_for_abort.artifact_ref)

    assert not abort_staged_path.exists()
    assert adapter.validate_artifact(staged_for_abort.artifact_ref, staged_for_abort.artifact_checksum) is False


def test_local_classifier_artifacts_are_tenant_isolated_and_checksum_guarded(tmp_path: Path) -> None:
    tenant_id, gateway, items = _training_graph()
    adapter = LocalNaiveBayesClassifierAdapter(
        tenant_id=tenant_id,
        dms_gateway=gateway,
        artifact_root=tmp_path,
    )
    trained = adapter.train(items, "2026.2", "train")
    foreign = adapter.for_tenant(uuid.uuid4())

    assert foreign.validate_artifact(trained.artifact_ref, trained.artifact_checksum) is False
    assert adapter.validate_artifact(trained.artifact_ref, "0" * 64) is False

    artifact_id = uuid.UUID(trained.artifact_ref.removeprefix("local://"))
    path = tmp_path / str(tenant_id) / f"{artifact_id}.json"
    path.write_bytes(path.read_bytes() + b"tampered")
    assert adapter.validate_artifact(trained.artifact_ref, trained.artifact_checksum) is False


def test_local_classifier_rejects_foreign_training_references_before_opening(tmp_path: Path) -> None:
    tenant_id, gateway, items = _training_graph()
    adapter = LocalNaiveBayesClassifierAdapter(
        tenant_id=uuid.uuid4(),
        dms_gateway=gateway,
        artifact_root=tmp_path,
    )

    with pytest.raises(KeyError, match="tenant mismatch"):
        adapter.train(items, "foreign", "train")
    assert gateway.opened == []


def test_local_classifier_rejects_malformed_category_and_artifact_schema(tmp_path: Path) -> None:
    tenant_id, gateway, items = _training_graph()
    adapter = LocalNaiveBayesClassifierAdapter(
        tenant_id=tenant_id,
        dms_gateway=gateway,
        artifact_root=tmp_path,
    )
    malformed = [dict(items[0], category="Not Valid")]
    with pytest.raises(InvalidProviderOutput, match="categories"):
        adapter.train(malformed, "invalid", "train")

    artifact_id = uuid.uuid4()
    tenant_dir = tmp_path / str(tenant_id)
    tenant_dir.mkdir()
    content = json.dumps({"schema_version": 1, "categories": []}).encode()
    (tenant_dir / f"{artifact_id}.json").write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    assert adapter.validate_artifact(f"local://{artifact_id}", checksum) is False


def test_local_classifier_rejects_invalid_artifact_fields_and_missing_roots(tmp_path: Path) -> None:
    tenant_id, gateway, _ = _training_graph()
    adapter = LocalNaiveBayesClassifierAdapter(
        tenant_id=tenant_id,
        dms_gateway=gateway,
        artifact_root=tmp_path,
    )
    adapter.feature_buckets = 1
    tenant_dir = tmp_path / str(tenant_id)
    tenant_dir.mkdir()
    invalid_models = [
        {"schema_version": 1, "document_total": True, "categories": {"invoice": {}}},
        {
            "schema_version": 1,
            "document_total": 1,
            "categories": {"invoice": {"documents": True, "total_features": 0, "features": {}}},
        },
        {
            "schema_version": 1,
            "document_total": 1,
            "categories": {"invoice": {"documents": 1, "total_features": False, "features": {}}},
        },
        {
            "schema_version": 1,
            "document_total": 1,
            "categories": {"invoice": {"documents": 1, "total_features": 0, "features": {"0": True}}},
        },
    ]
    for index, model in enumerate(invalid_models):
        artifact_id = uuid.uuid4()
        content = json.dumps(model, sort_keys=True, separators=(",", ":")).encode()
        path = tenant_dir / f"{artifact_id}.json"
        path.write_bytes(content)
        checksum = hashlib.sha256(content).hexdigest()
        artifact_ref = f"local://{artifact_id}"
        assert adapter.validate_artifact(artifact_ref, checksum) is True
        with pytest.raises(InvalidProviderOutput):
            adapter.classify(
                io.BytesIO(b"INVOICE TOTAL"),
                SimpleNamespace(artifact_ref=artifact_ref, artifact_checksum=checksum),
                f"classify-{index}",
            )

    unconfigured = LocalNaiveBayesClassifierAdapter(tenant_id=tenant_id, dms_gateway=gateway)
    assert unconfigured.validate_artifact(f"local://{uuid.uuid4()}", "0" * 64) is False
    with pytest.raises(ProviderUnavailable, match="artifact root"):
        unconfigured.publish_artifact(f"local://{uuid.uuid4()}", "0" * 64)


class OversizedStream:
    def __init__(self) -> None:
        self.remaining = MAX_DOCUMENT_BYTES + 1

    def read(self, size: int = -1) -> bytes:
        assert 0 < size <= LocalNaiveBayesClassifierAdapter.CHUNK_SIZE
        length = min(size, self.remaining)
        self.remaining -= length
        return b"x" * length


def test_local_classifier_bounds_streams_and_health(tmp_path: Path) -> None:
    tenant_id, gateway, items = _training_graph()
    adapter = LocalNaiveBayesClassifierAdapter(
        tenant_id=tenant_id,
        dms_gateway=gateway,
        artifact_root=tmp_path,
    )
    trained = adapter.train(items, "bounded", "train")
    model = SimpleNamespace(artifact_ref=trained.artifact_ref, artifact_checksum=trained.artifact_checksum)

    with pytest.raises(InvalidProviderOutput, match="50 MiB"):
        adapter.classify(cast(BinaryIO, OversizedStream()), model, "classify")
    assert adapter.health().available is True
    gateway.available = False
    assert adapter.health().available is False


def test_resolver_binds_local_classifier_to_request_tenant(tmp_path: Path) -> None:
    tenant_id, gateway, _ = _training_graph()
    registry = RegisteredProviderResolver()
    registered = LocalNaiveBayesClassifierAdapter(dms_gateway=gateway, artifact_root=tmp_path)
    registry.register_classifier("local", registered)

    resolved = registry.resolve_classifier(tenant_id, "local")

    assert isinstance(resolved, LocalNaiveBayesClassifierAdapter)
    assert resolved is not registered
    assert resolved.tenant_id == tenant_id
    with pytest.raises(ProviderUnavailable, match="not configured"):
        registry.resolve_classifier(tenant_id, "missing")


def test_resolver_registers_ocr_and_rejects_invalid_protocols(tmp_path: Path) -> None:
    tenant_id, gateway, _ = _training_graph()
    registry = RegisteredProviderResolver()
    ocr = LocalTesseractOCRAdapter(executable="/bin/sh")
    classifier = LocalNaiveBayesClassifierAdapter(dms_gateway=gateway, artifact_root=tmp_path)

    registry.register_ocr("tesseract", ocr)
    assert registry.resolve_ocr(tenant_id, "tesseract") is ocr
    assert registry.configured_ocr()["tesseract"] is ocr
    assert "tesseract" in registry.configured_ocr()

    with pytest.raises(ValueError, match="OCR engine"):
        registry.register_ocr("", ocr)
    with pytest.raises(ValueError, match="OCR engine"):
        registry.register_ocr("broken", object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="classifier provider"):
        registry.register_classifier("", classifier)
    with pytest.raises(ValueError, match="classifier provider"):
        registry.register_classifier("broken", object())  # type: ignore[arg-type]


def test_resolver_duplicate_registration_requires_explicit_replace(tmp_path: Path) -> None:
    tenant_id, gateway, _ = _training_graph()
    registry = RegisteredProviderResolver()
    first_ocr = LocalTesseractOCRAdapter(executable="/bin/sh")
    replacement_ocr = LocalTesseractOCRAdapter(executable="/bin/echo")
    first_classifier = LocalNaiveBayesClassifierAdapter(dms_gateway=gateway, artifact_root=tmp_path)
    replacement_classifier = LocalNaiveBayesClassifierAdapter(dms_gateway=gateway, artifact_root=tmp_path)

    registry.register_ocr("tesseract", first_ocr)
    registry.register_classifier("local", first_classifier)

    with pytest.raises(ValueError, match="already registered"):
        registry.register_ocr("tesseract", replacement_ocr)
    with pytest.raises(ValueError, match="already registered"):
        registry.register_classifier("local", replacement_classifier)

    registry.register_ocr("tesseract", replacement_ocr, replace=True)
    registry.register_classifier("local", replacement_classifier, replace=True)

    assert registry.resolve_ocr(tenant_id, "tesseract") is replacement_ocr
    assert registry.configured_classifiers()["local"] is replacement_classifier


def test_configure_adapters_rejects_invalid_protocols_and_installs_valid_ones(tmp_path: Path) -> None:
    original_gateway = get_dms_gateway()
    original_resolver = get_provider_resolver()
    tenant_id, gateway, _ = _training_graph()
    resolver = RegisteredProviderResolver()
    resolver.register_classifier(
        "local",
        LocalNaiveBayesClassifierAdapter(dms_gateway=gateway, artifact_root=tmp_path),
    )

    try:
        with pytest.raises(TypeError, match="protocols"):
            configure_adapters(dms_gateway=object(), provider_resolver=resolver)  # type: ignore[arg-type]

        configure_adapters(dms_gateway=gateway, provider_resolver=resolver)

        assert get_dms_gateway() is gateway
        resolved = get_provider_resolver().resolve_classifier(tenant_id, "local")
        assert isinstance(resolved, LocalNaiveBayesClassifierAdapter)
        assert resolved.tenant_id == tenant_id
    finally:
        configure_adapters(dms_gateway=original_gateway, provider_resolver=original_resolver)


def test_tesseract_unavailable_mode_timeout_and_invalid_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    unavailable = LocalTesseractOCRAdapter(executable="/definitely/missing/tesseract")
    assert unavailable.health().available is False
    with pytest.raises(ProviderUnavailable, match="unavailable"):
        unavailable.extract(io.BytesIO(b"image"), OCRRequest("text", "tesseract"), "key")

    adapter = LocalTesseractOCRAdapter(executable="/bin/sh")
    with pytest.raises(ProviderUnavailable, match="text extraction only"):
        adapter.extract(io.BytesIO(b"image"), OCRRequest("table", "tesseract"), "key")

    def timeout(*args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired("tesseract", 300, output=b"private output")

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(DependencyTimeout) as caught:
        adapter.extract(io.BytesIO(b"image"), OCRRequest("text", "tesseract"), "key")
    assert "private output" not in str(caught.value)


def test_tesseract_runtime_configuration_and_success_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = LocalTesseractOCRAdapter(executable="/bin/sh")
    assert adapter.chunk_size == LocalTesseractOCRAdapter.CHUNK_SIZE
    assert adapter.timeout_seconds == float(LocalTesseractOCRAdapter.TIMEOUT_SECONDS)
    assert adapter.max_document_bytes == MAX_DOCUMENT_BYTES
    valid_configuration = {
        "limits": {"max_document_bytes": 1024, "max_text_characters": 2048},
        "resilience": {"stream_chunk_size_bytes": 64, "timeout_seconds": 2.5},
    }

    adapter.configure_runtime(valid_configuration)

    assert adapter.chunk_size == 64
    assert adapter.timeout_seconds == 2.5
    assert adapter.max_document_bytes == 1024
    assert adapter.max_text_characters == 2048

    with pytest.raises(ValueError) as invalid_timeout:
        adapter.configure_runtime(
            {
                "limits": {"max_document_bytes": 1024, "max_text_characters": 2048},
                "resilience": {"stream_chunk_size_bytes": 64, "timeout_seconds": True},
            }
        )
    assert str(invalid_timeout.value) == "validated adapter timeout is required"

    tsv = (
        "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "1\t1\t0\t0\t1200\t1600\t-1\t\n"
        "5\t1\t10\t10\t100\t20\t95\tInvoice\n"
        "5\t1\t120\t10\t100\t20\t85\tTotal\n"
    )
    result = LocalTesseractOCRAdapter._parse_tsv(tsv, processing_time_ms=3)

    assert result.raw_text == "Invoice Total"
    assert result.processing_time_ms == 3
    assert result.confidence == Decimal("0.9000")
    assert result.pages[0].page_number == 1
    assert result.pages[0].width == 1200
    assert result.pages[0].height == 1600
    assert result.pages[0].confidence == Decimal("0.9000")
    assert result.pages[0].provider_metadata == {"provider": "tesseract", "evidence": "tsv"}

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=2, stdout=b""))
    with pytest.raises(InvalidProviderOutput, match="page evidence"):
        adapter.extract(io.BytesIO(b"image"), OCRRequest("text", "tesseract"), "key")


def test_tesseract_extract_returns_validated_output_and_removes_temporary_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "tesseract"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o700)
    adapter = LocalTesseractOCRAdapter(executable=str(executable))
    seen_paths: list[Path] = []
    tsv = (
        "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "1\t1\t0\t0\t100\t100\t-1\t\n"
        "5\t1\t0\t0\t10\t10\t75\tPaid\n"
    )

    def completed(args: list[str], **kwargs: object) -> SimpleNamespace:
        del kwargs
        seen_paths.append(Path(args[1]))
        assert seen_paths[-1].exists()
        return SimpleNamespace(returncode=0, stdout=tsv.encode("utf-8"))

    monkeypatch.setattr(subprocess, "run", completed)

    result = adapter.extract(io.BytesIO(b"image-bytes"), OCRRequest("text", "tesseract"), "key")

    assert result.raw_text == "Paid"
    assert result.pages[0].confidence == Decimal("0.7500")
    assert seen_paths
    assert not seen_paths[0].exists()


def test_tesseract_schema_parser_rejects_gaps_and_bad_geometry() -> None:
    gap = "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n" "1\t2\t0\t0\t100\t100\t-1\t\n"
    with pytest.raises(InvalidProviderOutput, match="ordered from one"):
        LocalTesseractOCRAdapter._parse_tsv(gap, processing_time_ms=1)

    malformed = "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n" "1\t1\t0\t0\t0\t100\t-1\t\n"
    with pytest.raises(InvalidProviderOutput, match="width"):
        LocalTesseractOCRAdapter._parse_tsv(malformed, processing_time_ms=1)


def test_tesseract_schema_parser_rejects_malformed_rows_and_confidence() -> None:
    malformed_page = "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n" "x\t1\t0\t0\t100\t100\t-1\t\n"
    with pytest.raises(InvalidProviderOutput, match="malformed page evidence"):
        LocalTesseractOCRAdapter._parse_tsv(malformed_page, processing_time_ms=1)

    malformed_confidence = (
        "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "1\t1\t0\t0\t100\t100\t-1\t\n"
        "5\t1\t0\t0\t10\t10\tbad\tword\n"
    )
    with pytest.raises(InvalidProviderOutput, match="malformed confidence"):
        LocalTesseractOCRAdapter._parse_tsv(malformed_confidence, processing_time_ms=1)


def test_result_dtos_reject_unbounded_nested_and_non_finite_evidence() -> None:
    with pytest.raises(InvalidProviderOutput, match="non-finite"):
        OCRPageResult(
            1,
            100,
            100,
            Decimal("0.5"),
            structured_data={"value": float("inf")},
        )
    with pytest.raises(InvalidProviderOutput, match="allowed bound"):
        OCRResult(
            (OCRPageResult(1, 100, 100, Decimal("0.5")),),
            Decimal("0.5"),
            1,
            structured_data={"value": "x" * 20_000_001},
        )


def test_result_dtos_reject_ordering_duplicates_and_invalid_bounds() -> None:
    with pytest.raises(InvalidProviderOutput, match="unique"):
        OCRResult(
            (
                OCRPageResult(1, 100, 100, Decimal("0.5")),
                OCRPageResult(1, 100, 100, Decimal("0.5")),
            ),
            Decimal("0.5"),
            1,
        )
    with pytest.raises(InvalidProviderOutput, match="ordered"):
        ClassificationResult(
            (
                ClassificationScoreResult("invoice", Decimal("0.1")),
                ClassificationScoreResult("receipt", Decimal("0.9")),
            ),
            1,
        )
    with pytest.raises(InvalidProviderOutput, match="unique"):
        ClassificationResult(
            (
                ClassificationScoreResult("invoice", Decimal("0.9")),
                ClassificationScoreResult("invoice", Decimal("0.1")),
            ),
            1,
        )


def test_artifact_write_is_private_and_checksum_matches_exact_bytes(tmp_path: Path) -> None:
    tenant_id, gateway, items = _training_graph()
    adapter = LocalNaiveBayesClassifierAdapter(
        tenant_id=tenant_id,
        dms_gateway=gateway,
        artifact_root=tmp_path,
    )
    trained = adapter.train(items, "permissions", "train")
    artifact_id = uuid.UUID(trained.artifact_ref.removeprefix("local://"))
    path = tmp_path / str(tenant_id) / f"{artifact_id}.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == trained.artifact_checksum
    assert os.stat(path.parent).st_mode & 0o077 == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout_seconds": float("inf")},
        {"timeout_seconds": 0},
        {"max_attempts": True},
        {"initial_backoff_seconds": 2, "max_backoff_seconds": 1},
        {"jitter_ratio": 2},
        {"circuit_failure_threshold": False},
        {"circuit_recovery_seconds": 0},
    ],
)
def test_resilience_policy_rejects_invalid_tenant_runtime_values(kwargs: dict[str, object]) -> None:
    values = {
        "timeout_seconds": 1.0,
        "max_attempts": 2,
        "initial_backoff_seconds": 0.0,
        "max_backoff_seconds": 1.0,
        "jitter_ratio": 0.0,
        "circuit_failure_threshold": 2,
        "circuit_recovery_seconds": 1.0,
    }
    values.update(kwargs)

    with pytest.raises(ValueError):
        ResiliencePolicy(**values)  # type: ignore[arg-type]


def test_resilience_executor_retries_opens_and_recovers_circuit() -> None:
    clock = {"now": 0.0}
    slept: list[float] = []
    executor = ResilienceExecutor(
        monotonic=lambda: clock["now"],
        sleep=lambda seconds: slept.append(seconds),
        random_value=lambda: 0.0,
    )
    policy = ResiliencePolicy(
        timeout_seconds=1.0,
        max_attempts=2,
        initial_backoff_seconds=0.5,
        max_backoff_seconds=1.0,
        jitter_ratio=0.0,
        circuit_failure_threshold=2,
        circuit_recovery_seconds=10.0,
    )
    attempts = {"count": 0}

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ProviderUnavailable("temporary")
        return "ok"

    assert executor.execute("ocr:test", flaky, policy) == "ok"
    assert slept == [0.5]

    def always_down() -> str:
        raise ProviderUnavailable("down")

    with pytest.raises(ProviderUnavailable):
        executor.execute("ocr:open", always_down, policy)
    with pytest.raises(DependencyCircuitOpen):
        executor.execute("ocr:open", lambda: "blocked", policy)

    clock["now"] = 11.0
    assert executor.execute("ocr:open", lambda: "recovered", policy) == "recovered"

    with pytest.raises(ValueError):
        executor.execute("", lambda: "bad", policy)


def test_tesseract_extract_rejects_stream_utf8_and_size_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "tesseract"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o700)
    adapter = LocalTesseractOCRAdapter(executable=str(executable))
    adapter.max_document_bytes = 4
    adapter.chunk_size = 2

    with pytest.raises(InvalidProviderOutput, match="empty"):
        adapter.extract(io.BytesIO(b""), OCRRequest("text", "tesseract"), "key")
    with pytest.raises(InvalidProviderOutput, match="byte limit"):
        adapter.extract(io.BytesIO(b"12345"), OCRRequest("text", "tesseract"), "key")

    class TextStream:
        def read(self, size: int = -1) -> str:
            return "not-bytes"

    with pytest.raises(InvalidProviderOutput, match="non-byte"):
        adapter.extract(cast(BinaryIO, TextStream()), OCRRequest("text", "tesseract"), "key")

    adapter.max_document_bytes = 1024
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=b"\xff"),
    )
    with pytest.raises(InvalidProviderOutput, match="UTF-8"):
        adapter.extract(io.BytesIO(b"image"), OCRRequest("text", "tesseract"), "key")

    adapter.max_text_characters = 1
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=b"a" * 3),
    )
    with pytest.raises(InvalidProviderOutput, match="allowed bound"):
        adapter.extract(io.BytesIO(b"image"), OCRRequest("text", "tesseract"), "key")

    with pytest.raises(ProviderUnavailable, match="template matching"):
        adapter.match(io.BytesIO(b"image"), [], "key")


def test_local_classifier_runtime_configuration_and_dependency_guards(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tenant_id, gateway, items = _training_graph()
    adapter = LocalNaiveBayesClassifierAdapter(tenant_id=tenant_id, dms_gateway=gateway, artifact_root=tmp_path)
    configuration = {
        "limits": {"max_document_bytes": 1024, "max_structured_bytes": 4096},
        "providers": {"artifact_root_environment_variable": "DOCINTEL_ARTIFACT_ROOT"},
        "classifier": {"feature_buckets": 64, "provider_max_categories": 4},
        "resilience": {"stream_chunk_size_bytes": 8},
    }

    adapter.configure_runtime(configuration)

    assert adapter.feature_buckets == 64
    assert adapter.max_categories == 4
    assert adapter.chunk_size == 8
    assert adapter.max_document_bytes == 1024
    assert adapter.max_structured_bytes == 4096

    with pytest.raises(ValueError, match="configuration"):
        adapter.configure_runtime({**configuration, "limits": []})
    for section, field in (
        ("classifier", "feature_buckets"),
        ("classifier", "provider_max_categories"),
        ("resilience", "stream_chunk_size_bytes"),
        ("limits", "max_document_bytes"),
        ("limits", "max_structured_bytes"),
    ):
        invalid_configuration = {
            key: dict(value) if isinstance(value, dict) else value for key, value in configuration.items()
        }
        cast(dict[str, object], invalid_configuration[section])[field] = True
        with pytest.raises(InvalidProviderOutput) as invalid_runtime_field:
            adapter.configure_runtime(invalid_configuration)
        assert str(invalid_runtime_field.value) == f"{field} must be an integer"

    env_bound = LocalNaiveBayesClassifierAdapter(tenant_id=tenant_id, dms_gateway=gateway)
    monkeypatch.delenv("DOCINTEL_ARTIFACT_ROOT", raising=False)
    with pytest.raises(ProviderUnavailable, match="environment reference"):
        env_bound.configure_runtime(configuration)
    monkeypatch.setenv("DOCINTEL_ARTIFACT_ROOT", str(tmp_path))
    env_bound.configure_runtime(configuration)
    assert env_bound.artifact_root == tmp_path

    unbound = LocalNaiveBayesClassifierAdapter(dms_gateway=gateway, artifact_root=tmp_path)
    with pytest.raises(ProviderUnavailable, match="not bound"):
        unbound.stage_training(items, "unbound", "key")

    gateway.available = False
    with pytest.raises(ProviderUnavailable, match="DMS"):
        adapter.stage_training(items, "dms-down", "key")


def test_local_classifier_rejects_training_item_and_artifact_edge_cases(tmp_path: Path) -> None:
    tenant_id, gateway, items = _training_graph()
    adapter = LocalNaiveBayesClassifierAdapter(
        tenant_id=tenant_id,
        dms_gateway=gateway,
        artifact_root=tmp_path,
    )
    with pytest.raises(InvalidProviderOutput, match="document identifiers"):
        adapter.stage_training([{"category": "invoice", "document_id": "bad"}], "bad-id", "key")

    adapter.max_categories = 1
    with pytest.raises(InvalidProviderOutput, match="categories"):
        adapter.stage_training(items, "too-many-categories", "key")

    adapter.max_categories = 10
    adapter.max_structured_bytes = 1
    with pytest.raises(InvalidProviderOutput, match="artifact exceeds"):
        adapter.stage_training(items, "too-large", "key")

    with pytest.raises(InvalidProviderOutput, match="artifact reference"):
        adapter.classify(
            io.BytesIO(b"INVOICE"), SimpleNamespace(artifact_ref="remote://bad", artifact_checksum="0" * 64), "key"
        )

    artifact_id = uuid.uuid4()
    tenant_dir = tmp_path / str(tenant_id)
    tenant_dir.mkdir(exist_ok=True)
    bad_json = tenant_dir / f"{artifact_id}.json"
    bad_json.write_bytes(b"{")
    checksum = hashlib.sha256(b"{").hexdigest()
    with pytest.raises(InvalidProviderOutput, match="artifact schema"):
        adapter.classify(
            io.BytesIO(b"INVOICE"),
            SimpleNamespace(artifact_ref=f"local://{artifact_id}", artifact_checksum=checksum),
            "key",
        )


def test_local_classifier_rejects_empty_and_non_byte_streams(tmp_path: Path) -> None:
    tenant_id, gateway, items = _training_graph()
    adapter = LocalNaiveBayesClassifierAdapter(
        tenant_id=tenant_id,
        dms_gateway=gateway,
        artifact_root=tmp_path,
    )
    trained = adapter.train(items, "stream-validation", "train")
    model = SimpleNamespace(artifact_ref=trained.artifact_ref, artifact_checksum=trained.artifact_checksum)

    class TextStream:
        def read(self, size: int = -1) -> str:
            del size
            return "not-bytes"

    with pytest.raises(InvalidProviderOutput, match="empty"):
        adapter.classify(io.BytesIO(b""), model, "empty")
    with pytest.raises(InvalidProviderOutput, match="non-byte"):
        adapter.classify(cast(BinaryIO, TextStream()), model, "text")


def test_local_classifier_predict_validates_integer_artifact_fields_and_feature_weights(tmp_path: Path) -> None:
    tenant_id, gateway, _ = _training_graph()
    adapter = LocalNaiveBayesClassifierAdapter(
        tenant_id=tenant_id,
        dms_gateway=gateway,
        artifact_root=tmp_path,
    )
    adapter.feature_buckets = 4
    valid_model = {
        "document_total": 2,
        "categories": {
            "invoice": {"documents": 1, "total_features": 8, "features": {"0": 7}},
            "receipt": {"documents": 1, "total_features": 8, "features": {"0": 0}},
        },
    }

    category, scores = adapter._predict(Counter({0: 2}), valid_model)

    assert category == "invoice"
    assert scores[0] == ("invoice", Decimal("0.9846"))
    assert scores[1] == ("receipt", Decimal("0.0154"))
    uneven_denominator_model = {
        "document_total": 2,
        "categories": {
            "invoice": {"documents": 1, "total_features": 8, "features": {"0": 7}},
            "receipt": {"documents": 1, "total_features": 0, "features": {"0": 0}},
        },
    }
    category, scores = adapter._predict(Counter({0: 1}), uneven_denominator_model)
    assert category == "invoice"
    assert scores == (("invoice", Decimal("0.7273")), ("receipt", Decimal("0.2727")))
    prior_and_missing_feature_model = {
        "document_total": 4,
        "categories": {
            "invoice": {"documents": 3, "total_features": 9, "features": {"0": 8}},
            "receipt": {"documents": 1, "total_features": 9, "features": {"1": 8}},
        },
    }
    category, scores = adapter._predict(Counter({0: 1, 2: 1}), prior_and_missing_feature_model)
    assert category == "invoice"
    assert scores == (("invoice", Decimal("0.9643")), ("receipt", Decimal("0.0357")))
    missing_total_features_model = {
        "document_total": 2,
        "categories": {
            "invoice": {"documents": 1, "features": {"0": 1}},
            "receipt": {"documents": 1, "features": {}},
        },
    }
    assert adapter._predict(Counter({0: 1}), missing_total_features_model) == (
        "invoice",
        (("invoice", Decimal("0.6667")), ("receipt", Decimal("0.3333"))),
    )
    balanced_missing_total_features_model = {
        "document_total": 2,
        "categories": {
            "invoice": {"documents": 1, "features": {"0": 1}},
            "receipt": {"documents": 1, "total_features": 0, "features": {"0": 1}},
        },
    }
    assert adapter._predict(Counter({0: 1}), balanced_missing_total_features_model) == (
        "invoice",
        (("invoice", Decimal("0.5000")), ("receipt", Decimal("0.5000"))),
    )
    with pytest.raises(InvalidProviderOutput, match="no categories"):
        adapter._predict(Counter({0: 1}), {"categories": valid_model["categories"]})
    with pytest.raises(InvalidProviderOutput, match="category evidence"):
        adapter._predict(
            Counter({0: 1}),
            {"document_total": 2, "categories": {"invoice": {"total_features": 8, "features": {"0": 7}}}},
        )

    invalid_cases = [
        ("document_total", {"document_total": True, "categories": valid_model["categories"]}),
        (
            "documents",
            {
                "document_total": 2,
                "categories": {"invoice": {"documents": True, "total_features": 8, "features": {"0": 7}}},
            },
        ),
        (
            "total_features",
            {
                "document_total": 2,
                "categories": {"invoice": {"documents": 1, "total_features": False, "features": {"0": 7}}},
            },
        ),
        (
            "feature_count",
            {
                "document_total": 2,
                "categories": {"invoice": {"documents": 1, "total_features": 8, "features": {"0": True}}},
            },
        ),
    ]
    for field, model in invalid_cases:
        with pytest.raises(InvalidProviderOutput) as invalid_artifact_field:
            adapter._predict(Counter({0: 1}), model)
        assert str(invalid_artifact_field.value) == f"{field} must be an integer"


def test_local_classifier_publish_rejects_bad_checksum_and_abort_removes_published_artifact(tmp_path: Path) -> None:
    tenant_id, gateway, items = _training_graph()
    adapter = LocalNaiveBayesClassifierAdapter(
        tenant_id=tenant_id,
        dms_gateway=gateway,
        artifact_root=tmp_path,
    )
    staged = adapter.stage_training(items, "checksum-guard", "stage")

    with pytest.raises(InvalidProviderOutput, match="checksum"):
        adapter.publish_artifact(staged.artifact_ref, "0" * 64)

    assert adapter.validate_artifact(staged.artifact_ref, staged.artifact_checksum) is True
    adapter.publish_artifact(staged.artifact_ref, staged.artifact_checksum)
    assert adapter.validate_artifact(staged.artifact_ref, staged.artifact_checksum) is True

    adapter.abort_artifact(staged.artifact_ref)

    assert adapter.validate_artifact(staged.artifact_ref, staged.artifact_checksum) is False
