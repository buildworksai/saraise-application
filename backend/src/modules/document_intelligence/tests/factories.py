"""Typed factories and deterministic adapter evidence for module tests."""

from __future__ import annotations

import hashlib
import io
import uuid
from decimal import Decimal
from typing import BinaryIO, Mapping, Sequence

import factory
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, JobStatus
from src.modules.document_intelligence.adapters import (
    ClassificationResult,
    ClassificationScoreResult,
    DependencyHealth,
    DocumentDescriptor,
    OCRPageResult,
    OCRRequest,
    OCRResult,
    TemplateMatchResult,
    TrainingResult,
)
from src.modules.document_intelligence.models import (
    ClassificationReviewStatus,
    ClassificationStatus,
    ClassifierModelVersion,
    ClassifierTrainingJob,
    DocumentClassification,
    DocumentClassificationScore,
    DocumentExtraction,
    DocumentExtractionPage,
    ExpectedDataType,
    ExtractionStatus,
    ExtractionTemplate,
    ExtractionTemplateZone,
    ExtractionType,
    ModelVersionStatus,
    TemplateStatus,
    TrainingStatus,
    ZoneType,
)


def training_items(category_counts: Mapping[str, int] | None = None) -> list[dict[str, str]]:
    """Return valid, distinct DMS references for a training request."""

    counts = category_counts or {"invoice": 25, "receipt": 25}
    return [
        {
            "document_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"document:{category}:{index}")),
            "document_version_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"version:{category}:{index}")),
            "category": category,
        }
        for category, count in counts.items()
        for index in range(count)
    ]


class ExtractionTemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExtractionTemplate

    tenant_id = factory.LazyFunction(uuid.uuid4)
    created_by = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda number: f"Invoice template {number}")
    description = "Versioned invoice extraction configuration"
    document_category = "invoice"
    engine = "tesseract"
    match_threshold = Decimal("0.7000")
    status = TemplateStatus.DRAFT
    version = 1


class ExtractionTemplateZoneFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExtractionTemplateZone

    template = factory.SubFactory(ExtractionTemplateFactory)
    tenant_id = factory.SelfAttribute("template.tenant_id")
    created_by = factory.SelfAttribute("template.created_by")
    zone_name = factory.Sequence(lambda number: f"Invoice number {number}")
    extraction_key = factory.Sequence(lambda number: f"invoice_number_{number}")
    zone_type = ZoneType.TEXT
    x = Decimal("0.0500")
    y = Decimal("0.0500")
    width = Decimal("0.2000")
    height = Decimal("0.1000")
    page_number = 1
    expected_data_type = ExpectedDataType.STRING
    is_required = True


class DocumentExtractionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DocumentExtraction

    tenant_id = factory.LazyFunction(uuid.uuid4)
    created_by = factory.LazyFunction(uuid.uuid4)
    document_id = factory.LazyFunction(uuid.uuid4)
    document_version_id = factory.LazyFunction(uuid.uuid4)
    async_job_id = factory.LazyFunction(uuid.uuid4)
    idempotency_key = factory.LazyFunction(lambda: f"extract:{uuid.uuid4()}")
    engine = "tesseract"
    extraction_type = ExtractionType.TEXT
    status = ExtractionStatus.QUEUED


class CompletedDocumentExtractionFactory(DocumentExtractionFactory):
    status = ExtractionStatus.COMPLETED
    raw_text = "Verified OCR evidence"
    confidence = Decimal("0.9500")
    page_count = 1
    processing_time_ms = 125
    started_at = factory.LazyFunction(timezone.now)
    completed_at = factory.LazyFunction(timezone.now)


class DocumentExtractionPageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DocumentExtractionPage

    extraction = factory.SubFactory(CompletedDocumentExtractionFactory)
    tenant_id = factory.SelfAttribute("extraction.tenant_id")
    created_by = factory.SelfAttribute("extraction.created_by")
    page_number = 1
    width = 1200
    height = 1600
    raw_text = "Verified page evidence"
    structured_data = factory.LazyFunction(dict)
    table_data = factory.LazyFunction(list)
    confidence = Decimal("0.9500")
    provider_metadata = factory.LazyFunction(
        lambda: {"adapter_key": "tesseract", "adapter_version": "5", "result_checksum": "a" * 64}
    )


class ClassifierTrainingJobFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ClassifierTrainingJob

    tenant_id = factory.LazyFunction(uuid.uuid4)
    created_by = factory.LazyFunction(uuid.uuid4)
    async_job_id = factory.LazyFunction(uuid.uuid4)
    idempotency_key = factory.LazyFunction(lambda: f"train:{uuid.uuid4()}")
    name = factory.Sequence(lambda number: f"Invoice classifier {number}")
    training_items = factory.LazyFunction(training_items)
    training_data_count = 50
    category_counts = factory.LazyFunction(lambda: {"invoice": 25, "receipt": 25})
    requested_version = factory.Sequence(lambda number: f"2026.{number}")
    status = TrainingStatus.COMPLETED
    accuracy = Decimal("0.9500")
    started_at = factory.LazyFunction(timezone.now)
    completed_at = factory.LazyFunction(timezone.now)


class ClassifierModelVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ClassifierModelVersion

    training_job = factory.SubFactory(ClassifierTrainingJobFactory)
    tenant_id = factory.SelfAttribute("training_job.tenant_id")
    created_by = factory.SelfAttribute("training_job.created_by")
    version = factory.Sequence(lambda number: f"2026.{number}")
    provider_key = "local_classifier"
    artifact_ref = factory.LazyFunction(lambda: f"tenant-artifact://{uuid.uuid4()}")
    artifact_checksum = "a" * 64
    accuracy = Decimal("0.9500")
    status = ModelVersionStatus.CANDIDATE


class DocumentClassificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DocumentClassification

    model_version = factory.SubFactory(ClassifierModelVersionFactory)
    tenant_id = factory.SelfAttribute("model_version.tenant_id")
    created_by = factory.SelfAttribute("model_version.created_by")
    document_id = factory.LazyFunction(uuid.uuid4)
    document_version_id = factory.LazyFunction(uuid.uuid4)
    async_job_id = factory.LazyFunction(uuid.uuid4)
    idempotency_key = factory.LazyFunction(lambda: f"classify:{uuid.uuid4()}")
    status = ClassificationStatus.COMPLETED
    category = "invoice"
    confidence = Decimal("0.9000")
    secondary_category = "receipt"
    secondary_confidence = Decimal("0.3500")
    needs_review = False
    review_status = ClassificationReviewStatus.NOT_REQUIRED
    processing_time_ms = 80
    completed_at = factory.LazyFunction(timezone.now)


class DocumentClassificationScoreFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DocumentClassificationScore

    classification = factory.SubFactory(DocumentClassificationFactory)
    tenant_id = factory.SelfAttribute("classification.tenant_id")
    created_by = factory.SelfAttribute("classification.created_by")
    category = "invoice"
    confidence = Decimal("0.9000")
    rank = 1


class AsyncJobFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AsyncJob

    tenant_id = factory.LazyFunction(uuid.uuid4)
    actor_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    command = "document_intelligence.extract"
    status = JobStatus.QUEUED
    idempotency_key = factory.LazyFunction(lambda: f"job:{uuid.uuid4()}")
    payload = factory.LazyFunction(dict)
    correlation_id = factory.LazyFunction(lambda: f"test-{uuid.uuid4()}")


class DeterministicDMSGateway:
    """In-memory test gateway that still performs real streamed reads."""

    def __init__(self, content: bytes = b"document bytes", *, page_count: int = 1) -> None:
        self.content = content
        self.page_count = page_count
        self.open_count = 0

    def get_document(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID, document_version_id: uuid.UUID
    ) -> DocumentDescriptor:
        del tenant_id
        return DocumentDescriptor(
            document_id=document_id,
            document_version_id=document_version_id,
            mime_type="image/png",
            byte_size=len(self.content),
            page_count=self.page_count,
            checksum=hashlib.sha256(self.content).hexdigest(),
            content_handle="test-content",
        )

    def open_content(self, tenant_id: uuid.UUID, document_id: uuid.UUID, document_version_id: uuid.UUID) -> BinaryIO:
        del tenant_id, document_id, document_version_id
        self.open_count += 1
        return io.BytesIO(self.content)

    def health(self) -> DependencyHealth:
        return DependencyHealth(True, "ready", timezone.now())


class DeterministicOCRAdapter:
    """Adapter returning schema-validated evidence supplied by the test."""

    def __init__(self, result: OCRResult | None = None) -> None:
        self.result = result or OCRResult(
            pages=(
                OCRPageResult(
                    page_number=1,
                    width=1200,
                    height=1600,
                    confidence=Decimal("0.9500"),
                    raw_text="Verified OCR evidence",
                    provider_metadata={"adapter_key": "test_ocr"},
                ),
            ),
            confidence=Decimal("0.9500"),
            processing_time_ms=25,
            raw_text="Verified OCR evidence",
        )
        self.calls = 0

    def extract(self, content: BinaryIO, request: OCRRequest, idempotency_key: str) -> OCRResult:
        del request, idempotency_key
        content.read(1)
        self.calls += 1
        return self.result

    def match(self, content: BinaryIO, templates: Sequence[object], idempotency_key: str) -> TemplateMatchResult:
        del content, idempotency_key
        template_id = getattr(templates[0], "id", None) if templates else None
        return TemplateMatchResult(template_id=template_id, confidence=Decimal("0.9000"))

    def health(self) -> DependencyHealth:
        return DependencyHealth(True, "ready", timezone.now())


class DeterministicClassifierAdapter:
    def classify(self, content: BinaryIO, model: object, idempotency_key: str) -> ClassificationResult:
        del content, model, idempotency_key
        return ClassificationResult(
            scores=(
                ClassificationScoreResult("invoice", Decimal("0.9000")),
                ClassificationScoreResult("receipt", Decimal("0.3500")),
            ),
            processing_time_ms=20,
        )

    def train(
        self,
        items: Sequence[Mapping[str, object]],
        requested_version: str,
        idempotency_key: str,
    ) -> TrainingResult:
        del items, requested_version, idempotency_key
        return TrainingResult("local_classifier", "tenant-artifact://test", "a" * 64, Decimal("0.9500"))

    def validate_artifact(self, artifact_ref: str, checksum: str) -> bool:
        return artifact_ref.startswith("tenant-artifact://") and len(checksum) == 64

    def health(self) -> DependencyHealth:
        return DependencyHealth(True, "ready", timezone.now())


class DeterministicProviderResolver:
    def __init__(self) -> None:
        self.ocr = DeterministicOCRAdapter()
        self.classifier = DeterministicClassifierAdapter()

    def resolve_ocr(self, tenant_id: uuid.UUID, engine: str) -> DeterministicOCRAdapter:
        del tenant_id, engine
        return self.ocr

    def resolve_classifier(self, tenant_id: uuid.UUID, provider_key: str) -> DeterministicClassifierAdapter:
        del tenant_id, provider_key
        return self.classifier
