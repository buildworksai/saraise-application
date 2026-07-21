"""Typed extension contracts for document-intelligence dependencies.

The domain never imports DMS persistence models or provider configuration
models.  Deployments install adapters through :func:`configure_adapters`, and
tests can inject the same protocols directly into services.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO, Mapping, Protocol, Sequence, runtime_checkable
from uuid import UUID

MAX_DOCUMENT_BYTES = 50 * 1024 * 1024
MAX_PAGES = 10_000
MAX_TEXT_CHARACTERS = 20_000_000
MAX_STRUCTURED_BYTES = 20_000_000
MAX_CATEGORIES = 1_000
ALLOWED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/tiff",
        "image/bmp",
    }
)
_CATEGORY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_SHA256_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


class AdapterError(RuntimeError):
    """Base error for a configured integration."""


class ProviderUnavailable(AdapterError):
    """A requested provider or gateway is not configured/ready."""


class InvalidProviderOutput(AdapterError):
    """A provider returned evidence that cannot be trusted."""


class DependencyTimeout(AdapterError):
    """A dependency exceeded its fixed operation deadline."""


class DependencyCircuitOpen(AdapterError):
    """A dependency circuit breaker rejected the request."""


def _decimal_confidence(value: object, field_name: str = "confidence") -> Decimal:
    if isinstance(value, bool):
        raise InvalidProviderOutput(f"{field_name} must be a finite number")
    try:
        confidence = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidProviderOutput(f"{field_name} must be a finite number") from exc
    if not confidence.is_finite() or confidence < 0 or confidence > 1:
        raise InvalidProviderOutput(f"{field_name} must be between 0 and 1")
    return confidence.quantize(Decimal("0.0001"))


def _json_size(value: object) -> int:
    """Return a deterministic conservative size without serializing secrets."""
    if value is None:
        return 0
    if isinstance(value, (str, bytes)):
        return len(value)
    if isinstance(value, Mapping):
        return sum(len(str(key)) + _json_size(item) for key, item in value.items())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return sum(_json_size(item) for item in value)
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidProviderOutput("provider output contains a non-finite number")
    return len(str(value))


@dataclass(frozen=True, slots=True)
class DependencyHealth:
    """Sanitized dependency state safe for readiness reporting."""

    available: bool
    code: str
    checked_at: object
    circuit_state: str = "closed"

    def __post_init__(self) -> None:
        if not self.code or len(self.code) > 64:
            raise ValueError("dependency health requires a bounded stable code")
        if self.circuit_state not in {"closed", "open", "half_open", "unknown"}:
            raise ValueError("invalid circuit state")


@dataclass(frozen=True, slots=True)
class DocumentDescriptor:
    """Tenant-validated DMS metadata; ``content_handle`` is opaque."""

    document_id: UUID
    document_version_id: UUID
    mime_type: str
    byte_size: int
    checksum: str
    content_handle: str
    page_count: int | None = None

    def __post_init__(self) -> None:
        if self.mime_type.lower() not in ALLOWED_MIME_TYPES:
            raise ValueError("unsupported document MIME type")
        if isinstance(self.byte_size, bool) or not 0 < self.byte_size <= MAX_DOCUMENT_BYTES:
            raise ValueError("document size must be between 1 byte and 50 MiB")
        if self.page_count is not None and (isinstance(self.page_count, bool) or not 0 < self.page_count <= MAX_PAGES):
            raise ValueError("document page count is invalid")
        if not _SHA256_PATTERN.fullmatch(self.checksum):
            raise ValueError("document checksum must be SHA-256")
        if not self.content_handle or len(self.content_handle) > 1000:
            raise ValueError("opaque content handle is required")


@dataclass(frozen=True, slots=True)
class OCRRequest:
    extraction_type: str
    engine: str
    template_id: UUID | None = None
    zones: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        if self.extraction_type not in {"text", "structured", "table", "zone"}:
            raise ValueError("invalid extraction type")
        if not self.engine or len(self.engine) > 50:
            raise ValueError("engine is required")


@dataclass(frozen=True, slots=True)
class OCRPageResult:
    page_number: int
    width: int
    height: int
    confidence: Decimal
    raw_text: str = ""
    structured_data: Mapping[str, object] = field(default_factory=dict)
    table_data: tuple[object, ...] = ()
    provider_metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.page_number, bool) or not 1 <= self.page_number <= MAX_PAGES:
            raise InvalidProviderOutput("page number is impossible")
        if isinstance(self.width, bool) or not 0 < self.width <= 1_000_000:
            raise InvalidProviderOutput("page width is invalid")
        if isinstance(self.height, bool) or not 0 < self.height <= 1_000_000:
            raise InvalidProviderOutput("page height is invalid")
        object.__setattr__(self, "confidence", _decimal_confidence(self.confidence))
        if len(self.raw_text) > MAX_TEXT_CHARACTERS:
            raise InvalidProviderOutput("page text exceeds the allowed bound")
        if not isinstance(self.structured_data, Mapping):
            raise InvalidProviderOutput("structured page output must be an object")
        if not isinstance(self.table_data, tuple):
            object.__setattr__(self, "table_data", tuple(self.table_data))
        if not isinstance(self.provider_metadata, Mapping):
            raise InvalidProviderOutput("provider metadata must be an object")
        if _json_size((self.structured_data, self.table_data, self.provider_metadata)) > MAX_STRUCTURED_BYTES:
            raise InvalidProviderOutput("page output exceeds the allowed bound")


@dataclass(frozen=True, slots=True)
class OCRResult:
    pages: tuple[OCRPageResult, ...]
    confidence: Decimal
    processing_time_ms: int
    raw_text: str | None = None
    structured_data: Mapping[str, object] | None = None
    table_data: tuple[object, ...] | None = None

    def __post_init__(self) -> None:
        if not self.pages or len(self.pages) > MAX_PAGES:
            raise InvalidProviderOutput("OCR result must include bounded page evidence")
        object.__setattr__(self, "confidence", _decimal_confidence(self.confidence))
        if isinstance(self.processing_time_ms, bool) or self.processing_time_ms < 0:
            raise InvalidProviderOutput("processing time is invalid")
        expected = list(range(1, len(self.pages) + 1))
        if [page.page_number for page in self.pages] != expected:
            raise InvalidProviderOutput("OCR pages must be complete, unique, and ordered from one")
        if self.raw_text is not None and len(self.raw_text) > MAX_TEXT_CHARACTERS:
            raise InvalidProviderOutput("OCR text exceeds the allowed bound")
        if self.structured_data is not None and not isinstance(self.structured_data, Mapping):
            raise InvalidProviderOutput("structured output must be an object")
        if self.table_data is not None and not isinstance(self.table_data, tuple):
            object.__setattr__(self, "table_data", tuple(self.table_data))
        if _json_size((self.structured_data, self.table_data)) > MAX_STRUCTURED_BYTES:
            raise InvalidProviderOutput("OCR output exceeds the allowed bound")


@dataclass(frozen=True, slots=True)
class ClassificationScoreResult:
    category: str
    confidence: Decimal

    def __post_init__(self) -> None:
        if not _CATEGORY_PATTERN.fullmatch(self.category):
            raise InvalidProviderOutput("classification category is invalid")
        object.__setattr__(self, "confidence", _decimal_confidence(self.confidence))


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    scores: tuple[ClassificationScoreResult, ...]
    processing_time_ms: int

    def __post_init__(self) -> None:
        if not self.scores or len(self.scores) > MAX_CATEGORIES:
            raise InvalidProviderOutput("classification must include bounded scores")
        if isinstance(self.processing_time_ms, bool) or self.processing_time_ms < 0:
            raise InvalidProviderOutput("processing time is invalid")
        categories = [score.category for score in self.scores]
        if len(categories) != len(set(categories)):
            raise InvalidProviderOutput("classification categories must be unique")
        confidences = [score.confidence for score in self.scores]
        if confidences != sorted(confidences, reverse=True):
            raise InvalidProviderOutput("classification scores must be ordered by confidence")


@dataclass(frozen=True, slots=True)
class TrainingResult:
    provider_key: str
    artifact_ref: str
    artifact_checksum: str
    accuracy: Decimal

    def __post_init__(self) -> None:
        if not self.provider_key or len(self.provider_key) > 80:
            raise InvalidProviderOutput("training provider key is invalid")
        if not self.artifact_ref or len(self.artifact_ref) > 500:
            raise InvalidProviderOutput("training artifact reference is invalid")
        if not _SHA256_PATTERN.fullmatch(self.artifact_checksum):
            raise InvalidProviderOutput("training artifact checksum is invalid")
        object.__setattr__(self, "accuracy", _decimal_confidence(self.accuracy, "accuracy"))


@dataclass(frozen=True, slots=True)
class TemplateMatchResult:
    template_id: UUID | None
    confidence: Decimal
    processing_time_ms: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence", _decimal_confidence(self.confidence))
        if isinstance(self.processing_time_ms, bool) or self.processing_time_ms < 0:
            raise InvalidProviderOutput("processing time is invalid")
        if self.template_id is None and self.confidence != Decimal("0.0000"):
            raise InvalidProviderOutput("an unmatched template cannot carry confidence")


@runtime_checkable
class DMSGateway(Protocol):
    def get_document(self, tenant_id: UUID, document_id: UUID, document_version_id: UUID) -> DocumentDescriptor: ...
    def open_content(self, tenant_id: UUID, document_id: UUID, document_version_id: UUID) -> BinaryIO: ...
    def health(self) -> DependencyHealth: ...


@runtime_checkable
class OCRAdapter(Protocol):
    def extract(self, content: BinaryIO, request: OCRRequest, idempotency_key: str) -> OCRResult: ...
    def match(self, content: BinaryIO, templates: Sequence[object], idempotency_key: str) -> TemplateMatchResult: ...
    def health(self) -> DependencyHealth: ...


@runtime_checkable
class ClassifierAdapter(Protocol):
    def classify(self, content: BinaryIO, model: object, idempotency_key: str) -> ClassificationResult: ...

    def train(
        self, training_items: Sequence[Mapping[str, object]], requested_version: str, idempotency_key: str
    ) -> TrainingResult: ...

    def validate_artifact(self, artifact_ref: str, checksum: str) -> bool: ...
    def health(self) -> DependencyHealth: ...


@runtime_checkable
class ProviderResolver(Protocol):
    def resolve_ocr(self, tenant_id: UUID, engine: str) -> OCRAdapter: ...
    def resolve_classifier(self, tenant_id: UUID, provider_key: str) -> ClassifierAdapter: ...


class LocalTesseractOCRAdapter:
    """Local streaming Tesseract adapter with bounded execution and evidence.

    Input is copied to a private temporary file in chunks so a 50 MiB document
    is never accumulated in the API process.  Tesseract TSV output supplies
    page geometry, page numbers, recognized tokens, and provider confidence.
    Unsupported extraction modes fail explicitly rather than manufacturing
    structured or table output.
    """

    CHUNK_SIZE = 1024 * 1024
    TIMEOUT_SECONDS = 300

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("tesseract") or ""

    def health(self) -> DependencyHealth:
        from django.utils import timezone

        available = bool(self.executable and os.path.isfile(self.executable) and os.access(self.executable, os.X_OK))
        return DependencyHealth(
            available,
            "ready" if available else "runtime_unavailable",
            timezone.now(),
            "closed" if available else "unknown",
        )

    def extract(self, content: BinaryIO, request: OCRRequest, idempotency_key: str) -> OCRResult:
        del idempotency_key  # local execution has no remote side effect
        if not self.health().available:
            raise ProviderUnavailable("local OCR runtime is unavailable")
        if request.extraction_type != "text":
            raise ProviderUnavailable("local OCR supports text extraction only")

        temporary_path = ""
        started = time.monotonic()
        try:
            with tempfile.NamedTemporaryFile(prefix="saraise-ocr-", delete=False) as temporary:
                temporary_path = temporary.name
                total = 0
                while True:
                    chunk = content.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        raise InvalidProviderOutput("document content stream returned non-byte data")
                    total += len(chunk)
                    if total > MAX_DOCUMENT_BYTES:
                        raise InvalidProviderOutput("document content exceeds 50 MiB")
                    temporary.write(chunk)
                if total == 0:
                    raise InvalidProviderOutput("document content is empty")

            try:
                completed = subprocess.run(
                    [self.executable, temporary_path, "stdout", "tsv"],
                    check=False,
                    capture_output=True,
                    timeout=self.TIMEOUT_SECONDS,
                    env={"PATH": os.environ.get("PATH", "")},
                )
            except subprocess.TimeoutExpired as exc:
                raise DependencyTimeout("local OCR timed out") from exc
            if completed.returncode != 0:
                raise InvalidProviderOutput("local OCR did not produce valid page evidence")
            try:
                tsv = completed.stdout.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise InvalidProviderOutput("local OCR returned invalid UTF-8 evidence") from exc
            if len(tsv) > MAX_TEXT_CHARACTERS * 2:
                raise InvalidProviderOutput("local OCR evidence exceeds the allowed bound")
            elapsed_ms = max(1, round((time.monotonic() - started) * 1000))
            return self._parse_tsv(tsv, processing_time_ms=elapsed_ms)
        finally:
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass

    def match(
        self,
        content: BinaryIO,
        templates: Sequence[object],
        idempotency_key: str,
    ) -> TemplateMatchResult:
        del content, templates, idempotency_key
        raise ProviderUnavailable("local OCR does not provide template matching")

    @staticmethod
    def _parse_tsv(tsv: str, *, processing_time_ms: int) -> OCRResult:
        rows = csv.DictReader(io.StringIO(tsv), delimiter="\t")
        pages: dict[int, dict[str, object]] = {}
        all_confidences: list[Decimal] = []
        for row in rows:
            try:
                page_number = int(row.get("page_num") or "0")
                level = int(row.get("level") or "0")
                width = int(row.get("width") or "0")
                height = int(row.get("height") or "0")
            except ValueError as exc:
                raise InvalidProviderOutput("local OCR returned malformed page evidence") from exc
            if page_number <= 0:
                continue
            state = pages.setdefault(page_number, {"width": 0, "height": 0, "tokens": [], "confidence": []})
            if level == 1:
                state["width"] = width
                state["height"] = height
            token = (row.get("text") or "").strip()
            confidence_raw = row.get("conf") or "-1"
            try:
                confidence_percent = Decimal(confidence_raw)
            except InvalidOperation as exc:
                raise InvalidProviderOutput("local OCR returned malformed confidence evidence") from exc
            if token and confidence_percent >= 0:
                confidence = _decimal_confidence(confidence_percent / Decimal("100"))
                state["tokens"].append(token)  # type: ignore[union-attr]
                state["confidence"].append(confidence)  # type: ignore[union-attr]
                all_confidences.append(confidence)

        if not pages:
            raise InvalidProviderOutput("local OCR returned no page evidence")
        result_pages: list[OCRPageResult] = []
        for page_number in sorted(pages):
            state = pages[page_number]
            confidences = state["confidence"]
            if not isinstance(confidences, list):
                raise InvalidProviderOutput("local OCR confidence evidence is malformed")
            page_confidence = sum(confidences, Decimal("0")) / len(confidences) if confidences else Decimal("0")
            tokens = state["tokens"]
            if not isinstance(tokens, list):
                raise InvalidProviderOutput("local OCR text evidence is malformed")
            result_pages.append(
                OCRPageResult(
                    page_number=page_number,
                    width=int(state["width"]),
                    height=int(state["height"]),
                    raw_text=" ".join(str(token) for token in tokens),
                    confidence=page_confidence,
                    provider_metadata={"provider": "tesseract", "evidence": "tsv"},
                )
            )
        overall = sum(all_confidences, Decimal("0")) / len(all_confidences) if all_confidences else Decimal("0")
        raw_text = "\n\n".join(page.raw_text for page in result_pages)
        return OCRResult(
            pages=tuple(result_pages),
            confidence=overall,
            processing_time_ms=processing_time_ms,
            raw_text=raw_text,
        )


class LocalNaiveBayesClassifierAdapter:
    """Bounded OSS byte-feature classifier with tenant-isolated artifacts.

    It uses deterministic hashed byte trigrams, so it works for every allowed
    DMS MIME type without parsing document content into logs or job payloads.
    Training streams each tenant-owned version from DMS.  Artifacts are written
    atomically to a tenant directory and addressed by an opaque ``local://``
    reference; callers validate the SHA-256 before activation and inference.
    """

    PROVIDER_KEY = "local_naive_bayes"
    FEATURE_BUCKETS = 1024
    MAX_CATEGORIES = 100
    CHUNK_SIZE = 1024 * 1024

    def __init__(
        self,
        *,
        tenant_id: UUID | None = None,
        dms_gateway: DMSGateway | None = None,
        artifact_root: Path | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.dms_gateway = dms_gateway
        self.artifact_root = artifact_root or Path(
            os.environ.get("SARAISE_LOCAL_MODEL_DIR", "/tmp/saraise-document-intelligence-models")
        )

    def for_tenant(self, tenant_id: UUID) -> "LocalNaiveBayesClassifierAdapter":
        return type(self)(tenant_id=tenant_id, dms_gateway=get_dms_gateway(), artifact_root=self.artifact_root)

    def health(self) -> DependencyHealth:
        from django.utils import timezone

        gateway = self.dms_gateway or get_dms_gateway()
        try:
            dms_ready = gateway.health().available
        except Exception:
            dms_ready = False
        parent = self.artifact_root if self.artifact_root.exists() else self.artifact_root.parent
        writable = parent.exists() and os.access(parent, os.W_OK)
        ready = dms_ready and writable
        return DependencyHealth(ready, "ready" if ready else "runtime_unavailable", timezone.now())

    def train(
        self,
        training_items: Sequence[Mapping[str, object]],
        requested_version: str,
        idempotency_key: str,
    ) -> TrainingResult:
        del idempotency_key
        tenant_id, gateway = self._dependencies()
        categories = sorted({str(item.get("category", "")) for item in training_items})
        if (
            not categories
            or len(categories) > self.MAX_CATEGORIES
            or any(not _CATEGORY_PATTERN.fullmatch(item) for item in categories)
        ):
            raise InvalidProviderOutput("training categories are invalid or exceed the local provider bound")
        category_documents: Counter[str] = Counter()
        feature_counts: dict[str, Counter[int]] = defaultdict(Counter)
        totals: Counter[str] = Counter()
        for item in training_items:
            category = str(item["category"])
            try:
                document_id = UUID(str(item["document_id"]))
                version_id = UUID(str(item["document_version_id"]))
            except (KeyError, ValueError, TypeError, AttributeError) as exc:
                raise InvalidProviderOutput("training item contains invalid document identifiers") from exc
            gateway.get_document(tenant_id, document_id, version_id)
            content = gateway.open_content(tenant_id, document_id, version_id)
            with closing_binary(content):
                features = self._features(content)
            category_documents[category] += 1
            feature_counts[category].update(features)
            totals[category] += sum(features.values())
        document_total = sum(category_documents.values())
        model = {
            "schema_version": 1,
            "provider_key": self.PROVIDER_KEY,
            "requested_version": requested_version,
            "feature_buckets": self.FEATURE_BUCKETS,
            "document_total": document_total,
            "categories": {
                category: {
                    "documents": category_documents[category],
                    "total_features": totals[category],
                    "features": {str(key): value for key, value in sorted(feature_counts[category].items())},
                }
                for category in categories
            },
        }
        serialized = json.dumps(model, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(serialized) > MAX_STRUCTURED_BYTES:
            raise InvalidProviderOutput("local classifier artifact exceeds the allowed bound")
        checksum = hashlib.sha256(serialized).hexdigest()
        artifact_id = uuid.uuid4()
        tenant_dir = self.artifact_root / str(tenant_id)
        tenant_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = tenant_dir / f"{artifact_id}.json"
        temporary = tenant_dir / f".{artifact_id}.tmp"
        with temporary.open("xb") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        # Resubstitution accuracy is measured against every streamed training
        # document; no confidence or quality field is synthesized.
        correct = 0
        for item in training_items:
            document_id = UUID(str(item["document_id"]))
            version_id = UUID(str(item["document_version_id"]))
            content = gateway.open_content(tenant_id, document_id, version_id)
            with closing_binary(content):
                predicted, _ = self._predict(self._features(content), model)
            if predicted == str(item["category"]):
                correct += 1
        accuracy = Decimal(correct) / Decimal(document_total)
        return TrainingResult(self.PROVIDER_KEY, f"local://{artifact_id}", checksum, accuracy)

    def classify(self, content: BinaryIO, model: object, idempotency_key: str) -> ClassificationResult:
        del idempotency_key
        started = time.monotonic()
        artifact_ref = str(getattr(model, "artifact_ref", ""))
        checksum = str(getattr(model, "artifact_checksum", ""))
        loaded = self._load(artifact_ref, checksum)
        features = self._features(content)
        _, scores = self._predict(features, loaded)
        elapsed_ms = max(1, round((time.monotonic() - started) * 1000))
        return ClassificationResult(
            tuple(ClassificationScoreResult(category, confidence) for category, confidence in scores),
            elapsed_ms,
        )

    def validate_artifact(self, artifact_ref: str, checksum: str) -> bool:
        try:
            self._load(artifact_ref, checksum)
        except (ProviderUnavailable, InvalidProviderOutput, OSError):
            return False
        return True

    def _dependencies(self) -> tuple[UUID, DMSGateway]:
        if self.tenant_id is None:
            raise ProviderUnavailable("local classifier is not bound to a tenant")
        gateway = self.dms_gateway or get_dms_gateway()
        if not gateway.health().available:
            raise ProviderUnavailable("DMS is unavailable for local classifier training")
        return self.tenant_id, gateway

    def _artifact_path(self, artifact_ref: str) -> Path:
        if self.tenant_id is None:
            raise ProviderUnavailable("local classifier is not bound to a tenant")
        tenant_id = self.tenant_id
        if not artifact_ref.startswith("local://"):
            raise InvalidProviderOutput("local classifier artifact reference is invalid")
        try:
            artifact_id = UUID(artifact_ref.removeprefix("local://"))
        except ValueError as exc:
            raise InvalidProviderOutput("local classifier artifact reference is invalid") from exc
        return self.artifact_root / str(tenant_id) / f"{artifact_id}.json"

    def _load(self, artifact_ref: str, checksum: str) -> dict[str, object]:
        path = self._artifact_path(artifact_ref)
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise ProviderUnavailable("local classifier artifact is unavailable") from exc
        if len(content) > MAX_STRUCTURED_BYTES or hashlib.sha256(content).hexdigest() != checksum.lower():
            raise InvalidProviderOutput("local classifier artifact checksum is invalid")
        try:
            model = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidProviderOutput("local classifier artifact schema is invalid") from exc
        if (
            not isinstance(model, dict)
            or model.get("schema_version") != 1
            or not isinstance(model.get("categories"), dict)
        ):
            raise InvalidProviderOutput("local classifier artifact schema is invalid")
        return model

    def _features(self, content: BinaryIO) -> Counter[int]:
        counts: Counter[int] = Counter()
        previous = b""
        total = 0
        while True:
            chunk = content.read(self.CHUNK_SIZE)
            if not chunk:
                break
            if not isinstance(chunk, bytes):
                raise InvalidProviderOutput("document content stream returned non-byte data")
            total += len(chunk)
            if total > MAX_DOCUMENT_BYTES:
                raise InvalidProviderOutput("document content exceeds 50 MiB")
            data = previous + chunk
            for index in range(max(0, len(data) - 2)):
                digest = hashlib.blake2s(data[index : index + 3], digest_size=2).digest()
                counts[int.from_bytes(digest, "big") % self.FEATURE_BUCKETS] += 1
            previous = data[-2:]
        if total == 0:
            raise InvalidProviderOutput("document content is empty")
        return counts

    def _predict(
        self, features: Counter[int], model: Mapping[str, object]
    ) -> tuple[str, tuple[tuple[str, Decimal], ...]]:
        categories = model.get("categories")
        document_total = int(model.get("document_total", 0))
        if not isinstance(categories, Mapping) or not categories or document_total <= 0:
            raise InvalidProviderOutput("local classifier artifact contains no categories")
        log_scores: dict[str, float] = {}
        for category, raw in categories.items():
            if not isinstance(category, str) or not isinstance(raw, Mapping):
                raise InvalidProviderOutput("local classifier category evidence is invalid")
            documents = int(raw.get("documents", 0))
            total_features = int(raw.get("total_features", 0))
            saved = raw.get("features")
            if documents <= 0 or total_features < 0 or not isinstance(saved, Mapping):
                raise InvalidProviderOutput("local classifier category evidence is invalid")
            score = math.log(documents / document_total)
            denominator = total_features + self.FEATURE_BUCKETS
            for bucket, count in features.items():
                score += count * math.log((int(saved.get(str(bucket), 0)) + 1) / denominator)
            log_scores[category] = score
        maximum = max(log_scores.values())
        weights = {category: math.exp(score - maximum) for category, score in log_scores.items()}
        total_weight = sum(weights.values())
        ordered = tuple(
            sorted(
                ((category, _decimal_confidence(weight / total_weight)) for category, weight in weights.items()),
                key=lambda item: (-item[1], item[0]),
            )
        )
        return ordered[0][0], ordered


class closing_binary:
    """Close a DMS stream without suppressing provider exceptions."""

    def __init__(self, stream: BinaryIO) -> None:
        self.stream = stream

    def __enter__(self) -> BinaryIO:
        return self.stream

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.stream.close()


class RegisteredProviderResolver:
    """Thread-safe provider extension surface with no implicit fallback."""

    def __init__(self) -> None:
        self._ocr: dict[str, OCRAdapter] = {}
        self._classifiers: dict[str, ClassifierAdapter] = {}
        self._lock = threading.RLock()

    def register_ocr(self, engine: str, adapter: OCRAdapter, *, replace: bool = False) -> None:
        if not engine or len(engine) > 50 or not isinstance(adapter, OCRAdapter):
            raise ValueError("a valid OCR engine and adapter are required")
        with self._lock:
            if engine in self._ocr and not replace:
                raise ValueError(f"OCR adapter {engine!r} is already registered")
            self._ocr[engine] = adapter

    def register_classifier(self, provider_key: str, adapter: ClassifierAdapter, *, replace: bool = False) -> None:
        if not provider_key or len(provider_key) > 80 or not isinstance(adapter, ClassifierAdapter):
            raise ValueError("a valid classifier provider and adapter are required")
        with self._lock:
            if provider_key in self._classifiers and not replace:
                raise ValueError(f"classifier adapter {provider_key!r} is already registered")
            self._classifiers[provider_key] = adapter

    def resolve_ocr(self, tenant_id: UUID, engine: str) -> OCRAdapter:
        del tenant_id
        with self._lock:
            try:
                return self._ocr[engine]
            except KeyError as exc:
                raise ProviderUnavailable(f"OCR provider {engine!r} is not configured") from exc

    def resolve_classifier(self, tenant_id: UUID, provider_key: str) -> ClassifierAdapter:
        with self._lock:
            try:
                adapter = self._classifiers[provider_key]
            except KeyError as exc:
                raise ProviderUnavailable(f"classifier provider {provider_key!r} is not configured") from exc
        binder = getattr(adapter, "for_tenant", None)
        return binder(tenant_id) if callable(binder) else adapter

    def configured_ocr(self) -> Mapping[str, OCRAdapter]:
        with self._lock:
            return dict(self._ocr)

    def configured_classifiers(self) -> Mapping[str, ClassifierAdapter]:
        with self._lock:
            return dict(self._classifiers)


class _UnavailableGateway:
    def _raise(self) -> None:
        raise ProviderUnavailable("DMS gateway is not configured")

    def get_document(self, tenant_id: UUID, document_id: UUID, document_version_id: UUID) -> DocumentDescriptor:
        del tenant_id, document_id, document_version_id
        self._raise()

    def open_content(self, tenant_id: UUID, document_id: UUID, document_version_id: UUID) -> BinaryIO:
        del tenant_id, document_id, document_version_id
        self._raise()

    def health(self) -> DependencyHealth:
        from django.utils import timezone

        return DependencyHealth(False, "not_configured", timezone.now(), "unknown")


class _UnavailableResolver:
    def resolve_ocr(self, tenant_id: UUID, engine: str) -> OCRAdapter:
        del tenant_id, engine
        raise ProviderUnavailable("OCR provider is not configured")

    def resolve_classifier(self, tenant_id: UUID, provider_key: str) -> ClassifierAdapter:
        del tenant_id, provider_key
        raise ProviderUnavailable("classifier provider is not configured")


_adapter_lock = threading.RLock()
_dms_gateway: DMSGateway = _UnavailableGateway()
_default_resolver = RegisteredProviderResolver()
_default_resolver.register_ocr("tesseract", LocalTesseractOCRAdapter())
_default_resolver.register_classifier("local_naive_bayes", LocalNaiveBayesClassifierAdapter())
_provider_resolver: ProviderResolver = _default_resolver


def configure_adapters(*, dms_gateway: DMSGateway, provider_resolver: ProviderResolver) -> None:
    """Install validated integration adapters explicitly during application setup."""
    if not isinstance(dms_gateway, DMSGateway) or not isinstance(provider_resolver, ProviderResolver):
        raise TypeError("configured adapters do not satisfy document-intelligence protocols")
    global _dms_gateway, _provider_resolver
    with _adapter_lock:
        _dms_gateway = dms_gateway
        _provider_resolver = provider_resolver


def get_dms_gateway() -> DMSGateway:
    with _adapter_lock:
        return _dms_gateway


def get_provider_resolver() -> ProviderResolver:
    with _adapter_lock:
        return _provider_resolver


__all__ = [
    "ALLOWED_MIME_TYPES",
    "MAX_DOCUMENT_BYTES",
    "AdapterError",
    "ClassificationResult",
    "ClassificationScoreResult",
    "ClassifierAdapter",
    "DMSGateway",
    "DependencyCircuitOpen",
    "DependencyHealth",
    "DependencyTimeout",
    "DocumentDescriptor",
    "InvalidProviderOutput",
    "LocalTesseractOCRAdapter",
    "LocalNaiveBayesClassifierAdapter",
    "OCRAdapter",
    "OCRPageResult",
    "OCRRequest",
    "OCRResult",
    "ProviderResolver",
    "RegisteredProviderResolver",
    "ProviderUnavailable",
    "TemplateMatchResult",
    "TrainingResult",
    "configure_adapters",
    "get_dms_gateway",
    "get_provider_resolver",
]
