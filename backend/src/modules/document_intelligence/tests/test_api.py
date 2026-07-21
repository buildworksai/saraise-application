"""API v2 request-schema and response-contract tests.

Black-box endpoint tests are intentionally combined with serializer-level
checks: the former prove routing/envelopes/delegation, while the latter make
field ownership failures precise.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rest_framework.permissions import IsAuthenticated

from src.modules.document_intelligence import api, urls
from src.modules.document_intelligence.adapters import TemplateMatchResult
from src.modules.document_intelligence.models import ModelVersionStatus, TemplateStatus
from src.modules.document_intelligence.serializers import (
    ClassificationReviewSerializer,
    ClassifierTrainingJobCreateSerializer,
    DocumentClassificationCreateSerializer,
    DocumentExtractionCreateSerializer,
    ExtractionTemplateCreateSerializer,
    ExtractionTemplateZoneCreateSerializer,
)

from .factories import (
    AsyncJobFactory,
    ClassifierModelVersionFactory,
    ClassifierTrainingJobFactory,
    CompletedDocumentExtractionFactory,
    DocumentClassificationFactory,
    DocumentClassificationScoreFactory,
    DocumentExtractionPageFactory,
    ExtractionTemplateFactory,
    ExtractionTemplateZoneFactory,
    training_items,
)

pytest_plugins = ["src.core.testing.factories"]

BASE = "/api/v2/document-intelligence"


@pytest.fixture(autouse=True)
def isolate_api_from_access_dependency_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise controllers after authentication; access branches have dedicated tests."""

    monkeypatch.setattr(
        api.ActionAccessMixin,
        "get_permissions",
        lambda self: [IsAuthenticated()],
    )


@pytest.fixture
def api_graph(tenant_a_user: object, tenant_a: object) -> dict[str, object]:
    tenant_id = uuid.UUID(str(tenant_a.id))
    actor_id = uuid.uuid4()
    template = ExtractionTemplateFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        status=TemplateStatus.DRAFT,
    )
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
    durable_job = AsyncJobFactory(
        tenant_id=tenant_id,
        actor_id=str(actor_id),
        command="document_intelligence.train_classifier",
    )
    training = ClassifierTrainingJobFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        async_job_id=durable_job.id,
    )
    model = ClassifierModelVersionFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        training_job=training,
        status=ModelVersionStatus.CANDIDATE,
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
    return {
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "template": template,
        "zone": zone,
        "extraction": extraction,
        "page": page,
        "durable_job": durable_job,
        "training": training,
        "model": model,
        "classification": classification,
        "score": score,
    }


@pytest.mark.parametrize(
    ("serializer_class", "payload"),
    [
        (
            DocumentExtractionCreateSerializer,
            {
                "document_id": str(uuid.uuid4()),
                "document_version_id": str(uuid.uuid4()),
                "engine": "tesseract",
                "extraction_type": "text",
                "idempotency_key": "extract-1",
            },
        ),
        (
            DocumentClassificationCreateSerializer,
            {
                "document_id": str(uuid.uuid4()),
                "document_version_id": str(uuid.uuid4()),
                "idempotency_key": "classify-1",
            },
        ),
        (
            ExtractionTemplateCreateSerializer,
            {"name": "Invoice", "engine": "tesseract", "zones": []},
        ),
        (
            ClassificationReviewSerializer,
            {"category": "invoice", "note": "Confirmed against source"},
        ),
    ],
)
def test_mutation_serializers_reject_server_owned_tenant_and_result_fields(
    serializer_class: type,
    payload: dict[str, object],
) -> None:
    for field, value in (("tenant_id", str(uuid.uuid4())), ("status", "completed"), ("confidence", "1.0000")):
        serializer = serializer_class(data={**payload, field: value})
        assert serializer.is_valid() is False
        assert field in serializer.errors


def test_extraction_create_enforces_template_and_engine_modes() -> None:
    common = {
        "document_id": str(uuid.uuid4()),
        "document_version_id": str(uuid.uuid4()),
        "idempotency_key": "mode-validation",
    }
    structured = DocumentExtractionCreateSerializer(data={**common, "extraction_type": "structured"})
    text = DocumentExtractionCreateSerializer(data={**common, "extraction_type": "text"})
    assert structured.is_valid() is False
    assert "template_id" in structured.errors
    assert text.is_valid() is False
    assert "engine" in text.errors


