"""Executable service contracts for the document-intelligence domain.

These tests deliberately exercise durable rows, jobs, transition histories and
outbox events.  Adapter doubles return validated DTOs; they never manufacture a
success in the service under test.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.modules.document_intelligence.adapters import (
    DependencyTimeout,
    OCRPageResult,
    OCRResult,
    ProviderUnavailable,
    TemplateMatchResult,
)
from src.modules.document_intelligence.models import (
    ClassificationReviewStatus,
    ClassificationStatus,
    ClassifierModelVersion,
    ClassifierTrainingJob,
    DocumentExtraction,
    DocumentExtractionPage,
    ExtractionStatus,
    ExtractionTemplateZone,
    ExtractionType,
    ModelVersionStatus,
    TemplateStatus,
    TrainingStatus,
)
from src.modules.document_intelligence.services import (
    DocumentClassificationService,
    DocumentExtractionService,
    DocumentIntelligenceError,
    ProcessingFailure,
    TemplateMatchingService,
)

from .factories import (
    AsyncJobFactory,
    ClassifierModelVersionFactory,
    ClassifierTrainingJobFactory,
    CompletedDocumentExtractionFactory,
    DeterministicDMSGateway,
    DeterministicProviderResolver,
    DocumentExtractionFactory,
    ExtractionTemplateFactory,
    ExtractionTemplateZoneFactory,
    training_items,
)

pytestmark = pytest.mark.django_db


@dataclass
class AllowingEntitlements:
    calls: int = 0

    def check(self, tenant_id: uuid.UUID, capability: str) -> SimpleNamespace:
        assert isinstance(tenant_id, uuid.UUID)
        assert capability.startswith("document_intelligence.")
        self.calls += 1
        return SimpleNamespace(entitled=True)


@dataclass
class AllowingQuota:
    calls: int = 0
    total_cost: int = 0

    def consume(self, tenant_id: uuid.UUID, resource: str, *, cost: int) -> SimpleNamespace:
        assert isinstance(tenant_id, uuid.UUID)
        assert resource.startswith("document_intelligence.")
        self.calls += 1
        self.total_cost += cost
        return SimpleNamespace(allowed=True, remaining=10_000 - self.total_cost)


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def actor_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def dependencies() -> (
    tuple[DeterministicDMSGateway, DeterministicProviderResolver, AllowingEntitlements, AllowingQuota]
):
    return DeterministicDMSGateway(), DeterministicProviderResolver(), AllowingEntitlements(), AllowingQuota()


def extraction_service(
    dependencies: tuple[object, object, object, object], **kwargs: object
) -> DocumentExtractionService:
    dms, providers, entitlements, quota = dependencies
    return DocumentExtractionService(
        dms_gateway=dms,
        provider_resolver=providers,
        entitlement_service=entitlements,
        quota_service=quota,
        **kwargs,
    )


def classification_service(
    dependencies: tuple[object, object, object, object], **kwargs: object
) -> DocumentClassificationService:
    dms, providers, entitlements, quota = dependencies
    return DocumentClassificationService(
        dms_gateway=dms,
        provider_resolver=providers,
        entitlement_service=entitlements,
        quota_service=quota,
        **kwargs,
    )


def template_service(dependencies: tuple[object, object, object, object]) -> TemplateMatchingService:
    dms, providers, entitlements, quota = dependencies
    return TemplateMatchingService(
        dms_gateway=dms,
        provider_resolver=providers,
        entitlement_service=entitlements,
        quota_service=quota,
    )


def _request(document_id: uuid.UUID | None = None, version_id: uuid.UUID | None = None) -> dict[str, object]:
    return {
        "document_id": document_id or uuid.uuid4(),
        "document_version_id": version_id or uuid.uuid4(),
        "engine": "tesseract",
        "extraction_type": ExtractionType.TEXT,
    }


def _zone(name: str = "Invoice number", key: str = "invoice_number", *, x: str = "0.05") -> dict[str, object]:
    return {
        "zone_name": name,
        "extraction_key": key,
        "zone_type": "text",
        "x": x,
        "y": "0.05",
        "width": "0.20",
        "height": "0.10",
        "page_number": 1,
        "expected_data_type": "string",
        "is_required": True,
    }


def test_request_extraction_is_durable_and_idempotent(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    service = extraction_service(dependencies)
    request = _request()

    first = service.request_extraction(tenant_id, actor_id, request, "same-request")
    replay = service.request_extraction(tenant_id, actor_id, request, "same-request")

    assert replay.record.pk == first.record.pk
    assert replay.job.pk == first.job.pk
    assert DocumentExtraction.objects.for_tenant(tenant_id).count() == 1
    assert AsyncJob.objects.for_tenant(tenant_id).filter(command="document_intelligence.extract").count() == 1
    assert first.job.transitions.count() == 1
    assert OutboxEvent.objects.for_tenant(tenant_id).filter(event_type="async_job.enqueued").count() == 1
    quota = dependencies[3]
    assert isinstance(quota, AllowingQuota)
    assert quota.calls == 1


@pytest.mark.parametrize(
    ("method", "extraction_type"),
    [("extract_text", ExtractionType.TEXT), ("extract_tables", ExtractionType.TABLE)],
)
def test_extraction_convenience_methods_build_the_authoritative_request(
    method: str,
    extraction_type: str,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    service = extraction_service(dependencies)
    accepted = getattr(service, method)(
        tenant_id,
        actor_id,
        uuid.uuid4(),
        uuid.uuid4(),
        "tesseract",
        f"{method}-key",
    )
    assert accepted.record.extraction_type == extraction_type


def test_extraction_prerequisite_failure_does_not_enqueue_or_call_provider(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    dms, providers, _entitlements, _quota = dependencies
    dms.get_document = Mock(side_effect=ProviderUnavailable("private upstream detail"))  # type: ignore[method-assign]

    with pytest.raises(DocumentIntelligenceError) as caught:
        extraction_service(dependencies).request_extraction(tenant_id, actor_id, _request(), "failed-prerequisite")

    assert caught.value.error_code == "dms_unavailable"
    assert not AsyncJob.objects.for_tenant(tenant_id).exists()
    assert providers.ocr.calls == 0


def test_request_extraction_rejects_concurrency_without_consuming_quota(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    DocumentExtractionFactory(tenant_id=tenant_id, created_by=actor_id, status=ExtractionStatus.PROCESSING)
    quota = dependencies[3]
    assert isinstance(quota, AllowingQuota)

    with pytest.raises(DocumentIntelligenceError) as caught:
        extraction_service(dependencies, concurrency_policy=lambda _: 1).request_extraction(
            tenant_id, actor_id, _request(), "over-capacity"
        )

    assert caught.value.error_code == "concurrency_exceeded"
    assert caught.value.status_code == 429
    assert quota.calls == 0


def test_run_extraction_persists_complete_page_evidence_and_terminal_replay(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    service = extraction_service(dependencies)
    accepted = service.request_extraction(tenant_id, actor_id, _request(), "complete-extraction")

    completed = service.run_extraction(tenant_id, accepted.record.id, accepted.job.id)
    replay = service.run_extraction(tenant_id, accepted.record.id, accepted.job.id)

    assert completed.status == ExtractionStatus.COMPLETED
    assert completed.raw_text == "Verified OCR evidence"
    assert completed.confidence == Decimal("0.9500")
    assert replay.pk == completed.pk
    page = DocumentExtractionPage.objects.for_tenant(tenant_id).get(extraction=completed)
    assert page.page_number == 1
    assert page.provider_metadata == {"adapter_key": "test_ocr"}
    providers = dependencies[1]
    assert isinstance(providers, DeterministicProviderResolver)
    assert providers.ocr.calls == 1
    assert (
        OutboxEvent.objects.for_tenant(tenant_id)
        .filter(event_type="document_intelligence.extraction.completed")
        .exists()
    )


def test_low_confidence_extraction_preserves_evidence_and_requires_review(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    providers = dependencies[1]
    assert isinstance(providers, DeterministicProviderResolver)
    providers.ocr.result = OCRResult(
        pages=(
            OCRPageResult(
                1,
                100,
                100,
                Decimal("0.4000"),
                raw_text="Uncertain but real evidence",
                provider_metadata={"adapter_key": "test_ocr"},
            ),
        ),
        confidence=Decimal("0.4000"),
        processing_time_ms=9,
        raw_text="Uncertain but real evidence",
    )
    service = extraction_service(dependencies)
    accepted = service.request_extraction(tenant_id, actor_id, _request(), "low-confidence")

    result = service.run_extraction(tenant_id, accepted.record.id, accepted.job.id)

    assert result.status == ExtractionStatus.NEEDS_REVIEW
    assert result.raw_text == "Uncertain but real evidence"
    assert result.confidence == Decimal("0.4000")


def test_timeout_is_sanitized_and_persisted(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    providers = dependencies[1]
    assert isinstance(providers, DeterministicProviderResolver)
    secret = "provider-body-secret"
    providers.ocr.extract = Mock(side_effect=DependencyTimeout(secret))  # type: ignore[method-assign]
    service = extraction_service(dependencies)
    accepted = service.request_extraction(tenant_id, actor_id, _request(), "timeout")

    with pytest.raises(ProcessingFailure) as caught:
        service.run_extraction(tenant_id, accepted.record.id, accepted.job.id)

    record = DocumentExtraction.objects.for_tenant(tenant_id).get(pk=accepted.record.id)
    assert caught.value.error_code == "dependency_timeout"
    assert caught.value.status_code == 504
    assert record.status == ExtractionStatus.TIMED_OUT
    assert record.failure_code == "dependency_timeout"
    assert secret not in record.failure_message


def test_retry_cancel_and_archive_extraction_are_guarded(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    old_job = AsyncJobFactory(tenant_id=tenant_id, actor_id=str(actor_id), command="document_intelligence.extract")
    failed = DocumentExtractionFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        async_job_id=old_job.id,
        status=ExtractionStatus.FAILED,
        failure_code="dependency_failure",
    )
    service = extraction_service(dependencies)

    retried = service.retry_extraction(tenant_id, failed.id, actor_id, "retry-once")
    assert retried.record.status == ExtractionStatus.QUEUED
    assert retried.job.id != old_job.id
    cancelled = service.cancel_extraction(tenant_id, failed.id, actor_id)
    assert cancelled.status == ExtractionStatus.CANCELLED
    service.archive_extraction(tenant_id, failed.id, actor_id)
    failed.refresh_from_db()
    assert failed.is_deleted is True
    assert failed.deleted_at is not None


def test_cross_tenant_extraction_lookup_is_not_found(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    foreign = CompletedDocumentExtractionFactory()
    with pytest.raises(DocumentIntelligenceError) as caught:
        extraction_service(dependencies).get_extraction(tenant_id, foreign.id)
    assert caught.value.error_code == "resource_not_found"
    assert caught.value.status_code == 404


def test_classification_request_run_distribution_and_review_preserve_inference(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    model = ClassifierModelVersionFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        training_job__tenant_id=tenant_id,
        training_job__created_by=actor_id,
        status=ModelVersionStatus.ACTIVE,
    )
    service = classification_service(dependencies)
    accepted = service.request_classification(tenant_id, actor_id, uuid.uuid4(), uuid.uuid4(), "classification-request")
    assert accepted.record.model_version_id == model.id

    completed = service.run_classification(tenant_id, accepted.record.id, accepted.job.id)
    scores = list(service.get_confidence_distribution(tenant_id, completed.id))
    reviewed = service.review_classification(tenant_id, completed.id, actor_id, "receipt", "Verified against source")

    assert completed.status == ClassificationStatus.COMPLETED
    assert [(item.rank, item.category) for item in scores] == [(1, "invoice"), (2, "receipt")]
    assert reviewed.category == "invoice"
    assert reviewed.confidence == Decimal("0.9000")
    assert reviewed.reviewed_category == "receipt"
    assert reviewed.review_status == ClassificationReviewStatus.CORRECTED
    replay = service.review_classification(tenant_id, completed.id, actor_id, "receipt", "Verified against source")
    assert replay.id == completed.id
    with pytest.raises(DocumentIntelligenceError) as caught:
        service.review_classification(tenant_id, completed.id, actor_id, "invoice", "changed")
    assert caught.value.error_code == "review_conflict"


def test_classification_requires_tenant_active_model_before_dms_call(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    dms = dependencies[0]
    dms.get_document = Mock(wraps=dms.get_document)  # type: ignore[method-assign]
    with pytest.raises(DocumentIntelligenceError) as caught:
        classification_service(dependencies).request_classification(
            tenant_id, actor_id, uuid.uuid4(), uuid.uuid4(), "no-model"
        )
    assert caught.value.error_code == "model_unavailable"
    dms.get_document.assert_not_called()


def test_training_validates_minimum_before_provider_resolution(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    providers = dependencies[1]
    providers.resolve_classifier = Mock(wraps=providers.resolve_classifier)  # type: ignore[method-assign]

    with pytest.raises(DocumentIntelligenceError) as caught:
        classification_service(dependencies, classifier_provider_policy=lambda _: "local_classifier").train_classifier(
            tenant_id, actor_id, "Too small", training_items({"invoice": 5}), "v-small", "small"
        )

    assert caught.value.error_code == "training_minimum"
    providers.resolve_classifier.assert_not_called()
    assert not ClassifierTrainingJob.objects.for_tenant(tenant_id).exists()


def test_training_run_creates_candidate_atomically(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    service = classification_service(dependencies, classifier_provider_policy=lambda _: "local_classifier")
    accepted = service.train_classifier(
        tenant_id, actor_id, "Invoice model", training_items(), "2026.10", "training-request"
    )
    completed = service.run_training(tenant_id, accepted.record.id, accepted.job.id)
    candidate = ClassifierModelVersion.objects.for_tenant(tenant_id).get(training_job=completed)

    assert completed.status == TrainingStatus.COMPLETED
    assert completed.accuracy == Decimal("0.9500")
    assert candidate.status == ModelVersionStatus.CANDIDATE
    assert candidate.artifact_checksum == "a" * 64
    assert service.run_training(tenant_id, accepted.record.id, accepted.job.id).id == completed.id


def test_model_activation_and_rollback_retire_current_version(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    current = ClassifierModelVersionFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        training_job__tenant_id=tenant_id,
        training_job__created_by=actor_id,
        status=ModelVersionStatus.ACTIVE,
    )
    candidate = ClassifierModelVersionFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        training_job__tenant_id=tenant_id,
        training_job__created_by=actor_id,
        status=ModelVersionStatus.CANDIDATE,
    )
    service = classification_service(dependencies)

    activated = service.activate_model_version(tenant_id, candidate.id, actor_id, "activate-candidate")
    current.refresh_from_db()
    assert activated.status == ModelVersionStatus.ACTIVE
    assert current.status == ModelVersionStatus.RETIRED

    rolled_back = service.rollback_model_version(tenant_id, current.id, actor_id, "rollback-current")
    activated.refresh_from_db()
    assert rolled_back.status == ModelVersionStatus.ACTIVE
    assert activated.status == ModelVersionStatus.RETIRED


def test_model_activation_fails_closed_below_accuracy_threshold(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    candidate = ClassifierModelVersionFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        training_job__tenant_id=tenant_id,
        training_job__created_by=actor_id,
        accuracy=Decimal("0.8000"),
        status=ModelVersionStatus.CANDIDATE,
    )
    with pytest.raises(DocumentIntelligenceError) as caught:
        classification_service(dependencies).activate_model_version(
            tenant_id, candidate.id, actor_id, "below-threshold"
        )
    assert caught.value.error_code == "accuracy_threshold"
    candidate.refresh_from_db()
    assert candidate.status == ModelVersionStatus.CANDIDATE


def test_stale_training_cleanup_is_strictly_tenant_scoped(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    own_job = AsyncJobFactory(
        tenant_id=tenant_id, actor_id=str(actor_id), command="document_intelligence.train_classifier"
    )
    own = ClassifierTrainingJobFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        async_job_id=own_job.id,
        status=TrainingStatus.QUEUED,
    )
    other_job = AsyncJobFactory(command="document_intelligence.train_classifier")
    other = ClassifierTrainingJobFactory(
        tenant_id=other_job.tenant_id,
        async_job_id=other_job.id,
        status=TrainingStatus.QUEUED,
    )
    stale_at = timezone.now() - timedelta(hours=30)
    ClassifierTrainingJob.objects.filter(pk__in=[own.id, other.id]).update(updated_at=stale_at)

    count = classification_service(dependencies).cancel_stale_training_jobs(
        tenant_id, timezone.now() - timedelta(hours=24)
    )

    own.refresh_from_db()
    other.refresh_from_db()
    assert count == 1
    assert own.status == TrainingStatus.CANCELLED
    assert other.status == TrainingStatus.QUEUED


def test_template_lifecycle_clones_active_revision_and_zones(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    service = template_service(dependencies)
    template = service.create_template(
        tenant_id,
        actor_id,
        {"name": "Invoice", "engine": "tesseract", "document_category": "invoice"},
        [_zone()],
    )
    active = service.activate_template(tenant_id, template.id, actor_id, "activate-template")
    updated = service.update_template(tenant_id, active.id, actor_id, {"description": "Revised"})

    assert active.status == TemplateStatus.ACTIVE
    assert updated.id != active.id
    assert updated.version == active.version + 1
    assert updated.status == TemplateStatus.DRAFT
    assert updated.description == "Revised"
    assert ExtractionTemplateZone.objects.for_tenant(tenant_id).filter(template=updated, is_deleted=False).count() == 1


def test_zone_validation_rejects_overlap_and_rolls_back_template_create(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    service = template_service(dependencies)
    before_events = OutboxEvent.objects.for_tenant(tenant_id).count()

    with pytest.raises(DocumentIntelligenceError) as caught:
        service.create_template(
            tenant_id,
            actor_id,
            {"name": "Invalid", "engine": "tesseract"},
            [_zone(), _zone("Total", "total", x="0.10")],
        )

    assert caught.value.error_code == "zone_overlap"
    assert not service.list_templates(tenant_id, object()).exists()
    assert OutboxEvent.objects.for_tenant(tenant_id).count() == before_events


def test_template_matching_applies_threshold_and_rejects_foreign_results(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    template = ExtractionTemplateFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        status=TemplateStatus.ACTIVE,
        match_threshold=Decimal("0.9500"),
    )
    providers = dependencies[1]
    assert isinstance(providers, DeterministicProviderResolver)
    providers.ocr.match = Mock(  # type: ignore[method-assign]
        return_value=TemplateMatchResult(template.id, Decimal("0.9000"))
    )

    unmatched = template_service(dependencies).match_template(tenant_id, uuid.uuid4(), uuid.uuid4())
    assert unmatched.template_id is None
    assert unmatched.confidence == Decimal("0.0000")

    providers.ocr.match = Mock(  # type: ignore[method-assign]
        return_value=TemplateMatchResult(uuid.uuid4(), Decimal("0.9900"))
    )
    with pytest.raises(Exception, match="foreign template"):
        template_service(dependencies).match_template(tenant_id, uuid.uuid4(), uuid.uuid4())


def test_template_zone_crud_never_crosses_tenant_boundary(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    foreign_zone = ExtractionTemplateZoneFactory()
    service = template_service(dependencies)

    with pytest.raises(DocumentIntelligenceError) as caught:
        service.update_zone(tenant_id, foreign_zone.id, actor_id, {"zone_name": "Intrusion"})
    assert caught.value.status_code == 404
    foreign_zone.refresh_from_db()
    assert foreign_zone.zone_name != "Intrusion"
