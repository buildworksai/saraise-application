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
    DependencyCircuitOpen,
    DependencyHealth,
    DependencyTimeout,
    DocumentDescriptor,
    InvalidProviderOutput,
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
    ConfigurationAudit,
    ConfigurationVersion,
    DocumentExtraction,
    DocumentExtractionPage,
    DocumentIntelligenceConfiguration,
    ExtractionStatus,
    ExtractionTemplateZone,
    ExtractionType,
    ModelVersionStatus,
    QuotaReservation,
    TemplateStatus,
    TrainingStatus,
)
from src.modules.document_intelligence.services import (
    ConfigurationService,
    DocumentClassificationService,
    DocumentExtractionService,
    DocumentIntelligenceError,
    ProcessingFailure,
    TemplateMatchingService,
    _configuration_value,
    _failure_from_exception,
    _job_key,
    _required_text,
    _uuid,
    default_configuration_document,
    validate_configuration_document,
)

from .factories import (
    AsyncJobFactory,
    ClassifierModelVersionFactory,
    ClassifierTrainingJobFactory,
    CompletedDocumentExtractionFactory,
    DeterministicDMSGateway,
    DeterministicProviderResolver,
    DocumentClassificationFactory,
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


@dataclass
class DenyingQuota:
    calls: int = 0

    def consume(self, tenant_id: uuid.UUID, resource: str, *, cost: int) -> SimpleNamespace:
        assert isinstance(tenant_id, uuid.UUID)
        assert resource.startswith("document_intelligence.")
        assert cost > 0
        self.calls += 1
        return SimpleNamespace(allowed=False, remaining=0)


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


def test_validation_helpers_fail_closed_and_hash_oversized_job_keys() -> None:
    with pytest.raises(DocumentIntelligenceError) as invalid_uuid:
        _uuid("not-a-uuid", "document_id")
    assert invalid_uuid.value.error_code == "invalid_uuid"

    with pytest.raises(DocumentIntelligenceError) as missing_text:
        _required_text("   ", "engine", 50)
    assert missing_text.value.error_code == "validation_error"

    with pytest.raises(DocumentIntelligenceError):
        _required_text("x" * 51, "engine", 50)

    normal_key = _job_key("document_intelligence.extract", "short")
    long_key = _job_key("document_intelligence.extract", "x" * 300)
    assert normal_key == "document_intelligence.extract:short"
    assert long_key.startswith("document_intelligence.extract:")
    assert len(long_key) < len("document_intelligence.extract:" + ("x" * 300))

    assert _failure_from_exception(DependencyCircuitOpen("secret")) == (
        "failed",
        "circuit_open",
        "The dependency circuit is open.",
    )
    assert _failure_from_exception(ProviderUnavailable("secret")) == (
        "failed",
        "provider_unavailable",
        "The configured provider is unavailable.",
    )
    assert _failure_from_exception(InvalidProviderOutput("secret")) == (
        "failed",
        "invalid_output",
        "The provider returned invalid evidence.",
    )
    assert _failure_from_exception(RuntimeError("secret")) == (
        "failed",
        "dependency_failure",
        "The processing dependency failed.",
    )


def test_service_base_fails_closed_for_entitlement_provider_and_document_policy(
    tenant_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    class BrokenEntitlements:
        def check(self, tenant_id: uuid.UUID, capability: str) -> SimpleNamespace:
            raise RuntimeError("private entitlement detail")

    class DeniedEntitlements:
        def check(self, tenant_id: uuid.UUID, capability: str) -> SimpleNamespace:
            return SimpleNamespace(entitled=False)

    class ConfiguringUnavailableAdapter:
        configured = False

        def configure_runtime(self, configuration: object) -> None:
            self.configured = True

        def health(self) -> DependencyHealth:
            return DependencyHealth(False, "down", timezone.now())

    dms, providers, _entitlements, quota = dependencies
    service = DocumentExtractionService(
        dms_gateway=dms,
        provider_resolver=providers,
        entitlement_service=BrokenEntitlements(),
        quota_service=quota,
    )
    with pytest.raises(DocumentIntelligenceError) as unavailable:
        service._require_entitlement(tenant_id, "document_intelligence.extraction:create")
    assert unavailable.value.error_code == "dependency_unavailable"
    assert unavailable.value.status_code == 503

    denied = DocumentExtractionService(
        dms_gateway=dms,
        provider_resolver=providers,
        entitlement_service=DeniedEntitlements(),
        quota_service=quota,
    )
    with pytest.raises(DocumentIntelligenceError) as forbidden:
        denied._require_entitlement(tenant_id, "document_intelligence.extraction:create")
    assert forbidden.value.error_code == "entitlement_required"
    assert forbidden.value.status_code == 403

    adapter = ConfiguringUnavailableAdapter()
    with pytest.raises(DocumentIntelligenceError) as provider:
        extraction_service(dependencies)._provider_ready(tenant_id, adapter)
    assert adapter.configured is True
    assert provider.value.error_code == "provider_unavailable"

    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    dms.get_document = Mock(  # type: ignore[method-assign]
        return_value=DocumentDescriptor(
            document_id=uuid.uuid4(),
            document_version_id=version_id,
            mime_type="application/pdf",
            byte_size=1,
            checksum="a" * 64,
            content_handle="tenant://document",
            page_count=1,
        )
    )
    with pytest.raises(DocumentIntelligenceError) as mismatch:
        extraction_service(dependencies)._document(tenant_id, document_id, version_id)
    assert mismatch.value.error_code == "resource_not_found"

    dms.get_document = Mock(side_effect=ValueError("private malformed checksum"))  # type: ignore[method-assign]
    with pytest.raises(DocumentIntelligenceError) as malformed_metadata:
        extraction_service(dependencies)._document(tenant_id, document_id, version_id)
    assert malformed_metadata.value.error_code == "invalid_document_metadata"
    assert malformed_metadata.value.status_code == 503
    assert str(malformed_metadata.value) == "Document storage returned invalid metadata."


@pytest.mark.parametrize(
    ("descriptor_patch", "expected_code", "expected_status"),
    [
        ({}, "unsupported_media_type", 415),
        ({"byte_size": 128}, "document_too_large", 413),
        ({"page_count": 2}, "page_limit_exceeded", 413),
        ({"content_handle": "x" * 17}, "invalid_document_metadata", 503),
    ],
)
def test_document_descriptor_policy_rejects_unsafe_metadata(
    descriptor_patch: dict[str, object],
    expected_code: str,
    expected_status: int,
    tenant_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dms = dependencies[0]
    assert isinstance(dms, DeterministicDMSGateway)
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    descriptor_values = {
        "document_id": document_id,
        "document_version_id": version_id,
        "mime_type": "image/png",
        "byte_size": 128,
        "checksum": "b" * 64,
        "content_handle": "tenant://document",
        "page_count": 2,
    }
    descriptor_values.update(descriptor_patch)
    dms.get_document = Mock(  # type: ignore[arg-type, method-assign]
        return_value=DocumentDescriptor(**descriptor_values)
    )

    configuration = default_configuration_document()
    configuration["providers"]["allowed_mime_types"] = ["application/pdf"]
    configuration["limits"]["max_document_bytes"] = 64
    configuration["limits"]["max_pages"] = 1
    configuration["limits"]["content_handle_max_length"] = 16
    if expected_code == "unsupported_media_type":
        configuration["limits"]["max_document_bytes"] = 1024
        configuration["limits"]["max_pages"] = 10
        configuration["limits"]["content_handle_max_length"] = 64
    elif expected_code == "document_too_large":
        configuration["providers"]["allowed_mime_types"] = ["image/png"]
        configuration["limits"]["max_pages"] = 10
        configuration["limits"]["content_handle_max_length"] = 64
    elif expected_code == "page_limit_exceeded":
        configuration["providers"]["allowed_mime_types"] = ["image/png"]
        configuration["limits"]["max_document_bytes"] = 1024
        configuration["limits"]["content_handle_max_length"] = 64
    elif expected_code == "invalid_document_metadata":
        configuration["providers"]["allowed_mime_types"] = ["image/png"]
        configuration["limits"]["max_document_bytes"] = 1024
        configuration["limits"]["max_pages"] = 10
    monkeypatch.setattr(ConfigurationService, "get_effective", lambda self, tenant_id: configuration)
    monkeypatch.setattr(
        ConfigurationService,
        "get_value",
        lambda self, tenant_id, dotted_path: _configuration_lookup(configuration, dotted_path),
    )

    with pytest.raises(DocumentIntelligenceError) as caught:
        extraction_service(dependencies)._document(tenant_id, document_id, version_id)

    assert caught.value.error_code == expected_code
    assert caught.value.status_code == expected_status


def _configuration_lookup(configuration: dict[str, object], dotted_path: str) -> object:
    value: object = configuration
    for part in dotted_path.split("."):
        assert isinstance(value, dict)
        value = value[part]
    return value


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


def test_request_extraction_quota_denial_has_no_durable_job_or_reservation(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    dms, providers, entitlements, _quota = dependencies
    denied_quota = DenyingQuota()
    service = DocumentExtractionService(
        dms_gateway=dms,
        provider_resolver=providers,
        entitlement_service=entitlements,
        quota_service=denied_quota,
    )

    with pytest.raises(DocumentIntelligenceError) as caught:
        service.request_extraction(tenant_id, actor_id, _request(), "quota-denied")

    assert caught.value.error_code == "quota_exceeded"
    assert denied_quota.calls == 1
    assert not AsyncJob.objects.for_tenant(tenant_id).exists()
    assert not DocumentExtraction.objects.for_tenant(tenant_id).exists()
    assert not QuotaReservation.objects.for_tenant(tenant_id).exists()


def test_document_policy_rejects_invalid_page_metadata_before_acceptance(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    dms, providers, entitlements, quota = dependencies
    dms.page_count = 10_001
    service = DocumentExtractionService(
        dms_gateway=dms,
        provider_resolver=providers,
        entitlement_service=entitlements,
        quota_service=quota,
    )

    with pytest.raises(DocumentIntelligenceError) as caught:
        service.request_extraction(tenant_id, actor_id, _request(), "too-many-pages")

    assert caught.value.error_code == "invalid_document_metadata"
    assert not AsyncJob.objects.for_tenant(tenant_id).exists()


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


@pytest.mark.parametrize(
    ("extraction_type", "expected_field", "expected_value"),
    [
        (ExtractionType.STRUCTURED, "structured_data", {"invoice_number": "INV-100"}),
        (ExtractionType.ZONE, "structured_data", {"invoice_number": "INV-100"}),
        (ExtractionType.TABLE, "table_data", [{"sku": "A-1", "quantity": 2}]),
    ],
)
def test_run_extraction_completes_for_each_required_output_type(
    extraction_type: str,
    expected_field: str,
    expected_value: object,
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
                1200,
                1600,
                Decimal("0.9500"),
                raw_text="Invoice INV-100",
                structured_data={"invoice_number": "INV-100"},
                table_data=[{"sku": "A-1", "quantity": 2}],
                provider_metadata={"adapter_key": "test_ocr"},
            ),
        ),
        confidence=Decimal("0.9500"),
        processing_time_ms=12,
        raw_text="Invoice INV-100",
        structured_data={"invoice_number": "INV-100"},
        table_data=[{"sku": "A-1", "quantity": 2}],
    )
    service = extraction_service(dependencies)
    template_id = None
    if extraction_type in {ExtractionType.STRUCTURED, ExtractionType.ZONE}:
        template = template_service(dependencies).create_template(
            tenant_id,
            actor_id,
            {"name": f"{extraction_type} template", "engine": "tesseract", "document_category": "invoice"},
            [_zone()],
        )
        template_id = (
            template_service(dependencies)
            .activate_template(tenant_id, template.id, actor_id, f"{extraction_type}-activate")
            .id
        )
    accepted = service.request_extraction(
        tenant_id,
        actor_id,
        {**_request(), "extraction_type": extraction_type, "template_id": template_id},
        f"{extraction_type}-complete",
    )

    completed = service.run_extraction(tenant_id, accepted.record.id, accepted.job.id)

    assert completed.status == ExtractionStatus.COMPLETED
    assert getattr(completed, expected_field) == expected_value
    assert completed.page_count == 1


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


def test_run_extraction_rejects_invalid_provider_shape_and_persists_sanitized_failure(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    providers = dependencies[1]
    assert isinstance(providers, DeterministicProviderResolver)
    providers.ocr.extract = Mock(return_value={"raw_text": "not a validated DTO"})  # type: ignore[method-assign]
    service = extraction_service(dependencies)
    accepted = service.request_extraction(tenant_id, actor_id, _request(), "invalid-provider-shape")

    with pytest.raises(ProcessingFailure) as caught:
        service.run_extraction(tenant_id, accepted.record.id, accepted.job.id)

    record = DocumentExtraction.objects.for_tenant(tenant_id).get(pk=accepted.record.id)
    assert caught.value.error_code == "invalid_output"
    assert caught.value.status_code == 503
    assert record.status == ExtractionStatus.FAILED
    assert record.failure_code == "invalid_output"
    assert "not a validated DTO" not in record.failure_message
    assert not DocumentExtractionPage.objects.for_tenant(tenant_id).filter(extraction=record).exists()


def test_run_table_extraction_rejects_missing_table_evidence_without_partial_pages(
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
                1200,
                1600,
                Decimal("0.9500"),
                raw_text="Text-only evidence",
                provider_metadata={"adapter_key": "test_ocr"},
            ),
        ),
        confidence=Decimal("0.9500"),
        processing_time_ms=15,
        raw_text="Text-only evidence",
    )
    service = extraction_service(dependencies)
    accepted = service.request_extraction(
        tenant_id,
        actor_id,
        {**_request(), "extraction_type": ExtractionType.TABLE},
        "table-missing-output",
    )

    with pytest.raises(ProcessingFailure) as caught:
        service.run_extraction(tenant_id, accepted.record.id, accepted.job.id)

    record = DocumentExtraction.objects.for_tenant(tenant_id).get(pk=accepted.record.id)
    assert caught.value.error_code == "invalid_output"
    assert record.status == ExtractionStatus.FAILED
    assert record.page_count is None
    assert DocumentExtractionPage.objects.for_tenant(tenant_id).filter(extraction=record).count() == 0


def test_ocr_result_policy_rejects_tenant_configured_evidence_bounds(
    tenant_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuration = default_configuration_document()
    configuration["limits"]["max_pages"] = 1
    configuration["limits"]["max_text_characters"] = 8
    configuration["limits"]["max_structured_bytes"] = 32
    configuration["limits"]["page_dimension_max"] = 100
    monkeypatch.setattr(ConfigurationService, "get_effective", lambda self, tenant_id: configuration)

    valid_page = OCRPageResult(1, 50, 50, Decimal("0.8000"), raw_text="ok")
    second_page = OCRPageResult(2, 50, 50, Decimal("0.8000"), raw_text="ok")
    too_wide = OCRPageResult(1, 101, 50, Decimal("0.8000"), raw_text="ok")

    with pytest.raises(InvalidProviderOutput, match="page limit"):
        DocumentExtractionService._validate_ocr_result_policy(
            tenant_id,
            OCRResult((valid_page, second_page), Decimal("0.8000"), 1, raw_text="ok"),
        )
    with pytest.raises(InvalidProviderOutput, match="character"):
        DocumentExtractionService._validate_ocr_result_policy(
            tenant_id,
            OCRResult((valid_page,), Decimal("0.8000"), 1, raw_text="too long for policy"),
        )
    with pytest.raises(InvalidProviderOutput, match="structured"):
        DocumentExtractionService._validate_ocr_result_policy(
            tenant_id,
            OCRResult((valid_page,), Decimal("0.8000"), 1, structured_data={"field": "x" * 64}),
        )
    with pytest.raises(InvalidProviderOutput, match="dimensions"):
        DocumentExtractionService._validate_ocr_result_policy(
            tenant_id,
            OCRResult((too_wide,), Decimal("0.8000"), 1, raw_text="ok"),
        )


def test_dependency_execution_fails_closed_when_resilience_configuration_is_unavailable(
    tenant_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(self: ConfigurationService, tenant_id: uuid.UUID, dotted_path: str) -> object:
        del self, tenant_id, dotted_path
        raise DocumentIntelligenceError("invalid_configuration", "private invalid configuration")

    monkeypatch.setattr(ConfigurationService, "get_value", unavailable)

    with pytest.raises(DocumentIntelligenceError) as caught:
        extraction_service(dependencies)._execute_dependency(tenant_id, "ocr.test", lambda: "should-not-run")

    assert caught.value.error_code == "configuration_unavailable"
    assert caught.value.status_code == 503
    assert "private invalid configuration" not in str(caught.value)


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


def test_cancel_extraction_without_durable_job_still_terminal_and_tenant_scoped(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    extraction = DocumentExtractionFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        async_job_id=uuid.uuid4(),
        status=ExtractionStatus.QUEUED,
    )
    service = extraction_service(dependencies)

    cancelled = service.cancel_extraction(tenant_id, extraction.id, actor_id)

    assert cancelled.status == ExtractionStatus.CANCELLED
    assert not AsyncJob.objects.for_tenant(tenant_id).filter(pk=extraction.async_job_id).exists()


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


def test_classification_worker_rejects_invalid_provider_shape_and_records_terminal_failure(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    providers = dependencies[1]
    assert isinstance(providers, DeterministicProviderResolver)
    providers.classifier.classify = Mock(return_value={"category": "invoice"})  # type: ignore[method-assign]
    ClassifierModelVersionFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        training_job__tenant_id=tenant_id,
        training_job__created_by=actor_id,
        status=ModelVersionStatus.ACTIVE,
    )
    service = classification_service(dependencies)
    accepted = service.request_classification(
        tenant_id,
        actor_id,
        uuid.uuid4(),
        uuid.uuid4(),
        "classification-invalid-provider",
    )

    with pytest.raises(ProcessingFailure) as caught:
        service.run_classification(tenant_id, accepted.record.id, accepted.job.id)

    accepted.record.refresh_from_db()
    assert caught.value.error_code == "invalid_output"
    assert accepted.record.status == ClassificationStatus.FAILED
    assert accepted.record.failure_code == "invalid_output"
    assert accepted.record.failure_message == "The provider returned invalid evidence."


def test_classification_review_retry_cancel_and_archive_guards_use_durable_state(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    job = AsyncJobFactory(tenant_id=tenant_id, actor_id=str(actor_id), command="document_intelligence.classify")
    active_model = ClassifierModelVersionFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        training_job__tenant_id=tenant_id,
        training_job__created_by=actor_id,
        status=ModelVersionStatus.ACTIVE,
    )
    classification = DocumentClassificationFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        model_version=active_model,
        async_job_id=job.id,
        status=ClassificationStatus.FAILED,
        failure_code="provider_unavailable",
        failure_message="Provider unavailable",
    )
    service = classification_service(dependencies)

    retried = service.retry_classification(tenant_id, classification.id, actor_id, "classification-retry")
    assert retried.record.id != classification.id
    assert retried.record.status == ClassificationStatus.QUEUED

    cancelled = service.cancel_classification(tenant_id, retried.record.id, actor_id)
    assert cancelled.status == ClassificationStatus.CANCELLED
    retry_job = AsyncJob.objects.for_tenant(tenant_id).get(pk=retried.job.id)
    assert retry_job.status == "cancelled"

    service.archive_classification(tenant_id, cancelled.id, actor_id)
    cancelled.refresh_from_db()
    assert cancelled.is_deleted is True
    assert cancelled.deleted_at is not None

    with pytest.raises(DocumentIntelligenceError) as missing:
        service.retry_classification(tenant_id, cancelled.id, actor_id, "classification-retry-deleted")
    assert missing.value.error_code == "resource_not_found"

    with pytest.raises(DocumentIntelligenceError) as invalid_category:
        service.review_classification(tenant_id, classification.id, actor_id, "Invalid Category", "")
    assert invalid_category.value.error_code == "validation_error"


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


def test_template_zone_defaults_and_create_zone_preserve_all_fields(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    service = template_service(dependencies)
    default_page_zone = _zone()
    default_page_zone.pop("page_number")
    template = service.create_template(
        tenant_id,
        actor_id,
        {"name": "Invoice", "engine": "tesseract", "document_category": "invoice"},
        [default_page_zone],
    )
    existing = ExtractionTemplateZone.objects.for_tenant(tenant_id).get(template=template, is_deleted=False)
    assert existing.page_number == 1

    created = service.create_zone(
        tenant_id,
        template.id,
        actor_id,
        {
            "zone_name": "Due date",
            "extraction_key": "due_date",
            "zone_type": "text",
            "x": "0.55",
            "y": "0.15",
            "width": "0.25",
            "height": "0.08",
            "page_number": 3,
            "expected_data_type": "date",
            "is_required": False,
        },
    )

    assert created.zone_name == "Due date"
    assert created.extraction_key == "due_date"
    assert created.zone_type == "text"
    assert created.x == Decimal("0.55")
    assert created.y == Decimal("0.15")
    assert created.width == Decimal("0.25")
    assert created.height == Decimal("0.08")
    assert created.page_number == 3
    assert created.expected_data_type == "date"
    assert created.is_required is False
    assert (
        ExtractionTemplateZone.objects.for_tenant(tenant_id)
        .filter(template=template, is_deleted=False, zone_name="Invoice number")
        .exists()
    )


def test_update_zone_rewrites_only_active_template_zones_with_all_fields(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    dependencies: tuple[object, object, object, object],
) -> None:
    service = template_service(dependencies)
    template = service.create_template(
        tenant_id,
        actor_id,
        {"name": "Invoice", "engine": "tesseract", "document_category": "invoice"},
        [
            _zone(),
            {
                "zone_name": "Total",
                "extraction_key": "total",
                "zone_type": "text",
                "x": "0.70",
                "y": "0.70",
                "width": "0.20",
                "height": "0.10",
                "page_number": 2,
                "expected_data_type": "decimal",
                "is_required": False,
            },
        ],
    )
    target = ExtractionTemplateZone.objects.for_tenant(tenant_id).get(template=template, zone_name="Invoice number")
    deleted = ExtractionTemplateZoneFactory(
        tenant_id=tenant_id,
        created_by=actor_id,
        template=template,
        zone_name="Archived memo",
        extraction_key="archived_memo",
        x=Decimal("0.80"),
        y=Decimal("0.05"),
        width=Decimal("0.10"),
        height=Decimal("0.10"),
        page_number=5,
        is_deleted=True,
        deleted_at=timezone.now(),
    )

    updated = service.update_zone(
        tenant_id,
        target.id,
        actor_id,
        {
            "zone_name": "Purchase order",
            "extraction_key": "purchase_order",
            "zone_type": "text",
            "x": "0.12",
            "y": "0.22",
            "width": "0.18",
            "height": "0.07",
            "page_number": 4,
            "expected_data_type": "string",
            "is_required": False,
        },
    )

    active = {
        zone.zone_name: zone
        for zone in ExtractionTemplateZone.objects.for_tenant(tenant_id).filter(template=template, is_deleted=False)
    }
    assert set(active) == {"Purchase order", "Total"}
    assert updated.id == active["Purchase order"].id
    assert updated.extraction_key == "purchase_order"
    assert updated.zone_type == "text"
    assert updated.x == Decimal("0.12")
    assert updated.y == Decimal("0.22")
    assert updated.width == Decimal("0.18")
    assert updated.height == Decimal("0.07")
    assert updated.page_number == 4
    assert updated.expected_data_type == "string"
    assert updated.is_required is False
    retained = active["Total"]
    assert retained.extraction_key == "total"
    assert retained.zone_type == "text"
    assert retained.x == Decimal("0.7000")
    assert retained.y == Decimal("0.7000")
    assert retained.width == Decimal("0.2000")
    assert retained.height == Decimal("0.1000")
    assert retained.page_number == 2
    assert retained.expected_data_type == "decimal"
    assert retained.is_required is False
    deleted.refresh_from_db()
    assert deleted.is_deleted is True


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


def test_configuration_materializes_defaults_and_partial_updates_are_versioned(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    service = ConfigurationService()

    initial = service.get_record(tenant_id, "development")
    updated = service.save(
        tenant_id,
        actor_id,
        {"ui": {"page_size": 50}},
        environment="development",
        change_reason="Increase operator page size",
        correlation_id="cfg-partial-1",
        partial=True,
    )
    replay = service.save(
        tenant_id,
        actor_id,
        updated.document,
        environment="development",
        change_reason="No-op replay",
        correlation_id="cfg-partial-replay",
    )

    assert initial.version == 1
    assert updated.version == 2
    assert updated.document["ui"]["page_size"] == 50
    assert updated.document["providers"]["default_ocr_engine"] == "tesseract"
    assert replay.id == updated.id
    assert replay.version == 2
    assert ConfigurationVersion.objects.for_tenant(tenant_id).filter(environment="development").count() == 2
    assert ConfigurationAudit.objects.for_tenant(tenant_id).filter(environment="development").count() == 2
    assert service.get_value(tenant_id, "ui.page_size", "development") == 50


def test_configuration_import_export_simulate_and_rollback_preserve_audit_history(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    service = ConfigurationService()
    created = service.save(
        tenant_id,
        actor_id,
        default_configuration_document(),
        environment="saas",
        change_reason="Initialize SaaS defaults",
        correlation_id="cfg-init",
    )
    simulation = service.simulate(
        tenant_id,
        {"feature_flags": {"auto_classification_enabled": True, "rollout_percentage": 25}},
        environment="saas",
        partial=True,
    )

    assert created.version == 1
    assert simulation["valid"] is True
    assert simulation["requires_restart"] is False
    assert {
        "path": "feature_flags.rollout_percentage",
        "before": 0,
        "after": 25,
    } in simulation["changes"]

    exported = service.export_document(tenant_id, "saas")
    exported["document"]["feature_flags"]["auto_classification_enabled"] = True
    exported["document"]["feature_flags"]["rollout_percentage"] = 25
    imported = service.import_document(
        tenant_id,
        actor_id,
        exported,
        change_reason="Import rollout plan",
        correlation_id="cfg-import",
    )
    rolled_back = service.rollback(
        tenant_id,
        actor_id,
        1,
        environment="saas",
        change_reason="Rollback rollout plan",
        correlation_id="cfg-rollback",
    )

    assert imported.version == 2
    assert imported.document["feature_flags"]["rollout_percentage"] == 25
    assert rolled_back.version == 3
    assert rolled_back.document["feature_flags"]["rollout_percentage"] == 0
    assert list(
        ConfigurationAudit.objects.for_tenant(tenant_id)
        .filter(environment="saas")
        .order_by("version")
        .values_list("operation", flat=True)
    ) == ["initialize", "import", "rollback"]


def test_configuration_validation_fails_closed_for_bad_environment_import_and_schema(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    service = ConfigurationService()
    with pytest.raises(DocumentIntelligenceError) as bad_environment:
        service.get_record(tenant_id, "production")
    assert bad_environment.value.error_code == "configuration_unavailable"

    with pytest.raises(DocumentIntelligenceError) as bad_import_contract:
        service.import_document(
            tenant_id,
            actor_id,
            {
                "schema_version": 1,
                "module": "document_intelligence",
                "environment": "development",
                "document": default_configuration_document(),
                "unexpected": True,
            },
            change_reason="Bad import",
        )
    assert bad_import_contract.value.error_code == "invalid_configuration"

    invalid_document = default_configuration_document()
    invalid_document["providers"]["allowed_ocr_engines"] = []
    with pytest.raises(DocumentIntelligenceError) as bad_schema:
        service.save(
            tenant_id,
            actor_id,
            invalid_document,
            environment="development",
            change_reason="Unsafe provider policy",
            correlation_id="cfg-invalid",
        )
    assert bad_schema.value.error_code == "invalid_configuration"
    assert not DocumentIntelligenceConfiguration.objects.for_tenant(tenant_id).exists()


def test_configuration_validation_rejects_unsafe_policy_combinations() -> None:
    document = default_configuration_document()
    document["feature_flags"]["auto_classification_enabled"] = False
    document["feature_flags"]["rollout_percentage"] = 10
    with pytest.raises(DocumentIntelligenceError) as disabled_rollout:
        validate_configuration_document(document, environment="development")
    assert disabled_rollout.value.error_code == "invalid_configuration"

    document = default_configuration_document()
    document["ui"]["confidence_filter_presets"] = [0.1, 0.1]
    with pytest.raises(DocumentIntelligenceError) as duplicate_thresholds:
        validate_configuration_document(document, environment="development")
    assert duplicate_thresholds.value.error_code == "invalid_configuration"

    document = default_configuration_document()
    document["ui"]["positive_statuses"] = ["completed", "failed"]
    document["ui"]["warning_statuses"] = ["failed"]
    with pytest.raises(DocumentIntelligenceError) as overlapping_groups:
        validate_configuration_document(document, environment="development")
    assert overlapping_groups.value.error_code == "invalid_configuration"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda document: document["limits"].update({"max_pages": True}),
            "limits.max_pages must be a finite number",
        ),
        (
            lambda document: document["limits"].update({"max_pages": 2.5}),
            "limits.max_pages must be int",
        ),
        (
            lambda document: document["providers"].update({"allowed_mime_types": ["text/plain"]}),
            "An unsupported MIME type was configured",
        ),
        (
            lambda document: document["providers"].update({"allowed_extraction_types": ["unsafe"]}),
            "An unsupported extraction type was configured",
        ),
        (
            lambda document: document["templates"].update({"default_engine": "missing-engine"}),
            "templates.default_engine must be allow-listed",
        ),
        (
            lambda document: document["providers"].update({"default_classifier_provider": "unsupported"}),
            "Classifier provider is not supported",
        ),
        (
            lambda document: document["providers"].update({"artifact_root_environment_variable": "bad-ref"}),
            "Artifact root environment reference is invalid",
        ),
        (
            lambda document: document["classifier"].update(
                {"minimum_documents_per_category": 25, "minimum_training_documents": 20}
            ),
            "Per-category training minimum exceeds the total minimum",
        ),
        (
            lambda document: document["classifier"].update({"provider_max_categories": 20})
            or document["limits"].update({"max_categories": 10}),
            "Provider category capacity exceeds the tenant category limit",
        ),
        (
            lambda document: document["resilience"].update(
                {"initial_backoff_seconds": 10.0, "max_backoff_seconds": 1.0}
            ),
            "Retry backoff bounds are reversed",
        ),
        (
            lambda document: document["editor"]["new_zone"].update({"x": 0.8, "width": 0.3}),
            "Default editor zone exceeds the page bounds",
        ),
        (
            lambda document: document["editor"]["new_zone"].update({"zone_type": "unsafe"}),
            "Default editor zone type is invalid",
        ),
        (
            lambda document: document["editor"]["new_zone"].update({"expected_data_type": "object"}),
            "Default editor data type is invalid",
        ),
        (
            lambda document: document["observability"].update({"provider_duration_buckets_seconds": [0.25, 0.25, 1.0]}),
            "observability.provider_duration_buckets_seconds must be unique and ascending",
        ),
        (
            lambda document: document["feature_flags"].update({"allowed_roles": ["admin", "admin"]}),
            "feature_flags.allowed_roles contains duplicate values",
        ),
        (
            lambda document: document["workflows"].update({"extraction": []}),
            "workflows.extraction is invalid",
        ),
        (
            lambda document: document["workflows"]["extraction"][0].update({"to": ""}),
            "workflows.extraction contains an invalid transition",
        ),
    ],
)
def test_configuration_validation_rejects_each_unsafe_boundary(
    mutate: object,
    message: str,
) -> None:
    document = default_configuration_document()
    mutate(document)

    with pytest.raises(DocumentIntelligenceError, match=message) as caught:
        validate_configuration_document(document, environment="development")

    assert caught.value.error_code == "invalid_configuration"


def test_configuration_helpers_do_not_leak_mutable_defaults_or_missing_paths() -> None:
    first = default_configuration_document()
    second = default_configuration_document()
    first["ui"]["page_size"] = 99

    assert second["ui"]["page_size"] != 99
    assert _configuration_value(second, "ui.page_size") == second["ui"]["page_size"]
    with pytest.raises(DocumentIntelligenceError) as caught:
        _configuration_value(second, "ui.missing")
    assert caught.value.error_code == "invalid_configuration"


def test_configuration_save_rejects_bad_operation_and_bad_correlation(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    service = ConfigurationService()
    service.save(
        tenant_id,
        actor_id,
        default_configuration_document(),
        environment="development",
        change_reason="Initialize defaults",
        correlation_id="cfg-stale-1",
    )

    with pytest.raises(DocumentIntelligenceError) as bad_operation:
        service.save(
            tenant_id,
            actor_id,
            {"ui": {"page_size": 25}},
            environment="development",
            change_reason="Invalid operation",
            correlation_id="cfg-operation-2",
            partial=True,
            operation="unsafe",
        )
    assert bad_operation.value.error_code == "invalid_configuration"

    with pytest.raises(DocumentIntelligenceError) as bad_correlation:
        service.save(
            tenant_id,
            actor_id,
            {"ui": {"page_size": 25}},
            environment="development",
            change_reason="Bad correlation",
            correlation_id="x" * 65,
            partial=True,
        )
    assert bad_correlation.value.error_code == "invalid_configuration"