def test_zone_serializer_rejects_out_of_bounds_geometry() -> None:
    serializer = ExtractionTemplateZoneCreateSerializer(
        data={
            "zone_name": "Total",
            "extraction_key": "total",
            "zone_type": "text",
            "x": "0.9000",
            "y": "0.1000",
            "width": "0.2000",
            "height": "0.1000",
            "page_number": 1,
            "expected_data_type": "decimal",
            "is_required": True,
        }
    )
    assert serializer.is_valid() is False
    assert "non_field_errors" in serializer.errors


def test_training_serializer_enforces_minimum_distribution_and_unique_versions() -> None:
    too_small = ClassifierTrainingJobCreateSerializer(
        data={
            "name": "Small",
            "items": training_items({"invoice": 5}),
            "requested_version": "v-small",
            "idempotency_key": "small",
        }
    )
    assert too_small.is_valid() is False
    assert "items" in too_small.errors

    items = training_items()
    items[-1] = dict(items[0])
    duplicate = ClassifierTrainingJobCreateSerializer(
        data={
            "name": "Duplicate",
            "items": items,
            "requested_version": "v-duplicate",
            "idempotency_key": "duplicate",
        }
    )
    assert duplicate.is_valid() is False
    assert "items" in duplicate.errors


def test_valid_operation_payloads_normalize_to_typed_primitives() -> None:
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    serializer = DocumentExtractionCreateSerializer(
        data={
            "document_id": str(document_id),
            "document_version_id": str(version_id),
            "engine": "tesseract",
            "extraction_type": "table",
            "idempotency_key": "valid-extraction",
        }
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["document_id"] == document_id
    assert serializer.validated_data["document_version_id"] == version_id

    template = ExtractionTemplateCreateSerializer(
        data={
            "name": "Invoice",
            "engine": "tesseract",
            "match_threshold": "0.8750",
            "zones": [],
        }
    )
    assert template.is_valid(), template.errors
    assert template.validated_data["match_threshold"] == Decimal("0.8750")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    [
        f"{BASE}/extractions/",
        f"{BASE}/extraction-pages/{uuid.uuid4()}/",
        f"{BASE}/classifications/",
        f"{BASE}/classification-scores/{uuid.uuid4()}/",
        f"{BASE}/templates/",
        f"{BASE}/template-zones/?template_id={uuid.uuid4()}",
        f"{BASE}/training-jobs/",
        f"{BASE}/model-versions/",
        f"{BASE}/health/",
    ],
)
def test_every_v2_resource_rejects_missing_session_with_stable_401(api_client: object, path: str) -> None:
    response = api_client.get(path)
    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert payload["error"]["correlation_id"]


@pytest.mark.django_db
def test_all_collections_are_rendered_v2_envelopes_with_bounded_pagination(
    authenticated_tenant_a_client: object,
    api_graph: dict[str, object],
) -> None:
    collections = {
        f"{BASE}/extractions/?page_size=100": api_graph["extraction"].id,
        f"{BASE}/classifications/?page_size=100": api_graph["classification"].id,
        f"{BASE}/templates/?page_size=100": api_graph["template"].id,
        f"{BASE}/template-zones/?template_id={api_graph['template'].id}&page_size=100": api_graph["zone"].id,
        f"{BASE}/training-jobs/?page_size=100": api_graph["training"].id,
        f"{BASE}/model-versions/?page_size=100": api_graph["model"].id,
    }
    for path, expected_id in collections.items():
        response = authenticated_tenant_a_client.get(path)
        assert response.status_code == 200, response.content
        payload = response.json()
        assert set(payload) == {"data", "meta"}
        assert str(expected_id) in {item["id"] for item in payload["data"]}
        pagination = payload["meta"]["pagination"]
        assert pagination["page"] == 1
        assert pagination["page_size"] <= 100
        assert payload["meta"]["correlation_id"]
        assert payload["meta"]["timestamp"]


