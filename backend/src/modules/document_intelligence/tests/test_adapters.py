"""Executable contract tests for concrete local document adapters."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import BinaryIO

import pytest
from django.utils import timezone

from src.modules.document_intelligence.adapters import (
    MAX_DOCUMENT_BYTES,
    ClassificationResult,
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
    TrainingResult,
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
        adapter.classify(OversizedStream(), model, "classify")
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


def test_tesseract_schema_parser_rejects_gaps_and_bad_geometry() -> None:
    gap = (
        "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "1\t2\t0\t0\t100\t100\t-1\t\n"
    )
    with pytest.raises(InvalidProviderOutput, match="ordered from one"):
        LocalTesseractOCRAdapter._parse_tsv(gap, processing_time_ms=1)

    malformed = (
        "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "1\t1\t0\t0\t0\t100\t-1\t\n"
    )
    with pytest.raises(InvalidProviderOutput, match="width"):
        LocalTesseractOCRAdapter._parse_tsv(malformed, processing_time_ms=1)


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
