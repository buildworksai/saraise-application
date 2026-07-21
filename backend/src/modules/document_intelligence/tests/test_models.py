"""Persistence invariants for immutable, tenant-owned domain evidence."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from src.core.tenancy import TenantScopedModel, TimestampedModel
from src.modules.document_intelligence.models import (
    ClassificationReviewStatus,
    ClassifierModelVersion,
    ClassifierTrainingJob,
    DocumentClassification,
    DocumentClassificationScore,
    DocumentExtraction,
    DocumentExtractionPage,
    ExtractionStatus,
    ExtractionTemplate,
    ExtractionTemplateZone,
    ModelVersionStatus,
    TemplateStatus,
)

from .factories import (
    ClassifierModelVersionFactory,
    ClassifierTrainingJobFactory,
    CompletedDocumentExtractionFactory,
    DocumentClassificationFactory,
    DocumentClassificationScoreFactory,
    DocumentExtractionFactory,
    DocumentExtractionPageFactory,
    ExtractionTemplateFactory,
    ExtractionTemplateZoneFactory,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "model",
    [
        DocumentExtraction,
        DocumentExtractionPage,
        DocumentClassification,
        DocumentClassificationScore,
        ClassifierTrainingJob,
        ClassifierModelVersion,
        ExtractionTemplate,
        ExtractionTemplateZone,
    ],
)
def test_domain_models_use_canonical_tenant_and_timestamp_bases(model: type[object]) -> None:
    assert issubclass(model, TenantScopedModel)
    assert issubclass(model, TimestampedModel)
    assert model._meta.get_field("tenant_id").get_internal_type() == "UUIDField"
    assert model._meta.get_field("tenant_id").db_index is True


def test_native_uuid_identity_and_soft_delete_defaults() -> None:
    extraction = DocumentExtractionFactory()
    assert isinstance(extraction.id, uuid.UUID)
    assert isinstance(extraction.tenant_id, uuid.UUID)
    assert extraction.is_deleted is False
    assert extraction.deleted_at is None


def test_completed_extraction_evidence_and_status_are_immutable() -> None:
    extraction = CompletedDocumentExtractionFactory()
    extraction.raw_text = "attempted overwrite"
    with pytest.raises(ValidationError, match="immutable"):
        extraction.save()

    extraction.refresh_from_db()
    extraction.status = ExtractionStatus.FAILED
    with pytest.raises(ValidationError, match="immutable"):
        extraction.save()


def test_append_only_page_rejects_update_and_delete() -> None:
    page = DocumentExtractionPageFactory()
    page.raw_text = "attempted overwrite"
    with pytest.raises(ValidationError, match="Append-only"):
        page.save()
    with pytest.raises(ValidationError, match="Append-only"):
        page.delete()


def test_append_only_score_rejects_update_and_delete() -> None:
    score = DocumentClassificationScoreFactory()
    with pytest.raises(ValidationError, match="Append-only"):
        score.save()
    with pytest.raises(ValidationError, match="Append-only"):
        score.delete()


def test_cross_tenant_parent_relations_fail_closed() -> None:
    template = ExtractionTemplateFactory()
    with pytest.raises(ValidationError, match="does not belong"):
        DocumentExtractionFactory(template=template, tenant_id=uuid.uuid4())


def test_zone_overlap_is_rejected() -> None:
    existing = ExtractionTemplateZoneFactory()
    with pytest.raises(ValidationError, match="overlap"):
        ExtractionTemplateZoneFactory(
            template=existing.template,
            tenant_id=existing.tenant_id,
            x=Decimal("0.1000"),
            y=Decimal("0.1000"),
        )


def test_zone_out_of_bounds_database_constraint() -> None:
    template = ExtractionTemplateFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        ExtractionTemplateZone.objects.create(
            tenant_id=template.tenant_id,
            created_by=template.created_by,
            template=template,
            zone_name="Outside",
            extraction_key="outside",
            zone_type="text",
            x=Decimal("0.9000"),
            y=Decimal("0.1000"),
            width=Decimal("0.2000"),
            height=Decimal("0.1000"),
            page_number=1,
            expected_data_type="string",
        )


def test_active_template_name_is_case_insensitively_unique() -> None:
    tenant_id = uuid.uuid4()
    ExtractionTemplateFactory(tenant_id=tenant_id, name="Invoice", status=TemplateStatus.ACTIVE)
    with pytest.raises(IntegrityError), transaction.atomic():
        ExtractionTemplateFactory(tenant_id=tenant_id, name="INVOICE", status=TemplateStatus.ACTIVE)


def test_only_one_active_model_per_tenant() -> None:
    tenant_id = uuid.uuid4()
    first_job = ClassifierTrainingJobFactory(tenant_id=tenant_id)
    first = ClassifierModelVersionFactory(training_job=first_job, status=ModelVersionStatus.ACTIVE)
    second_job = ClassifierTrainingJobFactory(tenant_id=tenant_id)
    with pytest.raises(IntegrityError), transaction.atomic():
        ClassifierModelVersionFactory(
            training_job=second_job,
            status=ModelVersionStatus.ACTIVE,
            version=f"{first.version}.next",
        )


def test_low_confidence_requires_pending_manual_review() -> None:
    model = ClassifierModelVersionFactory()
    classification = DocumentClassificationFactory.build(
        model_version=model,
        confidence=Decimal("0.4000"),
        needs_review=True,
        review_status=ClassificationReviewStatus.NOT_REQUIRED,
    )
    with pytest.raises(ValidationError, match="pending review"):
        classification.full_clean()


def test_rank_one_score_must_match_primary_inference() -> None:
    classification = DocumentClassificationFactory()
    with pytest.raises(ValidationError, match="Rank-one"):
        DocumentClassificationScoreFactory(
            classification=classification,
            category="receipt",
            confidence=Decimal("0.8000"),
            rank=1,
        )


def test_soft_delete_retains_extraction_evidence() -> None:
    extraction = CompletedDocumentExtractionFactory()
    extraction.is_deleted = True
    from django.utils import timezone

    extraction.deleted_at = timezone.now()
    extraction.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
    assert DocumentExtraction.objects.get(pk=extraction.pk).is_deleted is True