@pytest.mark.django_db
def test_all_read_only_detail_and_child_endpoints_return_enveloped_evidence(
    authenticated_tenant_a_client: object,
    api_graph: dict[str, object],
) -> None:
    detail_paths = {
        f"{BASE}/extractions/{api_graph['extraction'].id}/": api_graph["extraction"].id,
        f"{BASE}/extraction-pages/{api_graph['page'].id}/": api_graph["page"].id,
        f"{BASE}/classifications/{api_graph['classification'].id}/": api_graph["classification"].id,
        f"{BASE}/classification-scores/{api_graph['score'].id}/": api_graph["score"].id,
        f"{BASE}/templates/{api_graph['template'].id}/": api_graph["template"].id,
        f"{BASE}/template-zones/{api_graph['zone'].id}/": api_graph["zone"].id,
        f"{BASE}/training-jobs/{api_graph['training'].id}/": api_graph["training"].id,
        f"{BASE}/model-versions/{api_graph['model'].id}/": api_graph["model"].id,
    }
    for path, expected_id in detail_paths.items():
        response = authenticated_tenant_a_client.get(path)
        assert response.status_code == 200, response.content
        payload = response.json()
        assert payload["data"]["id"] == str(expected_id)
        assert payload["meta"]["correlation_id"]

    children = {
        f"{BASE}/extractions/{api_graph['extraction'].id}/pages/": api_graph["page"].id,
        f"{BASE}/classifications/{api_graph['classification'].id}/scores/": api_graph["score"].id,
    }
    for path, expected_id in children.items():
        response = authenticated_tenant_a_client.get(path)
        assert response.status_code == 200
        payload = response.json()
        assert [item["id"] for item in payload["data"]] == [str(expected_id)]
        assert payload["meta"]["pagination"]["count"] == 1


