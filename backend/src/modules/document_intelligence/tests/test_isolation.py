"""Two-tenant isolation evidence for every document-intelligence entity."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from django.core.exceptions import ValidationError

from src.modules.document_intelligence.models import (
    ClassifierModelVersion,
    ClassifierTrainingJob,
    DocumentClassification,
    DocumentClassificationScore,
    DocumentExtraction,
    DocumentExtractionPage,
    ExtractionTemplate,
    ExtractionTemplateZone,
)
from src.modules.document_intelligence.serializers import DocumentExtractionCreateSerializer
from src.modules.document_intelligence.services import (
    DocumentClassificationService,
    DocumentExtractionService,
    DocumentIntelligenceError,
    TemplateMatchingService,
)

from .factories import (
    ClassifierModelVersionFactory,
    ClassifierTrainingJobFactory,
    CompletedDocumentExtractionFactory,
    DocumentClassificationFactory,
    DocumentClassificationScoreFactory,
    DocumentExtractionPageFactory,
    ExtractionTemplateFactory,
    ExtractionTemplateZoneFactory,
)

pytestmark = pytest.mark.django_db


@dataclass(frozen=True)
class TenantGraph:
    tenant_id: uuid.UUID
    actor_id: uuid.UUID
    extraction: DocumentExtraction
    page: DocumentExtractionPage
    training: ClassifierTrainingJob
    model: ClassifierModelVersion
    classification: DocumentClassification
    score: DocumentClassificationScore
    template: ExtractionTemplate
    zone: ExtractionTemplateZone


def _graph(tenant_id: uuid.UUID) -> TenantGraph:
    actor_id = uuid.uuid4()
    template = ExtractionTemplateFactory(tenant_id=tenant_id, created_by=actor_id)
    zone = ExtractionTemplateZoneFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        template=template,
    )
    extraction = CompletedDocumentExtractionFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        template=template,
    )
    page = DocumentExtractionPageFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        extraction=extraction,
    )
    training = ClassifierTrainingJobFactory(tenant_id=tenant_id, created_by=actor_id)
    model = ClassifierModelVersionFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        training_job=training,
    )
    classification = DocumentClassificationFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        model_version=model,
    )
    score = DocumentClassificationScoreFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        classification=classification,
    )
    return TenantGraph(
        tenant_id,
        actor_id,
        extraction,
        page,
        training,
        model,
        classification,
        score,
        template,
        zone,
    )


@pytest.fixture
def tenant_graphs() -> tuple[TenantGraph, TenantGraph]:
    return _graph(uuid.uuid4()), _graph(uuid.uuid4())


@pytest.mark.parametrize(
    ("model", "attribute"),
    [
        (DocumentExtraction, "extraction"),
        (DocumentExtractionPage, "page"),
        (DocumentClassification, "classification"),
        (DocumentClassificationScore, "score"),
        (ClassifierTrainingJob, "training"),
        (ClassifierModelVersion, "model"),
        (ExtractionTemplate, "template"),
        (ExtractionTemplateZone, "zone"),
    ],
)
def test_for_tenant_list_never_contains_other_tenant_entity(
    model: type,
    attribute: str,
    tenant_graphs: tuple[TenantGraph, TenantGraph],
) -> None:
    own, foreign = tenant_graphs
    identities = set(model.objects.for_tenant(own.tenant_id).values_list("id", flat=True))
    assert getattr(own, attribute).id in identities
    assert getattr(foreign, attribute).id not in identities


def test_service_details_return_exact_404_for_foreign_ids(
    tenant_graphs: tuple[TenantGraph, TenantGraph],
) -> None:
    own, foreign = tenant_graphs
    checks = [
        (DocumentExtractionService(), foreign.extraction.id, "get_extraction"),
        (DocumentClassificationService(), foreign.classification.id, "get_classification"),
        (DocumentClassificationService(), foreign.training.id, "get_training_job"),
        (DocumentClassificationService(), foreign.model.id, "get_model_version"),
        (TemplateMatchingService(), foreign.template.id, "get_template"),
    ]
    for service, identifier, method_name in checks:
        with pytest.raises(DocumentIntelligenceError) as caught:
            getattr(service, method_name)(own.tenant_id, identifier)
        assert caught.value.status_code == 404
        assert caught.value.error_code == "resource_not_found"


def test_spoofed_tenant_create_is_rejected_before_service_dispatch(
    tenant_graphs: tuple[TenantGraph, TenantGraph],
) -> None:
    own, foreign = tenant_graphs
    serializer = DocumentExtractionCreateSerializer(
        data={
            "tenant_id": str(foreign.tenant_id),
            "document_id": str(uuid.uuid4()),
            "document_version_id": str(uuid.uuid4()),
            "engine": "tesseract",
            "extraction_type": "text",
            "idempotency_key": "spoofed",
        }
    )
    before = DocumentExtraction.objects.for_tenant(foreign.tenant_id).count()
    assert serializer.is_valid() is False
    assert "tenant_id" in serializer.errors
    assert DocumentExtraction.objects.for_tenant(foreign.tenant_id).count() == before
    assert DocumentExtraction.objects.for_tenant(own.tenant_id).count() == 1


@pytest.mark.parametrize(
    ("service", "method", "attribute", "args"),
    [
        (DocumentExtractionService, "archive_extraction", "extraction", ()),
        (DocumentExtractionService, "cancel_extraction", "extraction", ()),
        (DocumentClassificationService, "archive_classification", "classification", ()),
        (DocumentClassificationService, "cancel_classification", "classification", ()),
        (DocumentClassificationService, "cancel_training", "training", ()),
        (TemplateMatchingService, "archive_template", "template", ()),
        (TemplateMatchingService, "archive_zone", "zone", ()),
    ],
)
def test_cross_tenant_mutations_return_not_found_and_leave_target_unchanged(
    service: type,
    method: str,
    attribute: str,
    args: tuple[object, ...],
    tenant_graphs: tuple[TenantGraph, TenantGraph],
) -> None:
    own, foreign = tenant_graphs
    target = getattr(foreign, attribute)
    before = tuple((field.attname, getattr(target, field.attname)) for field in target._meta.concrete_fields)
    with pytest.raises(DocumentIntelligenceError) as caught:
        getattr(service(), method)(own.tenant_id, target.id, own.actor_id, *args)
    assert caught.value.status_code == 404
    target.refresh_from_db()
    after = tuple((field.attname, getattr(target, field.attname)) for field in target._meta.concrete_fields)
    assert after == before


def test_cross_tenant_parent_references_fail_model_validation(
    tenant_graphs: tuple[TenantGraph, TenantGraph],
) -> None:
    own, foreign = tenant_graphs
    page = DocumentExtractionPage(
        tenant_id=own.tenant_id,
        created_by=own.actor_id,
        extraction=foreign.extraction,
        page_number=2,
        width=100,
        height=100,
        confidence="0.9000",
        structured_data={},
        table_data=[],
    )
    with pytest.raises(ValidationError, match="does not belong"):
        page.full_clean()

    zone = ExtractionTemplateZone(
        tenant_id=own.tenant_id,
        created_by=own.actor_id,
        template=foreign.template,
        zone_name="Foreign",
        extraction_key="foreign",
        zone_type="text",
        x="0.1",
        y="0.1",
        width="0.1",
        height="0.1",
        page_number=1,
        expected_data_type="string",
    )
    with pytest.raises(ValidationError, match="does not belong"):
        zone.full_clean()