@pytest.mark.django_db
def test_extraction_filters_search_ordering_and_invalid_queries_are_server_side(
    authenticated_tenant_a_client: object,
    api_graph: dict[str, object],
) -> None:
    extraction = api_graph["extraction"]
    match = authenticated_tenant_a_client.get(
        f"{BASE}/extractions/",
        {
            "document_id": str(extraction.document_id),
            "status": extraction.status,
            "engine": extraction.engine,
            "extraction_type": extraction.extraction_type,
            "template_id": str(extraction.template_id),
            "search": str(extraction.document_id),
            "ordering": "-confidence",
        },
    )
    assert match.status_code == 200
    assert [item["id"] for item in match.json()["data"]] == [str(extraction.id)]

    invalid = authenticated_tenant_a_client.get(
        f"{BASE}/extractions/", {"ordering": "tenant_id", "unexpected": "value"}
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"


def test_router_has_complete_v2_surface_and_no_legacy_resource_route() -> None:
    route_names = {pattern.name for pattern in urls.router.urls}
    expected = {
        "extraction-list",
        "extraction-detail",
        "extraction-pages",
        "extraction-retry",
        "extraction-cancel",
        "extraction-page-detail",
        "classification-list",
        "classification-detail",
        "classification-scores",
        "classification-review",
        "classification-retry",
        "classification-cancel",
        "classification-score-detail",
        "template-list",
        "template-detail",
        "template-activate",
        "template-deactivate",
        "template-clone",
        "template-match",
        "template-zone-list",
        "template-zone-detail",
        "training-job-list",
        "training-job-detail",
        "training-job-retry",
        "training-job-cancel",
        "model-version-list",
        "model-version-detail",
        "model-version-activate",
        "model-version-rollback",
    }
    assert expected <= route_names
    assert not any("resource" in str(pattern.pattern) for pattern in urls.router.urls)


@pytest.mark.django_db
def test_extraction_mutations_delegate_and_preserve_v2_status_contracts(
    monkeypatch: pytest.MonkeyPatch,
    authenticated_tenant_a_client: object,
    api_graph: dict[str, object],
) -> None:
    service = Mock()
    accepted = SimpleNamespace(record=api_graph["extraction"], job=api_graph["durable_job"])
    service.request_extraction.return_value = accepted
    service.retry_extraction.return_value = accepted
    service.cancel_extraction.return_value = api_graph["extraction"]
    monkeypatch.setattr(api.DocumentExtractionViewSet, "service_class", Mock(return_value=service))

    create = authenticated_tenant_a_client.post(
        f"{BASE}/extractions/",
        {
            "document_id": str(uuid.uuid4()),
            "document_version_id": str(uuid.uuid4()),
            "engine": "tesseract",
            "extraction_type": "text",
            "idempotency_key": "api-create",
        },
        format="json",
    )
    assert create.status_code == 202
    assert set(create.json()["data"]) == {"extraction", "job"}
    service.request_extraction.assert_called_once()

    retry = authenticated_tenant_a_client.post(
        f"{BASE}/extractions/{api_graph['extraction'].id}/retry/",
        {"idempotency_key": "api-retry"},
        format="json",
    )
    assert retry.status_code == 202
    service.retry_extraction.assert_called_once()

    cancel = authenticated_tenant_a_client.post(
        f"{BASE}/extractions/{api_graph['extraction'].id}/cancel/",
        {"reason": "operator request"},
        format="json",
    )
    assert cancel.status_code == 200
    service.cancel_extraction.assert_called_once()

    archived = authenticated_tenant_a_client.delete(f"{BASE}/extractions/{api_graph['extraction'].id}/")
    assert archived.status_code == 204
    assert archived.content == b""
    service.archive_extraction.assert_called_once()


@pytest.mark.django_db
def test_classification_training_and_model_actions_all_delegate_to_services(
    monkeypatch: pytest.MonkeyPatch,
    authenticated_tenant_a_client: object,
    api_graph: dict[str, object],
) -> None:
    service = Mock()
    classification_work = SimpleNamespace(record=api_graph["classification"], job=api_graph["durable_job"])
    training_work = SimpleNamespace(record=api_graph["training"], job=api_graph["durable_job"])
    service.request_classification.return_value = classification_work
    service.retry_classification.return_value = classification_work
    service.review_classification.return_value = api_graph["classification"]
    service.cancel_classification.return_value = api_graph["classification"]
    service.train_classifier.return_value = training_work
    service.retry_training.return_value = training_work
    service.cancel_training.return_value = api_graph["training"]
    service.activate_model_version.return_value = api_graph["model"]
    service.rollback_model_version.return_value = api_graph["model"]
    for viewset in (
        api.DocumentClassificationViewSet,
        api.ClassifierTrainingJobViewSet,
        api.ClassifierModelVersionViewSet,
    ):
        monkeypatch.setattr(viewset, "service_class", Mock(return_value=service))

    classify = authenticated_tenant_a_client.post(
        f"{BASE}/classifications/",
        {
            "document_id": str(uuid.uuid4()),
            "document_version_id": str(uuid.uuid4()),
            "idempotency_key": "classify",
        },
        format="json",
    )
    assert classify.status_code == 202
    review = authenticated_tenant_a_client.post(
        f"{BASE}/classifications/{api_graph['classification'].id}/review/",
        {"category": "invoice", "note": "confirmed"},
        format="json",
    )
    retry = authenticated_tenant_a_client.post(
        f"{BASE}/classifications/{api_graph['classification'].id}/retry/",
        {"idempotency_key": "retry"},
        format="json",
    )
    cancel = authenticated_tenant_a_client.post(
        f"{BASE}/classifications/{api_graph['classification'].id}/cancel/",
        {},
        format="json",
    )
    archived = authenticated_tenant_a_client.delete(f"{BASE}/classifications/{api_graph['classification'].id}/")
    assert [review.status_code, retry.status_code, cancel.status_code, archived.status_code] == [
        200,
        202,
        200,
        204,
    ]

    train = authenticated_tenant_a_client.post(
        f"{BASE}/training-jobs/",
        {
            "name": "API training",
            "items": training_items(),
            "requested_version": "api-v1",
            "idempotency_key": "train",
        },
        format="json",
    )
    train_retry = authenticated_tenant_a_client.post(
        f"{BASE}/training-jobs/{api_graph['training'].id}/retry/",
        {"idempotency_key": "train-retry"},
        format="json",
    )
    train_cancel = authenticated_tenant_a_client.post(
        f"{BASE}/training-jobs/{api_graph['training'].id}/cancel/",
        {},
        format="json",
    )
    assert [train.status_code, train_retry.status_code, train_cancel.status_code] == [202, 202, 200]

    activate = authenticated_tenant_a_client.post(
        f"{BASE}/model-versions/{api_graph['model'].id}/activate/",
        {"transition_key": "activate"},
        format="json",
    )
    rollback = authenticated_tenant_a_client.post(
        f"{BASE}/model-versions/{api_graph['model'].id}/rollback/",
        {"transition_key": "rollback"},
        format="json",
    )
    assert [activate.status_code, rollback.status_code] == [200, 200]
    for method in (
        service.request_classification,
        service.review_classification,
        service.retry_classification,
        service.cancel_classification,
        service.archive_classification,
        service.train_classifier,
        service.retry_training,
        service.cancel_training,
        service.activate_model_version,
        service.rollback_model_version,
    ):
        method.assert_called_once()


@pytest.mark.django_db
def test_template_and_zone_mutations_delegate_with_explicit_domain_actions(
    monkeypatch: pytest.MonkeyPatch,
    authenticated_tenant_a_client: object,
    api_graph: dict[str, object],
) -> None:
    service = Mock()
    service.create_template.return_value = api_graph["template"]
    service.update_template.return_value = api_graph["template"]
    service.activate_template.return_value = api_graph["template"]
    service.deactivate_template.return_value = api_graph["template"]
    service.clone_template_revision.return_value = api_graph["template"]
    service.match_template.return_value = TemplateMatchResult(api_graph["template"].id, Decimal("0.9000"), 12)
    service.create_zone.return_value = api_graph["zone"]
    service.update_zone.return_value = api_graph["zone"]
    for viewset in (api.ExtractionTemplateViewSet, api.ExtractionTemplateZoneViewSet):
        monkeypatch.setattr(viewset, "service_class", Mock(return_value=service))

    requests = [
        authenticated_tenant_a_client.post(
            f"{BASE}/templates/",
            {"name": "API template", "engine": "tesseract", "zones": []},
            format="json",
        ),
        authenticated_tenant_a_client.patch(
            f"{BASE}/templates/{api_graph['template'].id}/",
            {"description": "Updated"},
            format="json",
        ),
        authenticated_tenant_a_client.post(
            f"{BASE}/templates/{api_graph['template'].id}/activate/",
            {"transition_key": "activate"},
            format="json",
        ),
        authenticated_tenant_a_client.post(
            f"{BASE}/templates/{api_graph['template'].id}/deactivate/",
            {"transition_key": "deactivate"},
            format="json",
        ),
        authenticated_tenant_a_client.post(
            f"{BASE}/templates/{api_graph['template'].id}/clone/",
            {"name": "Clone"},
            format="json",
        ),
        authenticated_tenant_a_client.post(
            f"{BASE}/templates/{api_graph['template'].id}/match/",
            {"document_id": str(uuid.uuid4()), "document_version_id": str(uuid.uuid4())},
            format="json",
        ),
        authenticated_tenant_a_client.post(
            f"{BASE}/template-zones/",
            {
                "template_id": str(api_graph["template"].id),
                "zone_name": "API zone",
                "extraction_key": "api_zone",
                "zone_type": "text",
                "x": "0.1",
                "y": "0.1",
                "width": "0.1",
                "height": "0.1",
                "page_number": 1,
                "expected_data_type": "string",
            },
            format="json",
        ),
        authenticated_tenant_a_client.patch(
            f"{BASE}/template-zones/{api_graph['zone'].id}/",
            {"zone_name": "Updated zone"},
            format="json",
        ),
        authenticated_tenant_a_client.delete(f"{BASE}/template-zones/{api_graph['zone'].id}/"),
        authenticated_tenant_a_client.delete(f"{BASE}/templates/{api_graph['template'].id}/"),
    ]
    assert [response.status_code for response in requests] == [201, 200, 200, 200, 201, 200, 201, 200, 204, 204]
    for method in (
        service.create_template,
        service.update_template,
        service.activate_template,
        service.deactivate_template,
        service.clone_template_revision,
        service.match_template,
        service.create_zone,
        service.update_zone,
        service.archive_zone,
        service.archive_template,
    ):
        method.assert_called_once()
