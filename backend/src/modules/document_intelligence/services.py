"""Tenant-safe application services for document intelligence.

All domain mutation lives here.  Controllers perform only primitive request
validation and serialization; workers call the same services under canonical
tenant context.  Document bytes remain streamed from DMS into configured
adapters and are never persisted or logged by this module.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import uuid
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, TypeVar
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework import status as http_status

from src.core.access.entitlements import EntitlementService, QuotaService
from src.core.api.results import OperationFailed
from src.core.async_jobs.models import AsyncJob, JobStatus
from src.core.async_jobs.services import enqueue, transition
from src.core.observability import get_correlation_id

from . import metrics
from .adapters import (
    DependencyCircuitOpen,
    DependencyTimeout,
    DMSGateway,
    DocumentDescriptor,
    InvalidProviderOutput,
    OCRRequest,
    OCRResult,
    ProviderResolver,
    ProviderUnavailable,
    ResilienceExecutor,
    ResiliencePolicy,
    TemplateMatchResult,
    get_dms_gateway,
    get_provider_resolver,
)
from .events import publish_domain_event
from .models import (
    ClassificationReviewStatus,
    ClassificationStatus,
    ClassifierModelVersion,
    ClassifierTrainingJob,
    DocumentClassification,
    DocumentClassificationScore,
    DocumentExtraction,
    DocumentExtractionPage,
    ExtractionStatus,
    ExtractionTemplate,
    ExtractionTemplateZone,
    ExtractionType,
    ModelVersionStatus,
    QuotaReservation,
    TemplateStatus,
    TrainingStatus,
)
from .state_machines import (
    CLASSIFICATION_STATE_MACHINE,
    EXTRACTION_STATE_MACHINE,
    MODEL_VERSION_STATE_MACHINE,
    TEMPLATE_STATE_MACHINE,
    TRAINING_STATE_MACHINE,
)

logger = logging.getLogger("saraise.document_intelligence")
T = TypeVar("T")

_CATEGORY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")


class DocumentIntelligenceError(OperationFailed):
    """Stable domain error mapped by the governed API exception handler."""

    def __init__(self, code: str, message: str, *, status_code: int = 422, detail: object | None = None) -> None:
        super().__init__(error_code=code, message=message, detail=detail, http_status=status_code)


class ProcessingFailure(DocumentIntelligenceError):
    """Raised after a worker has durably persisted a terminal failure."""


@dataclass(frozen=True, slots=True)
class AcceptedWork:
    record: object
    job: AsyncJob


def _uuid(value: UUID | str, name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise DocumentIntelligenceError("invalid_uuid", f"{name} must be a valid UUID.") from exc


def _required_text(value: object, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DocumentIntelligenceError("validation_error", f"{name} is required.")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise DocumentIntelligenceError("validation_error", f"{name} exceeds {maximum} characters.")
    return normalized


def _transition_metadata(actor_id: UUID | None, reason: str) -> dict[str, str]:
    return {
        "actor_id": str(actor_id or uuid.UUID(int=0)),
        "reason": reason,
        "correlation_id": get_correlation_id() or str(uuid.uuid4()),
    }


def _initial_history(key: str, actor_id: UUID, status: str, reason: str) -> list[dict[str, object]]:
    return [
        {
            "transition_key": key,
            "command": "enqueue",
            "from_state": "",
            "to_state": status,
            "occurred_at": timezone.now().isoformat(),
            "metadata": _transition_metadata(actor_id, reason),
        }
    ]


def _job_key(command: str, idempotency_key: str) -> str:
    # Hash only when namespacing would exceed the durable-job key bound.
    combined = f"{command}:{idempotency_key}"
    if len(combined) <= 255:
        return combined
    import hashlib

    return f"{command}:{hashlib.sha256(idempotency_key.encode('utf-8')).hexdigest()}"


def _failure_from_exception(exc: Exception) -> tuple[str, str, str]:
    """Return (domain state, stable code, sanitized operator-safe detail)."""
    if isinstance(exc, DependencyTimeout):
        return "timed_out", "dependency_timeout", "The dependency timed out."
    if isinstance(exc, DependencyCircuitOpen):
        return "failed", "circuit_open", "The dependency circuit is open."
    if isinstance(exc, ProviderUnavailable):
        return "failed", "provider_unavailable", "The configured provider is unavailable."
    if isinstance(exc, InvalidProviderOutput):
        return "failed", "invalid_output", "The provider returned invalid evidence."
    return "failed", "dependency_failure", "The processing dependency failed."


class _ServiceBase:
    def __init__(
        self,
        *,
        dms_gateway: DMSGateway | None = None,
        provider_resolver: ProviderResolver | None = None,
        entitlement_service: EntitlementService | None = None,
        quota_service: QuotaService | None = None,
        resilience_executor: ResilienceExecutor | None = None,
    ) -> None:
        self.dms = dms_gateway or get_dms_gateway()
        self.providers = provider_resolver or get_provider_resolver()
        self.entitlements = entitlement_service or EntitlementService()
        self.quotas = quota_service or QuotaService()
        self.resilience = resilience_executor or ResilienceExecutor()

    @staticmethod
    def _tenant(value: UUID | str) -> UUID:
        return _uuid(value, "tenant_id")

    def _require_entitlement(self, tenant_id: UUID, capability: str) -> None:
        try:
            entitled = self.entitlements.check(tenant_id, capability).entitled
        except Exception as exc:
            raise DocumentIntelligenceError(
                "dependency_unavailable",
                "Entitlement state is unavailable.",
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc
        if not entitled:
            raise DocumentIntelligenceError(
                "entitlement_required",
                "The tenant is not entitled to this capability.",
                status_code=http_status.HTTP_403_FORBIDDEN,
            )

    def _consume_quota(self, tenant_id: UUID, resource: str, cost: int, operation_key: str) -> None:
        if (
            QuotaReservation.objects.for_tenant(tenant_id)
            .filter(resource=resource, operation_key=operation_key)
            .exists()
        ):
            return
        try:
            result = self.quotas.consume(tenant_id, resource, cost=cost)
        except Exception as exc:
            raise DocumentIntelligenceError(
                "dependency_unavailable",
                "Quota state is unavailable.",
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc
        if not result.allowed:
            raise DocumentIntelligenceError(
                "quota_exceeded",
                "The tenant quota is exhausted.",
                status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"remaining": result.remaining},
            )
        QuotaReservation.objects.create(
            tenant_id=tenant_id,
            created_by=uuid.UUID(int=0),
            resource=resource,
            operation_key=operation_key,
            cost=cost,
        )

    def _document(self, tenant_id: UUID, document_id: UUID, version_id: UUID) -> DocumentDescriptor:
        try:
            descriptor = self._execute_dependency(
                tenant_id,
                "dms.get_document",
                lambda: self.dms.get_document(tenant_id, document_id, version_id),
            )
        except (KeyError, ObjectDoesNotExist) as exc:
            raise DocumentIntelligenceError(
                "resource_not_found",
                "The requested document version was not found.",
                status_code=http_status.HTTP_404_NOT_FOUND,
            ) from exc
        except ProviderUnavailable as exc:
            raise DocumentIntelligenceError(
                "dms_unavailable",
                "Document storage is unavailable.",
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc
        if not isinstance(descriptor, DocumentDescriptor):
            raise DocumentIntelligenceError(
                "invalid_document_metadata",
                "Document storage returned invalid metadata.",
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if descriptor.document_id != document_id or descriptor.document_version_id != version_id:
            raise DocumentIntelligenceError(
                "resource_not_found",
                "The requested document version was not found.",
                status_code=http_status.HTTP_404_NOT_FOUND,
            )
        configuration = ConfigurationService().get_effective(tenant_id)
        limits = configuration["limits"]
        providers = configuration["providers"]
        if descriptor.mime_type.lower() not in providers["allowed_mime_types"]:
            raise DocumentIntelligenceError(
                "unsupported_media_type", "The document MIME type is not enabled.", status_code=415
            )
        if descriptor.byte_size > int(limits["max_document_bytes"]):
            raise DocumentIntelligenceError(
                "document_too_large", "The document exceeds the tenant byte limit.", status_code=413
            )
        if descriptor.page_count is not None and descriptor.page_count > int(limits["max_pages"]):
            raise DocumentIntelligenceError(
                "page_limit_exceeded", "The document exceeds the tenant page limit.", status_code=413
            )
        if len(descriptor.content_handle) > int(limits["content_handle_max_length"]):
            raise DocumentIntelligenceError(
                "invalid_document_metadata", "The content handle exceeds the configured bound.", status_code=503
            )
        return descriptor

    @staticmethod
    def _validate_ocr_result_policy(tenant_id: UUID, result: OCRResult) -> None:
        limits = ConfigurationService().get_effective(tenant_id)["limits"]
        if len(result.pages) > int(limits["max_pages"]):
            raise InvalidProviderOutput("OCR result exceeds the configured page limit")
        if result.raw_text is not None and len(result.raw_text) > int(limits["max_text_characters"]):
            raise InvalidProviderOutput("OCR text exceeds the configured character limit")
        structured_size = len(
            json.dumps((result.structured_data, result.table_data), default=str, separators=(",", ":")).encode("utf-8")
        )
        if structured_size > int(limits["max_structured_bytes"]):
            raise InvalidProviderOutput("OCR structured evidence exceeds the configured byte limit")
        dimension_max = int(limits["page_dimension_max"])
        if any(page.width > dimension_max or page.height > dimension_max for page in result.pages):
            raise InvalidProviderOutput("OCR page dimensions exceed the configured provider bound")

    def _resilience_policy(self, tenant_id: UUID) -> ResiliencePolicy:
        configuration = ConfigurationService()
        return ResiliencePolicy(
            timeout_seconds=float(configuration.get_value(tenant_id, "resilience.timeout_seconds")),
            max_attempts=int(configuration.get_value(tenant_id, "resilience.max_attempts")),
            initial_backoff_seconds=float(configuration.get_value(tenant_id, "resilience.initial_backoff_seconds")),
            max_backoff_seconds=float(configuration.get_value(tenant_id, "resilience.max_backoff_seconds")),
            jitter_ratio=float(configuration.get_value(tenant_id, "resilience.jitter_ratio")),
            circuit_failure_threshold=int(configuration.get_value(tenant_id, "resilience.circuit_failure_threshold")),
            circuit_recovery_seconds=float(configuration.get_value(tenant_id, "resilience.circuit_recovery_seconds")),
        )

    def _execute_dependency(self, tenant_id: UUID, key: str, operation: Callable[[], T]) -> T:
        try:
            policy = self._resilience_policy(tenant_id)
        except Exception as exc:
            raise DocumentIntelligenceError(
                "configuration_unavailable",
                "Validated tenant resilience configuration is unavailable.",
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc
        return self.resilience.execute(f"{tenant_id}:{key}", operation, policy)

    def _provider_ready(self, tenant_id: UUID, adapter: object) -> None:
        try:
            configure_runtime = getattr(adapter, "configure_runtime", None)
            if callable(configure_runtime):
                configure_runtime(ConfigurationService().get_effective(tenant_id))
            health = self._execute_dependency(
                tenant_id,
                "provider.health",
                adapter.health,  # type: ignore[attr-defined]
            )
        except Exception as exc:
            raise DocumentIntelligenceError("provider_unavailable", "The provider is unavailable.") from exc
        if not getattr(health, "available", False):
            raise DocumentIntelligenceError("provider_unavailable", "The provider is unavailable.")


class DocumentExtractionService(_ServiceBase):
    """Request, execute, retry, cancel, archive, and query extractions."""

    def __init__(self, *, concurrency_policy: Callable[[UUID], int] | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.concurrency_policy = concurrency_policy or (
            lambda tenant_id: int(ConfigurationService().get_value(tenant_id, "extraction.max_active"))
        )

    def request_extraction(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        request: Mapping[str, object],
        idempotency_key: str,
    ) -> AcceptedWork:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        key = _required_text(idempotency_key, "idempotency_key", 255)
        existing = DocumentExtraction.objects.for_tenant(tenant_id).filter(idempotency_key=key).first()
        if existing is not None:
            job = AsyncJob.objects.for_tenant(tenant_id).get(pk=existing.async_job_id)
            return AcceptedWork(existing, job)
        if not isinstance(request, Mapping):
            raise DocumentIntelligenceError("validation_error", "request must be an object.")
        document_id = _uuid(request.get("document_id"), "document_id")
        version_id = _uuid(request.get("document_version_id", request.get("version_id")), "document_version_id")
        extraction_type = str(request.get("extraction_type", ""))
        if extraction_type not in ExtractionType.values:
            raise DocumentIntelligenceError("validation_error", "extraction_type is invalid.")
        configuration = ConfigurationService().get_effective(tenant_id)
        if extraction_type not in configuration["providers"]["allowed_extraction_types"]:
            raise DocumentIntelligenceError("validation_error", "extraction_type is disabled by tenant policy.")
        template_id = request.get("template_id")
        template = None
        if template_id not in (None, ""):
            template = (
                ExtractionTemplate.objects.for_tenant(tenant_id)
                .filter(pk=_uuid(template_id, "template_id"), is_deleted=False)
                .first()
            )
            if template is None:
                raise DocumentIntelligenceError("resource_not_found", "Template not found.", status_code=404)
            if template.status != TemplateStatus.ACTIVE:
                raise DocumentIntelligenceError(
                    "template_inactive", "The extraction template is not active.", status_code=409
                )
        if extraction_type in {ExtractionType.STRUCTURED, ExtractionType.ZONE} and template is None:
            raise DocumentIntelligenceError("template_required", "This extraction type requires a template.")
        engine = str(request.get("engine") or (template.engine if template else ""))
        engine = _required_text(engine, "engine", 50)
        if engine not in configuration["providers"]["allowed_ocr_engines"]:
            raise DocumentIntelligenceError("validation_error", "engine is disabled by tenant policy.")

        descriptor = self._document(tenant_id, document_id, version_id)
        try:
            adapter = self.providers.resolve_ocr(tenant_id, engine)
        except ProviderUnavailable as exc:
            raise DocumentIntelligenceError("provider_unavailable", "The OCR provider is not configured.") from exc
        self._provider_ready(tenant_id, adapter)
        self._require_entitlement(tenant_id, "document_intelligence.extraction:create")
        if descriptor.page_count is None:
            raise DocumentIntelligenceError("page_count_unavailable", "Document page metadata is required.")

        limit = self.concurrency_policy(tenant_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise DocumentIntelligenceError(
                "policy_unavailable", "Extraction concurrency policy is invalid.", status_code=503
            )

        extraction_id = uuid.uuid4()
        command = "document_intelligence.extract"
        with transaction.atomic():
            active = (
                DocumentExtraction.objects.for_tenant(tenant_id)
                .filter(status__in=[ExtractionStatus.QUEUED, ExtractionStatus.PROCESSING], is_deleted=False)
                .count()
            )
            if active >= limit:
                raise DocumentIntelligenceError(
                    "concurrency_exceeded", "The tenant extraction concurrency limit is reached.", status_code=429
                )
            self._consume_quota(
                tenant_id, "document_intelligence.pages_processed", descriptor.page_count, f"extraction:{key}"
            )
            job = enqueue(
                tenant_id,
                actor_id,
                command,
                {"extraction_id": str(extraction_id), "engine": engine, "extraction_type": extraction_type},
                _job_key(command, key),
            )
            try:
                extraction = DocumentExtraction.objects.create(
                    id=extraction_id,
                    tenant_id=tenant_id,
                    created_by=actor_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    async_job_id=job.id,
                    idempotency_key=key,
                    engine=engine,
                    extraction_type=extraction_type,
                    template=template,
                    transition_history=_initial_history(key, actor_id, ExtractionStatus.QUEUED, "Extraction enqueued"),
                )
            except IntegrityError:
                extraction = DocumentExtraction.objects.for_tenant(tenant_id).get(idempotency_key=key)
                job = AsyncJob.objects.for_tenant(tenant_id).get(pk=extraction.async_job_id)
                return AcceptedWork(extraction, job)
        metrics.REQUESTS.labels(operation="extraction", outcome="accepted").inc()
        return AcceptedWork(extraction, job)

    def extract_text(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        version_id: UUID,
        engine: str,
        idempotency_key: str,
    ) -> AcceptedWork:
        return self.request_extraction(
            tenant_id,
            actor_id,
            {
                "document_id": document_id,
                "document_version_id": version_id,
                "engine": engine,
                "extraction_type": ExtractionType.TEXT,
            },
            idempotency_key,
        )

    def extract_structured_data(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        version_id: UUID,
        template_id: UUID,
        idempotency_key: str,
    ) -> AcceptedWork:
        return self.request_extraction(
            tenant_id,
            actor_id,
            {
                "document_id": document_id,
                "document_version_id": version_id,
                "template_id": template_id,
                "extraction_type": ExtractionType.STRUCTURED,
            },
            idempotency_key,
        )

    def extract_tables(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        version_id: UUID,
        engine: str,
        idempotency_key: str,
    ) -> AcceptedWork:
        return self.request_extraction(
            tenant_id,
            actor_id,
            {
                "document_id": document_id,
                "document_version_id": version_id,
                "engine": engine,
                "extraction_type": ExtractionType.TABLE,
            },
            idempotency_key,
        )

    def extract_by_template(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        version_id: UUID,
        template_id: UUID,
        idempotency_key: str,
    ) -> AcceptedWork:
        return self.request_extraction(
            tenant_id,
            actor_id,
            {
                "document_id": document_id,
                "document_version_id": version_id,
                "template_id": template_id,
                "extraction_type": ExtractionType.ZONE,
            },
            idempotency_key,
        )

    def run_extraction(self, tenant_id: UUID, extraction_id: UUID, async_job_id: UUID) -> DocumentExtraction:
        tenant_id = self._tenant(tenant_id)
        extraction_id = _uuid(extraction_id, "extraction_id")
        job_id = _uuid(async_job_id, "async_job_id")
        extraction = DocumentExtraction.objects.for_tenant(tenant_id).filter(pk=extraction_id).first()
        if extraction is None:
            raise DocumentIntelligenceError("resource_not_found", "Extraction not found.", status_code=404)
        if extraction.async_job_id != job_id:
            raise DocumentIntelligenceError(
                "job_mismatch", "The durable job does not own this extraction.", status_code=409
            )
        if extraction.status in {ExtractionStatus.COMPLETED, ExtractionStatus.NEEDS_REVIEW}:
            return extraction
        if extraction.status != ExtractionStatus.QUEUED:
            raise DocumentIntelligenceError(
                "illegal_transition", "Extraction cannot be run from its current state.", status_code=409
            )

        transition_key = f"{job_id}:start"
        extraction = EXTRACTION_STATE_MACHINE.apply(
            extraction,
            "start",
            transition_key=transition_key,
            tenant_id=tenant_id,
            metadata=_transition_metadata(extraction.created_by, "Worker started extraction"),
        )
        extraction.started_at = timezone.now()
        extraction.save(update_fields=["started_at", "updated_at"])
        publish_domain_event(
            tenant_id,
            "document_intelligence.extraction.started",
            "document_extraction",
            extraction.id,
            actor_id=extraction.created_by,
            payload={
                "status": extraction.status,
                "engine": extraction.engine,
                "extraction_type": extraction.extraction_type,
            },
        )

        try:
            adapter = self.providers.resolve_ocr(tenant_id, extraction.engine)
            self._provider_ready(tenant_id, adapter)
            descriptor = self._document(tenant_id, extraction.document_id, extraction.document_version_id)
            zones: tuple[Mapping[str, object], ...] = ()
            if extraction.template_id:
                zones = tuple(
                    ExtractionTemplateZone.objects.for_tenant(tenant_id)
                    .filter(template_id=extraction.template_id, is_deleted=False)
                    .order_by("page_number", "zone_name")
                    .values(
                        "zone_name",
                        "extraction_key",
                        "zone_type",
                        "x",
                        "y",
                        "width",
                        "height",
                        "page_number",
                        "expected_data_type",
                        "is_required",
                    )
                )
            request = OCRRequest(extraction.extraction_type, extraction.engine, extraction.template_id, zones)

            def extract_with_fresh_stream() -> OCRResult:
                content = self.dms.open_content(tenant_id, extraction.document_id, extraction.document_version_id)
                with closing(content):
                    return adapter.extract(content, request, str(job_id))

            result = self._execute_dependency(tenant_id, f"ocr.{extraction.engine}.extract", extract_with_fresh_stream)
            if not isinstance(result, OCRResult):
                raise InvalidProviderOutput("OCR adapter omitted validated result evidence")
            self._validate_ocr_result_policy(tenant_id, result)
            if descriptor.page_count is not None and len(result.pages) != descriptor.page_count:
                raise InvalidProviderOutput("OCR page evidence does not match DMS metadata")
            self._persist_extraction_result(tenant_id, extraction.id, job_id, result)
        except Exception as exc:
            state, code, message = _failure_from_exception(exc)
            self._fail_extraction(tenant_id, extraction.id, job_id, state, code, message)
            metrics.observe_provider_failure(extraction.engine, code)
            raise ProcessingFailure(code, message, status_code=504 if state == "timed_out" else 503) from exc
        return DocumentExtraction.objects.for_tenant(tenant_id).get(pk=extraction.id)

    def _persist_extraction_result(self, tenant_id: UUID, extraction_id: UUID, job_id: UUID, result: OCRResult) -> None:
        with transaction.atomic():
            extraction = DocumentExtraction.objects.for_tenant(tenant_id).select_for_update().get(pk=extraction_id)
            if extraction.status != ExtractionStatus.PROCESSING:
                raise DocumentIntelligenceError("illegal_transition", "Extraction is not processing.", status_code=409)
            if DocumentExtractionPage.objects.for_tenant(tenant_id).filter(extraction=extraction).exists():
                raise InvalidProviderOutput("partial page evidence already exists")
            pages = [
                DocumentExtractionPage(
                    tenant_id=tenant_id,
                    created_by=extraction.created_by,
                    extraction=extraction,
                    page_number=page.page_number,
                    width=page.width,
                    height=page.height,
                    raw_text=page.raw_text,
                    structured_data=dict(page.structured_data),
                    table_data=list(page.table_data),
                    confidence=page.confidence,
                    provider_metadata=dict(page.provider_metadata),
                )
                for page in result.pages
            ]
            # bulk_create is safe here only after explicit full_clean because the
            # model's append-only save hook intentionally rejects later mutation.
            for page in pages:
                page.full_clean()
            DocumentExtractionPage.objects.bulk_create(pages)
            output = {
                ExtractionType.TEXT: result.raw_text,
                ExtractionType.STRUCTURED: result.structured_data,
                ExtractionType.ZONE: result.structured_data,
                ExtractionType.TABLE: result.table_data,
            }[extraction.extraction_type]
            if output is None:
                raise InvalidProviderOutput("OCR result omitted output required by extraction type")
            extraction.raw_text = result.raw_text
            extraction.structured_data = dict(result.structured_data) if result.structured_data is not None else None
            extraction.table_data = list(result.table_data) if result.table_data is not None else None
            extraction.confidence = result.confidence
            extraction.page_count = len(result.pages)
            extraction.processing_time_ms = result.processing_time_ms
            extraction.completed_at = timezone.now()
            extraction.failure_code = ""
            extraction.failure_message = ""
            extraction.save()
            needs_review = result.confidence < Decimal(
                str(ConfigurationService().get_value(tenant_id, "review.low_confidence_threshold"))
            )
            command = "require_review" if needs_review else "complete"
            extraction = EXTRACTION_STATE_MACHINE.apply(
                extraction,
                command,
                tenant_id=tenant_id,
                transition_key=f"{job_id}:{command}",
                metadata=_transition_metadata(extraction.created_by, "Validated OCR evidence persisted"),
            )
            event_type = (
                "document_intelligence.extraction.needs_review"
                if needs_review
                else "document_intelligence.extraction.completed"
            )
            publish_domain_event(
                tenant_id,
                event_type,
                "document_extraction",
                extraction.id,
                actor_id=extraction.created_by,
                payload={
                    "status": extraction.status,
                    "engine": extraction.engine,
                    "extraction_type": extraction.extraction_type,
                    "page_count": len(result.pages),
                    "duration_ms": result.processing_time_ms,
                },
            )
        metrics.PAGES_PROCESSED.labels(engine=extraction.engine, outcome="validated").inc(len(result.pages))
        metrics.REQUESTS.labels(operation="extraction", outcome=extraction.status).inc()
        if needs_review:
            metrics.LOW_CONFIDENCE.labels(operation="extraction").inc()

    def _fail_extraction(
        self, tenant_id: UUID, extraction_id: UUID, job_id: UUID, state: str, code: str, message: str
    ) -> None:
        command = "time_out" if state == "timed_out" else "fail"
        with transaction.atomic():
            extraction = DocumentExtraction.objects.for_tenant(tenant_id).select_for_update().get(pk=extraction_id)
            if extraction.status in {ExtractionStatus.FAILED, ExtractionStatus.TIMED_OUT}:
                return
            extraction.failure_code = code
            extraction.failure_message = message
            extraction.completed_at = timezone.now()
            extraction.save(update_fields=["failure_code", "failure_message", "completed_at", "updated_at"])
            extraction = EXTRACTION_STATE_MACHINE.apply(
                extraction,
                command,
                tenant_id=tenant_id,
                transition_key=f"{job_id}:{command}",
                metadata=_transition_metadata(extraction.created_by, message),
            )
            publish_domain_event(
                tenant_id,
                "document_intelligence.extraction.failed",
                "document_extraction",
                extraction.id,
                actor_id=extraction.created_by,
                payload={"status": extraction.status, "engine": extraction.engine, "failure_code": code},
            )

    def retry_extraction(
        self, tenant_id: UUID, extraction_id: UUID, actor_id: UUID, idempotency_key: str
    ) -> AcceptedWork:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        key = _required_text(idempotency_key, "idempotency_key", 255)
        with transaction.atomic():
            extraction = (
                DocumentExtraction.objects.for_tenant(tenant_id).select_for_update().filter(pk=extraction_id).first()
            )
            if extraction is None or extraction.is_deleted:
                raise DocumentIntelligenceError("resource_not_found", "Extraction not found.", status_code=404)
            if extraction.status not in {ExtractionStatus.FAILED, ExtractionStatus.TIMED_OUT}:
                raise DocumentIntelligenceError(
                    "illegal_transition", "Only failed or timed-out extraction can retry.", status_code=409
                )
            job = enqueue(
                tenant_id,
                actor_id,
                "document_intelligence.extract",
                {
                    "extraction_id": str(extraction.id),
                    "engine": extraction.engine,
                    "extraction_type": extraction.extraction_type,
                },
                _job_key("document_intelligence.extract.retry", key),
            )
            extraction = EXTRACTION_STATE_MACHINE.apply(
                extraction,
                "retry",
                tenant_id=tenant_id,
                transition_key=key,
                metadata=_transition_metadata(actor_id, "Extraction retry requested"),
            )
            extraction.async_job_id = job.id
            extraction.failure_code = ""
            extraction.failure_message = ""
            extraction.completed_at = None
            extraction.save(
                update_fields=["async_job_id", "failure_code", "failure_message", "completed_at", "updated_at"]
            )
            return AcceptedWork(extraction, job)

    def cancel_extraction(self, tenant_id: UUID, extraction_id: UUID, actor_id: UUID) -> DocumentExtraction:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        extraction = self.get_extraction(tenant_id, extraction_id)
        if extraction.status == ExtractionStatus.CANCELLED:
            return extraction
        if extraction.status not in {ExtractionStatus.QUEUED, ExtractionStatus.PROCESSING}:
            raise DocumentIntelligenceError("illegal_transition", "Extraction cannot be cancelled.", status_code=409)
        extraction = EXTRACTION_STATE_MACHINE.apply(
            extraction,
            "cancel",
            tenant_id=tenant_id,
            transition_key=f"cancel:{extraction.id}:{extraction.status}",
            metadata=_transition_metadata(actor_id, "Extraction cancelled"),
        )
        try:
            job = AsyncJob.objects.for_tenant(tenant_id).get(pk=extraction.async_job_id)
            if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
                transition(
                    job.id, tenant_id, JobStatus.CANCELLED, reason="Domain extraction cancelled", actor_id=actor_id
                )
        except AsyncJob.DoesNotExist:
            logger.warning(
                "document_intelligence.durable_job_missing",
                extra={
                    "event": "document_intelligence.durable_job_missing",
                    "correlation_id": get_correlation_id() or str(extraction.id),
                    "tenant_id": str(tenant_id),
                    "extraction_id": str(extraction.id),
                },
            )
        return extraction

    def archive_extraction(self, tenant_id: UUID, extraction_id: UUID, actor_id: UUID) -> None:
        tenant_id = self._tenant(tenant_id)
        del actor_id
        with transaction.atomic():
            extraction = (
                DocumentExtraction.objects.for_tenant(tenant_id).select_for_update().filter(pk=extraction_id).first()
            )
            if extraction is None:
                raise DocumentIntelligenceError("resource_not_found", "Extraction not found.", status_code=404)
            if extraction.status in {ExtractionStatus.QUEUED, ExtractionStatus.PROCESSING}:
                raise DocumentIntelligenceError(
                    "illegal_transition", "Active extraction cannot be archived.", status_code=409
                )
            if not extraction.is_deleted:
                extraction.is_deleted = True
                extraction.deleted_at = timezone.now()
                extraction.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def get_extraction(self, tenant_id: UUID, extraction_id: UUID) -> DocumentExtraction:
        tenant_id = self._tenant(tenant_id)
        extraction = (
            DocumentExtraction.objects.for_tenant(tenant_id)
            .select_related("template")
            .filter(pk=extraction_id, is_deleted=False)
            .first()
        )
        if extraction is None:
            raise DocumentIntelligenceError("resource_not_found", "Extraction not found.", status_code=404)
        return extraction

    def list_extractions(self, tenant_id: UUID, filters: object) -> QuerySet[DocumentExtraction]:
        tenant_id = self._tenant(tenant_id)
        queryset = DocumentExtraction.objects.for_tenant(tenant_id).filter(is_deleted=False).select_related("template")
        return filters.apply(queryset) if hasattr(filters, "apply") else queryset


class DocumentClassificationService(_ServiceBase):
    """Classifier inference, review, training, and model lifecycle authority."""

    def __init__(
        self, *, classifier_provider_policy: Callable[[UUID], str | None] | None = None, **kwargs: object
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.classifier_provider_policy = classifier_provider_policy or (
            lambda tenant_id: str(ConfigurationService().get_value(tenant_id, "providers.default_classifier_provider"))
        )

    def request_classification(
        self, tenant_id: UUID, actor_id: UUID, document_id: UUID, version_id: UUID, idempotency_key: str
    ) -> AcceptedWork:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        document_id = _uuid(document_id, "document_id")
        version_id = _uuid(version_id, "version_id")
        key = _required_text(idempotency_key, "idempotency_key", 255)
        existing = DocumentClassification.objects.for_tenant(tenant_id).filter(idempotency_key=key).first()
        if existing:
            return AcceptedWork(existing, AsyncJob.objects.for_tenant(tenant_id).get(pk=existing.async_job_id))
        model = (
            ClassifierModelVersion.objects.for_tenant(tenant_id)
            .filter(status=ModelVersionStatus.ACTIVE)
            .select_related("training_job")
            .first()
        )
        if model is None:
            raise DocumentIntelligenceError("model_unavailable", "No active classifier model is available.")
        descriptor = self._document(tenant_id, document_id, version_id)
        if descriptor.page_count is None:
            raise DocumentIntelligenceError("page_count_unavailable", "Document page metadata is required.")
        try:
            adapter = self.providers.resolve_classifier(tenant_id, model.provider_key)
        except ProviderUnavailable as exc:
            raise DocumentIntelligenceError(
                "provider_unavailable", "The classifier provider is not configured."
            ) from exc
        self._provider_ready(tenant_id, adapter)
        self._require_entitlement(tenant_id, "document_intelligence.classification:create")
        classification_id = uuid.uuid4()
        command = "document_intelligence.classify"
        with transaction.atomic():
            self._consume_quota(
                tenant_id, "document_intelligence.pages_processed", descriptor.page_count, f"classification:{key}"
            )
            job = enqueue(
                tenant_id,
                actor_id,
                command,
                {"classification_id": str(classification_id), "model_version_id": str(model.id)},
                _job_key(command, key),
            )
            classification = DocumentClassification.objects.create(
                id=classification_id,
                tenant_id=tenant_id,
                created_by=actor_id,
                document_id=document_id,
                document_version_id=version_id,
                async_job_id=job.id,
                idempotency_key=key,
                model_version=model,
                transition_history=_initial_history(
                    key, actor_id, ClassificationStatus.QUEUED, "Classification enqueued"
                ),
            )
        metrics.REQUESTS.labels(operation="classification", outcome="accepted").inc()
        return AcceptedWork(classification, job)

    def run_classification(
        self, tenant_id: UUID, classification_id: UUID, async_job_id: UUID
    ) -> DocumentClassification:
        tenant_id = self._tenant(tenant_id)
        classification = (
            DocumentClassification.objects.for_tenant(tenant_id)
            .select_related("model_version")
            .filter(pk=classification_id)
            .first()
        )
        if classification is None:
            raise DocumentIntelligenceError("resource_not_found", "Classification not found.", status_code=404)
        job_id = _uuid(async_job_id, "async_job_id")
        if classification.async_job_id != job_id:
            raise DocumentIntelligenceError(
                "job_mismatch", "The durable job does not own this classification.", status_code=409
            )
        if classification.status == ClassificationStatus.COMPLETED:
            return classification
        classification = CLASSIFICATION_STATE_MACHINE.apply(
            classification,
            "start",
            tenant_id=tenant_id,
            transition_key=f"{job_id}:start",
            metadata=_transition_metadata(classification.created_by, "Worker started classification"),
        )
        try:
            adapter = self.providers.resolve_classifier(tenant_id, classification.model_version.provider_key)
            self._provider_ready(tenant_id, adapter)
            self._document(tenant_id, classification.document_id, classification.document_version_id)

            def classify_with_fresh_stream() -> object:
                content = self.dms.open_content(
                    tenant_id, classification.document_id, classification.document_version_id
                )
                with closing(content):
                    return adapter.classify(content, classification.model_version, str(job_id))

            result = self._execute_dependency(
                tenant_id,
                f"classifier.{classification.model_version.provider_key}.classify",
                classify_with_fresh_stream,
            )
            from .adapters import ClassificationResult

            if not isinstance(result, ClassificationResult):
                raise InvalidProviderOutput("classifier omitted validated result evidence")
            with transaction.atomic():
                locked = (
                    DocumentClassification.objects.for_tenant(tenant_id).select_for_update().get(pk=classification.id)
                )
                if locked.status != ClassificationStatus.PROCESSING:
                    raise DocumentIntelligenceError(
                        "illegal_transition", "Classification is not processing.", status_code=409
                    )
                primary = result.scores[0]
                secondary = (
                    result.scores[1]
                    if len(result.scores) > 1
                    and result.scores[1].confidence
                    > Decimal(
                        str(ConfigurationService().get_value(tenant_id, "classifier.secondary_confidence_threshold"))
                    )
                    else None
                )
                locked.category = primary.category
                locked.confidence = primary.confidence
                locked.secondary_category = secondary.category if secondary else ""
                locked.secondary_confidence = secondary.confidence if secondary else None
                locked.needs_review = primary.confidence < Decimal(
                    str(ConfigurationService().get_value(tenant_id, "review.low_confidence_threshold"))
                )
                locked.review_status = (
                    ClassificationReviewStatus.PENDING
                    if locked.needs_review
                    else ClassificationReviewStatus.NOT_REQUIRED
                )
                locked.processing_time_ms = result.processing_time_ms
                locked.completed_at = timezone.now()
                locked.save()
                for rank, score in enumerate(result.scores, 1):
                    evidence = DocumentClassificationScore(
                        tenant_id=tenant_id,
                        created_by=locked.created_by,
                        classification=locked,
                        category=score.category,
                        confidence=score.confidence,
                        rank=rank,
                    )
                    evidence.full_clean()
                    evidence.save()
                locked = CLASSIFICATION_STATE_MACHINE.apply(
                    locked,
                    "complete",
                    tenant_id=tenant_id,
                    transition_key=f"{job_id}:complete",
                    metadata=_transition_metadata(locked.created_by, "Validated classification evidence persisted"),
                )
                publish_domain_event(
                    tenant_id,
                    "document_intelligence.classification.completed",
                    "document_classification",
                    locked.id,
                    actor_id=locked.created_by,
                    payload={
                        "status": locked.status,
                        "model_version_id": str(locked.model_version_id),
                        "duration_ms": result.processing_time_ms,
                    },
                )
                if locked.needs_review:
                    publish_domain_event(
                        tenant_id,
                        "document_intelligence.classification.low_confidence",
                        "document_classification",
                        locked.id,
                        actor_id=locked.created_by,
                        payload={"status": locked.status, "review_status": locked.review_status},
                    )
                    metrics.LOW_CONFIDENCE.labels(operation="classification").inc()
        except Exception as exc:
            state, code, message = _failure_from_exception(exc)
            command = "time_out" if state == "timed_out" else "fail"
            with transaction.atomic():
                locked = (
                    DocumentClassification.objects.for_tenant(tenant_id).select_for_update().get(pk=classification.id)
                )
                if locked.status == ClassificationStatus.PROCESSING:
                    locked.failure_code = code
                    locked.failure_message = message
                    locked.completed_at = timezone.now()
                    locked.save(update_fields=["failure_code", "failure_message", "completed_at", "updated_at"])
                    CLASSIFICATION_STATE_MACHINE.apply(
                        locked,
                        command,
                        tenant_id=tenant_id,
                        transition_key=f"{job_id}:{command}",
                        metadata=_transition_metadata(locked.created_by, message),
                    )
            metrics.observe_provider_failure(classification.model_version.provider_key, code)
            raise ProcessingFailure(code, message, status_code=504 if state == "timed_out" else 503) from exc
        metrics.REQUESTS.labels(operation="classification", outcome="completed").inc()
        return DocumentClassification.objects.for_tenant(tenant_id).get(pk=classification.id)

    def get_classification(self, tenant_id: UUID, classification_id: UUID) -> DocumentClassification:
        tenant_id = self._tenant(tenant_id)
        value = (
            DocumentClassification.objects.for_tenant(tenant_id)
            .select_related("model_version")
            .filter(pk=classification_id, is_deleted=False)
            .first()
        )
        if value is None:
            raise DocumentIntelligenceError("resource_not_found", "Classification not found.", status_code=404)
        return value

    def list_classifications(self, tenant_id: UUID, filters: object) -> QuerySet[DocumentClassification]:
        tenant_id = self._tenant(tenant_id)
        queryset = (
            DocumentClassification.objects.for_tenant(tenant_id)
            .filter(is_deleted=False)
            .select_related("model_version")
        )
        return filters.apply(queryset) if hasattr(filters, "apply") else queryset

    def get_confidence_distribution(
        self, tenant_id: UUID, classification_id: UUID
    ) -> QuerySet[DocumentClassificationScore]:
        classification = self.get_classification(tenant_id, classification_id)
        return (
            DocumentClassificationScore.objects.for_tenant(self._tenant(tenant_id))
            .filter(classification=classification)
            .order_by("rank")
        )

    def review_classification(
        self, tenant_id: UUID, classification_id: UUID, actor_id: UUID, category: str, note: str
    ) -> DocumentClassification:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        category = _required_text(category, "category", 80)
        if not _CATEGORY_RE.fullmatch(category):
            raise DocumentIntelligenceError("validation_error", "category is invalid.")
        note = str(note).strip()
        note_maximum = int(ConfigurationService().get_value(tenant_id, "review.note_max_length"))
        if len(note) > note_maximum:
            raise DocumentIntelligenceError("validation_error", f"review note exceeds {note_maximum} characters.")
        with transaction.atomic():
            classification = (
                DocumentClassification.objects.for_tenant(tenant_id)
                .select_for_update()
                .filter(pk=classification_id, is_deleted=False)
                .first()
            )
            if classification is None:
                raise DocumentIntelligenceError("resource_not_found", "Classification not found.", status_code=404)
            if classification.status != ClassificationStatus.COMPLETED:
                raise DocumentIntelligenceError(
                    "illegal_transition", "Only completed inference can be reviewed.", status_code=409
                )
            if classification.reviewed_at is not None:
                if classification.reviewed_category == category and classification.review_note == note:
                    return classification
                raise DocumentIntelligenceError(
                    "review_conflict", "Classification was already reviewed.", status_code=409
                )
            classification.reviewed_category = category
            classification.reviewed_by = actor_id
            classification.reviewed_at = timezone.now()
            classification.review_note = note
            classification.review_status = (
                ClassificationReviewStatus.CONFIRMED
                if category == classification.category
                else ClassificationReviewStatus.CORRECTED
            )
            classification.save(
                update_fields=[
                    "reviewed_category",
                    "reviewed_by",
                    "reviewed_at",
                    "review_note",
                    "review_status",
                    "updated_at",
                ]
            )
            publish_domain_event(
                tenant_id,
                "document_intelligence.classification.reviewed",
                "document_classification",
                classification.id,
                actor_id=actor_id,
                payload={"status": classification.status, "review_status": classification.review_status},
            )
            return classification

    def retry_classification(
        self, tenant_id: UUID, classification_id: UUID, actor_id: UUID, idempotency_key: str
    ) -> AcceptedWork:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        key = _required_text(idempotency_key, "idempotency_key", 255)
        with transaction.atomic():
            value = (
                DocumentClassification.objects.for_tenant(tenant_id)
                .select_for_update()
                .filter(pk=classification_id)
                .first()
            )
            if value is None or value.is_deleted:
                raise DocumentIntelligenceError("resource_not_found", "Classification not found.", status_code=404)
            if value.status not in {ClassificationStatus.FAILED, ClassificationStatus.TIMED_OUT}:
                raise DocumentIntelligenceError(
                    "illegal_transition", "Classification cannot be retried.", status_code=409
                )
            # Reclassification is a new immutable inference record.
            return self.request_classification(
                tenant_id,
                actor_id,
                value.document_id,
                value.document_version_id,
                key,
            )

    def cancel_classification(self, tenant_id: UUID, classification_id: UUID, actor_id: UUID) -> DocumentClassification:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        value = self.get_classification(tenant_id, classification_id)
        if value.status == ClassificationStatus.CANCELLED:
            return value
        value = CLASSIFICATION_STATE_MACHINE.apply(
            value,
            "cancel",
            tenant_id=tenant_id,
            transition_key=f"cancel:{value.id}:{value.status}",
            metadata=_transition_metadata(actor_id, "Classification cancelled"),
        )
        job = AsyncJob.objects.for_tenant(tenant_id).filter(pk=value.async_job_id).first()
        if job and job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
            transition(
                job.id, tenant_id, JobStatus.CANCELLED, reason="Domain classification cancelled", actor_id=actor_id
            )
        return value

    def archive_classification(self, tenant_id: UUID, classification_id: UUID, actor_id: UUID) -> None:
        tenant_id = self._tenant(tenant_id)
        del actor_id
        with transaction.atomic():
            value = (
                DocumentClassification.objects.for_tenant(tenant_id)
                .select_for_update()
                .filter(pk=classification_id)
                .first()
            )
            if value is None:
                raise DocumentIntelligenceError("resource_not_found", "Classification not found.", status_code=404)
            if value.status in {ClassificationStatus.QUEUED, ClassificationStatus.PROCESSING}:
                raise DocumentIntelligenceError(
                    "illegal_transition", "Active classification cannot be archived.", status_code=409
                )
            value.is_deleted = True
            value.deleted_at = timezone.now()
            value.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def train_classifier(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        name: str,
        items: Sequence[Mapping[str, object]],
        requested_version: str,
        idempotency_key: str,
    ) -> AcceptedWork:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        name = _required_text(name, "name", 255)
        requested_version = _required_text(requested_version, "requested_version", 50)
        key = _required_text(idempotency_key, "idempotency_key", 255)
        existing = ClassifierTrainingJob.objects.for_tenant(tenant_id).filter(idempotency_key=key).first()
        if existing:
            return AcceptedWork(existing, AsyncJob.objects.for_tenant(tenant_id).get(pk=existing.async_job_id))
        normalized: list[dict[str, str]] = []
        counts: Counter[str] = Counter()
        for item in items:
            if not isinstance(item, Mapping):
                raise DocumentIntelligenceError("validation_error", "Every training item must be an object.")
            document_id = _uuid(item.get("document_id"), "document_id")
            version_id = _uuid(item.get("document_version_id"), "document_version_id")
            category = _required_text(item.get("category"), "category", 80)
            if not _CATEGORY_RE.fullmatch(category):
                raise DocumentIntelligenceError("validation_error", "Training category is invalid.")
            descriptor = self._document(tenant_id, document_id, version_id)
            if descriptor.page_count is None:
                raise DocumentIntelligenceError(
                    "page_count_unavailable", "Training document page metadata is required."
                )
            normalized.append(
                {"document_id": str(document_id), "document_version_id": str(version_id), "category": category}
            )
            counts[category] += 1
        minimum_documents = int(ConfigurationService().get_value(tenant_id, "classifier.minimum_training_documents"))
        minimum_per_category = int(
            ConfigurationService().get_value(tenant_id, "classifier.minimum_documents_per_category")
        )
        if len(normalized) < minimum_documents:
            raise DocumentIntelligenceError(
                "training_minimum", f"At least {minimum_documents} training documents are required."
            )
        if any(count < minimum_per_category for count in counts.values()):
            raise DocumentIntelligenceError(
                "category_minimum", f"Every category requires at least {minimum_per_category} documents."
            )
        provider_key = self.classifier_provider_policy(tenant_id)
        active = ClassifierModelVersion.objects.for_tenant(tenant_id).filter(status=ModelVersionStatus.ACTIVE).first()
        provider_key = provider_key or (active.provider_key if active else None)
        if not provider_key:
            raise DocumentIntelligenceError("provider_unavailable", "No classifier provider policy is configured.")
        try:
            adapter = self.providers.resolve_classifier(tenant_id, provider_key)
        except ProviderUnavailable as exc:
            raise DocumentIntelligenceError(
                "provider_unavailable", "The classifier provider is not configured."
            ) from exc
        self._provider_ready(tenant_id, adapter)
        self._require_entitlement(tenant_id, "document_intelligence.training:create")
        training_id = uuid.uuid4()
        command = "document_intelligence.train_classifier"
        with transaction.atomic():
            self._consume_quota(
                tenant_id, "document_intelligence.training_documents", len(normalized), f"training:{key}"
            )
            job = enqueue(
                tenant_id,
                actor_id,
                command,
                {"training_job_id": str(training_id), "provider_key": provider_key},
                _job_key(command, key),
            )
            training = ClassifierTrainingJob.objects.create(
                id=training_id,
                tenant_id=tenant_id,
                created_by=actor_id,
                async_job_id=job.id,
                idempotency_key=key,
                name=name,
                training_items=normalized,
                training_data_count=len(normalized),
                category_counts=dict(counts),
                requested_version=requested_version,
                transition_history=_initial_history(
                    key, actor_id, TrainingStatus.QUEUED, "Classifier training enqueued"
                ),
            )
        return AcceptedWork(training, job)

    def run_training(self, tenant_id: UUID, training_job_id: UUID, async_job_id: UUID) -> ClassifierTrainingJob:
        tenant_id = self._tenant(tenant_id)
        training = ClassifierTrainingJob.objects.for_tenant(tenant_id).filter(pk=training_job_id).first()
        if training is None:
            raise DocumentIntelligenceError("resource_not_found", "Training job not found.", status_code=404)
        job_id = _uuid(async_job_id, "async_job_id")
        if training.async_job_id != job_id:
            raise DocumentIntelligenceError(
                "job_mismatch", "The durable job does not own this training run.", status_code=409
            )
        if training.status == TrainingStatus.COMPLETED:
            return training
        training = TRAINING_STATE_MACHINE.apply(
            training,
            "start",
            tenant_id=tenant_id,
            transition_key=f"{job_id}:start",
            metadata=_transition_metadata(training.created_by, "Worker started classifier training"),
        )
        training.started_at = timezone.now()
        training.save(update_fields=["started_at", "updated_at"])
        job = AsyncJob.objects.for_tenant(tenant_id).get(pk=job_id)
        provider_key = str(job.payload.get("provider_key", ""))
        publish_domain_event(
            tenant_id,
            "document_intelligence.training.started",
            "classifier_training_job",
            training.id,
            actor_id=training.created_by,
            payload={
                "status": training.status,
                "provider_key": provider_key,
                "training_data_count": training.training_data_count,
            },
        )
        result = None
        adapter = None
        try:
            adapter = self.providers.resolve_classifier(tenant_id, provider_key)
            self._provider_ready(tenant_id, adapter)
            stage_training = getattr(adapter, "stage_training", adapter.train)
            result = self._execute_dependency(
                tenant_id,
                f"classifier.{provider_key}.train",
                lambda: stage_training(training.training_items, training.requested_version, str(job_id)),
            )
            from .adapters import TrainingResult

            if not isinstance(result, TrainingResult):
                raise InvalidProviderOutput("classifier training omitted validated artifact evidence")
            if result.provider_key != provider_key:
                raise InvalidProviderOutput("training result provider does not match the requested provider")
            with transaction.atomic():
                locked = ClassifierTrainingJob.objects.for_tenant(tenant_id).select_for_update().get(pk=training.id)
                locked.accuracy = result.accuracy
                locked.completed_at = timezone.now()
                locked.save(update_fields=["accuracy", "completed_at", "updated_at"])
                locked = TRAINING_STATE_MACHINE.apply(
                    locked,
                    "complete",
                    tenant_id=tenant_id,
                    transition_key=f"{job_id}:complete",
                    metadata=_transition_metadata(locked.created_by, "Validated classifier artifact persisted"),
                )
                ClassifierModelVersion.objects.create(
                    tenant_id=tenant_id,
                    created_by=locked.created_by,
                    version=locked.requested_version,
                    provider_key=result.provider_key,
                    artifact_ref=result.artifact_ref,
                    artifact_checksum=result.artifact_checksum.lower(),
                    training_job=locked,
                    accuracy=result.accuracy,
                    status=ModelVersionStatus.CANDIDATE,
                    transition_history=_initial_history(
                        f"{job_id}:candidate",
                        locked.created_by,
                        ModelVersionStatus.CANDIDATE,
                        "Training artifact created",
                    ),
                )
                publish_domain_event(
                    tenant_id,
                    "document_intelligence.training.completed",
                    "classifier_training_job",
                    locked.id,
                    actor_id=locked.created_by,
                    payload={
                        "status": locked.status,
                        "provider_key": result.provider_key,
                        "training_data_count": locked.training_data_count,
                    },
                )
            self._execute_dependency(
                tenant_id,
                f"classifier.{provider_key}.publish_artifact",
                lambda: adapter.publish_artifact(result.artifact_ref, result.artifact_checksum),
            )
        except Exception as exc:
            if adapter is not None and result is not None:
                try:
                    self._execute_dependency(
                        tenant_id,
                        f"classifier.{provider_key}.abort_artifact",
                        lambda: adapter.abort_artifact(result.artifact_ref),
                    )
                except Exception as compensation_exc:
                    logger.critical(
                        "document_intelligence.artifact_compensation_failed",
                        extra={
                            "event": "document_intelligence.artifact_compensation_failed",
                            "correlation_id": get_correlation_id() or str(job_id),
                            "tenant_id": str(tenant_id),
                            "training_job_id": str(training.id),
                            "error": type(compensation_exc).__name__,
                        },
                    )
            state, code, message = _failure_from_exception(exc)
            command = "time_out" if state == "timed_out" else "fail"
            with transaction.atomic():
                locked = ClassifierTrainingJob.objects.for_tenant(tenant_id).select_for_update().get(pk=training.id)
                if locked.status == TrainingStatus.TRAINING:
                    locked.failure_code = code
                    locked.failure_message = message
                    locked.completed_at = timezone.now()
                    locked.save(update_fields=["failure_code", "failure_message", "completed_at", "updated_at"])
                    locked = TRAINING_STATE_MACHINE.apply(
                        locked,
                        command,
                        tenant_id=tenant_id,
                        transition_key=f"{job_id}:{command}",
                        metadata=_transition_metadata(locked.created_by, message),
                    )
                    publish_domain_event(
                        tenant_id,
                        "document_intelligence.training.failed",
                        "classifier_training_job",
                        locked.id,
                        actor_id=locked.created_by,
                        payload={"status": locked.status, "provider_key": provider_key, "failure_code": code},
                    )
            metrics.observe_provider_failure(provider_key, code)
            raise ProcessingFailure(code, message, status_code=504 if state == "timed_out" else 503) from exc
        return ClassifierTrainingJob.objects.for_tenant(tenant_id).get(pk=training.id)

    def retry_training(
        self, tenant_id: UUID, training_job_id: UUID, actor_id: UUID, idempotency_key: str
    ) -> AcceptedWork:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        key = _required_text(idempotency_key, "idempotency_key", 255)
        with transaction.atomic():
            training = (
                ClassifierTrainingJob.objects.for_tenant(tenant_id)
                .select_for_update()
                .filter(pk=training_job_id)
                .first()
            )
            if training is None:
                raise DocumentIntelligenceError("resource_not_found", "Training job not found.", status_code=404)
            if training.status not in {TrainingStatus.FAILED, TrainingStatus.TIMED_OUT}:
                raise DocumentIntelligenceError(
                    "illegal_transition", "Training job cannot be retried.", status_code=409
                )
            old_job = AsyncJob.objects.for_tenant(tenant_id).get(pk=training.async_job_id)
            provider_key = str(old_job.payload.get("provider_key", ""))
            job = enqueue(
                tenant_id,
                actor_id,
                "document_intelligence.train_classifier",
                {"training_job_id": str(training.id), "provider_key": provider_key},
                _job_key("document_intelligence.train_classifier.retry", key),
            )
            training = TRAINING_STATE_MACHINE.apply(
                training,
                "retry",
                tenant_id=tenant_id,
                transition_key=key,
                metadata=_transition_metadata(actor_id, "Classifier training retry requested"),
            )
            training.async_job_id = job.id
            training.failure_code = ""
            training.failure_message = ""
            training.completed_at = None
            training.save(
                update_fields=["async_job_id", "failure_code", "failure_message", "completed_at", "updated_at"]
            )
            return AcceptedWork(training, job)

    def cancel_training(self, tenant_id: UUID, training_job_id: UUID, actor_id: UUID) -> ClassifierTrainingJob:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        training = ClassifierTrainingJob.objects.for_tenant(tenant_id).filter(pk=training_job_id).first()
        if training is None:
            raise DocumentIntelligenceError("resource_not_found", "Training job not found.", status_code=404)
        if training.status == TrainingStatus.CANCELLED:
            return training
        training = TRAINING_STATE_MACHINE.apply(
            training,
            "cancel",
            tenant_id=tenant_id,
            transition_key=f"cancel:{training.id}:{training.status}",
            metadata=_transition_metadata(actor_id, "Classifier training cancelled"),
        )
        job = AsyncJob.objects.for_tenant(tenant_id).filter(pk=training.async_job_id).first()
        if job and job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
            transition(job.id, tenant_id, JobStatus.CANCELLED, reason="Domain training cancelled", actor_id=actor_id)
        return training

    def activate_model_version(
        self, tenant_id: UUID, model_version_id: UUID, actor_id: UUID, transition_key: str
    ) -> ClassifierModelVersion:
        return self._activate_model(tenant_id, model_version_id, actor_id, transition_key, rollback=False)

    def rollback_model_version(
        self, tenant_id: UUID, model_version_id: UUID, actor_id: UUID, transition_key: str
    ) -> ClassifierModelVersion:
        return self._activate_model(tenant_id, model_version_id, actor_id, transition_key, rollback=True)

    def _activate_model(
        self, tenant_id: UUID, model_version_id: UUID, actor_id: UUID, transition_key: str, *, rollback: bool
    ) -> ClassifierModelVersion:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        transition_key = _required_text(transition_key, "transition_key", 255)
        with transaction.atomic():
            target = (
                ClassifierModelVersion.objects.for_tenant(tenant_id)
                .select_for_update()
                .filter(pk=model_version_id)
                .first()
            )
            if target is None:
                raise DocumentIntelligenceError("resource_not_found", "Model version not found.", status_code=404)
            required_status = ModelVersionStatus.RETIRED if rollback else ModelVersionStatus.CANDIDATE
            if target.status != required_status:
                raise DocumentIntelligenceError(
                    "illegal_transition", "Model version cannot perform this action.", status_code=409
                )
            accuracy_threshold = Decimal(
                str(ConfigurationService().get_value(tenant_id, "classifier.activation_accuracy_threshold"))
            )
            if target.accuracy <= accuracy_threshold:
                raise DocumentIntelligenceError(
                    "accuracy_threshold", f"Model accuracy must be greater than {accuracy_threshold}."
                )
            try:
                adapter = self.providers.resolve_classifier(tenant_id, target.provider_key)
                ready = self._execute_dependency(
                    tenant_id,
                    f"classifier.{target.provider_key}.validate_artifact",
                    lambda: adapter.validate_artifact(target.artifact_ref, target.artifact_checksum),
                )
            except ProviderUnavailable as exc:
                raise DocumentIntelligenceError(
                    "provider_unavailable", "The classifier provider is unavailable.", status_code=503
                ) from exc
            if ready is not True:
                raise DocumentIntelligenceError(
                    "artifact_unavailable", "The classifier artifact is not ready.", status_code=503
                )
            current = (
                ClassifierModelVersion.objects.for_tenant(tenant_id)
                .select_for_update()
                .filter(status=ModelVersionStatus.ACTIVE)
                .exclude(pk=target.pk)
                .first()
            )
            now = timezone.now()
            if current:
                current = MODEL_VERSION_STATE_MACHINE.apply(
                    current,
                    "retire",
                    tenant_id=tenant_id,
                    transition_key=f"{transition_key}:retire-current",
                    metadata=_transition_metadata(actor_id, "Superseded by model activation"),
                )
                current.retired_at = now
                current.save(update_fields=["retired_at", "updated_at"])
            command = "rollback" if rollback else "activate"
            target = MODEL_VERSION_STATE_MACHINE.apply(
                target,
                command,
                tenant_id=tenant_id,
                transition_key=transition_key,
                context={"artifact_ready": True},
                metadata=_transition_metadata(
                    actor_id, "Classifier model rollback" if rollback else "Classifier model activation"
                ),
            )
            target.activated_by = actor_id
            target.activated_at = now
            target.retired_at = None
            target.save(update_fields=["activated_by", "activated_at", "retired_at", "updated_at"])
            publish_domain_event(
                tenant_id,
                "document_intelligence.model.rolled_back" if rollback else "document_intelligence.model.activated",
                "classifier_model_version",
                target.id,
                actor_id=actor_id,
                payload={
                    "status": target.status,
                    "provider_key": target.provider_key,
                    "model_version_id": str(target.id),
                },
            )
            return target

    def cancel_stale_training_jobs(self, tenant_id: UUID, cutoff: datetime) -> int:
        tenant_id = self._tenant(tenant_id)
        if timezone.is_naive(cutoff):
            raise DocumentIntelligenceError("validation_error", "cutoff must be timezone-aware.")
        ids = list(
            ClassifierTrainingJob.objects.for_tenant(tenant_id)
            .filter(status__in=[TrainingStatus.QUEUED, TrainingStatus.TRAINING], updated_at__lt=cutoff)
            .values_list("id", flat=True)
        )
        cancelled = 0
        for job_id in ids:
            try:
                self.cancel_training(tenant_id, job_id, uuid.UUID(int=0))
                cancelled += 1
            except DocumentIntelligenceError:
                continue
        return cancelled

    def list_training_jobs(self, tenant_id: UUID, filters: object) -> QuerySet[ClassifierTrainingJob]:
        queryset = ClassifierTrainingJob.objects.for_tenant(self._tenant(tenant_id)).all()
        return filters.apply(queryset) if hasattr(filters, "apply") else queryset

    def get_training_job(self, tenant_id: UUID, training_job_id: UUID) -> ClassifierTrainingJob:
        value = ClassifierTrainingJob.objects.for_tenant(self._tenant(tenant_id)).filter(pk=training_job_id).first()
        if value is None:
            raise DocumentIntelligenceError("resource_not_found", "Training job not found.", status_code=404)
        return value

    def list_model_versions(self, tenant_id: UUID, filters: object) -> QuerySet[ClassifierModelVersion]:
        queryset = ClassifierModelVersion.objects.for_tenant(self._tenant(tenant_id)).select_related("training_job")
        return filters.apply(queryset) if hasattr(filters, "apply") else queryset

    def get_model_version(self, tenant_id: UUID, model_version_id: UUID) -> ClassifierModelVersion:
        value = (
            ClassifierModelVersion.objects.for_tenant(self._tenant(tenant_id))
            .select_related("training_job")
            .filter(pk=model_version_id)
            .first()
        )
        if value is None:
            raise DocumentIntelligenceError("resource_not_found", "Model version not found.", status_code=404)
        return value


class TemplateMatchingService(_ServiceBase):
    """Versioned template and normalized zone lifecycle."""

    def create_template(
        self, tenant_id: UUID, actor_id: UUID, data: Mapping[str, object], zones: Sequence[Mapping[str, object]]
    ) -> ExtractionTemplate:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        supplied_key = data.get("idempotency_key")
        if supplied_key in (None, ""):
            canonical = json.dumps({"data": dict(data), "zones": list(zones)}, sort_keys=True, default=str)
            idempotency_key = f"template:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
        else:
            idempotency_key = _required_text(supplied_key, "idempotency_key", 255)
        existing = ExtractionTemplate.objects.for_tenant(tenant_id).filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing
        with transaction.atomic():
            template = ExtractionTemplate.objects.create(
                tenant_id=tenant_id,
                created_by=actor_id,
                idempotency_key=idempotency_key,
                name=_required_text(data.get("name"), "name", 255),
                description=str(data.get("description", "")).strip(),
                document_category=str(data.get("document_category", "")).strip(),
                engine=_required_text(data.get("engine"), "engine", 50),
                match_threshold=Decimal(
                    str(
                        data.get(
                            "match_threshold",
                            ConfigurationService().get_value(tenant_id, "templates.default_match_threshold"),
                        )
                    )
                ),
                status=TemplateStatus.DRAFT,
                transition_history=_initial_history(
                    str(uuid.uuid4()), actor_id, TemplateStatus.DRAFT, "Template created"
                ),
            )
            self._replace_zones_locked(tenant_id, template, actor_id, zones)
            publish_domain_event(
                tenant_id,
                "document_intelligence.template.created",
                "extraction_template",
                template.id,
                actor_id=actor_id,
                payload={"status": template.status, "engine": template.engine},
            )
            return template

    def update_template(
        self, tenant_id: UUID, template_id: UUID, actor_id: UUID, data: Mapping[str, object]
    ) -> ExtractionTemplate:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            template = (
                ExtractionTemplate.objects.for_tenant(tenant_id)
                .select_for_update()
                .filter(pk=template_id, is_deleted=False)
                .first()
            )
            if template is None:
                raise DocumentIntelligenceError("resource_not_found", "Template not found.", status_code=404)
            if template.status == TemplateStatus.ACTIVE:
                clone = self.clone_template_revision(
                    tenant_id, template.id, actor_id, str(data.get("name", template.name))
                )
                return self.update_template(tenant_id, clone.id, actor_id, data)
            if template.status == TemplateStatus.RETIRED:
                raise DocumentIntelligenceError(
                    "immutable_template", "Retired templates are immutable.", status_code=409
                )
            allowed = {"name", "description", "document_category", "engine", "match_threshold"}
            for field, value in data.items():
                if field not in allowed:
                    raise DocumentIntelligenceError("validation_error", f"{field} cannot be updated.")
                setattr(template, field, value.strip() if isinstance(value, str) else value)
            template.full_clean()
            template.save()
            return template

    def replace_zones(
        self, tenant_id: UUID, template_id: UUID, actor_id: UUID, zones: Sequence[Mapping[str, object]]
    ) -> list[ExtractionTemplateZone]:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            template = (
                ExtractionTemplate.objects.for_tenant(tenant_id)
                .select_for_update()
                .filter(pk=template_id, is_deleted=False)
                .first()
            )
            if template is None:
                raise DocumentIntelligenceError("resource_not_found", "Template not found.", status_code=404)
            return self._replace_zones_locked(tenant_id, template, actor_id, zones)

    def _replace_zones_locked(
        self, tenant_id: UUID, template: ExtractionTemplate, actor_id: UUID, zones: Sequence[Mapping[str, object]]
    ) -> list[ExtractionTemplateZone]:
        if template.status not in {TemplateStatus.DRAFT, TemplateStatus.INACTIVE}:
            raise DocumentIntelligenceError("immutable_template", "Template zones cannot be changed.", status_code=409)
        normalized = self.validate_zones(tenant_id, template.id, zones, _locked_template=template)
        existing = {
            zone.zone_name: zone
            for zone in ExtractionTemplateZone.objects.for_tenant(tenant_id)
            .select_for_update()
            .filter(template=template)
        }
        retained: set[UUID] = set()
        result: list[ExtractionTemplateZone] = []
        for values in normalized:
            zone = existing.get(str(values["zone_name"]))
            if zone is None:
                zone = ExtractionTemplateZone(tenant_id=tenant_id, created_by=actor_id, template=template)
            for key, value in values.items():
                setattr(zone, key, value)
            zone.is_deleted = False
            zone.deleted_at = None
            zone.full_clean()
            zone.save()
            retained.add(zone.id)
            result.append(zone)
        for zone in existing.values():
            if zone.id not in retained and not zone.is_deleted:
                zone.is_deleted = True
                zone.deleted_at = timezone.now()
                zone.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
        return result

    def clone_template_revision(
        self, tenant_id: UUID, template_id: UUID, actor_id: UUID, name: str
    ) -> ExtractionTemplate:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            source = (
                ExtractionTemplate.objects.for_tenant(tenant_id)
                .select_for_update()
                .filter(pk=template_id, is_deleted=False)
                .first()
            )
            if source is None:
                raise DocumentIntelligenceError("resource_not_found", "Template not found.", status_code=404)
            clone_key = (
                "template-clone:"
                + hashlib.sha256(f"{source.id}:{source.version + 1}:{name.strip()}".encode("utf-8")).hexdigest()
            )
            existing = ExtractionTemplate.objects.for_tenant(tenant_id).filter(idempotency_key=clone_key).first()
            if existing is not None:
                return existing
            clone = ExtractionTemplate.objects.create(
                tenant_id=tenant_id,
                created_by=actor_id,
                idempotency_key=clone_key,
                name=_required_text(name, "name", 255),
                description=source.description,
                document_category=source.document_category,
                engine=source.engine,
                match_threshold=source.match_threshold,
                status=TemplateStatus.DRAFT,
                version=source.version + 1,
                transition_history=_initial_history(
                    str(uuid.uuid4()), actor_id, TemplateStatus.DRAFT, "Template revision cloned"
                ),
            )
            zones = list(
                ExtractionTemplateZone.objects.for_tenant(tenant_id)
                .filter(template=source, is_deleted=False)
                .values(
                    "zone_name",
                    "extraction_key",
                    "zone_type",
                    "x",
                    "y",
                    "width",
                    "height",
                    "page_number",
                    "expected_data_type",
                    "is_required",
                )
            )
            self._replace_zones_locked(tenant_id, clone, actor_id, zones)
            return clone

    def activate_template(
        self, tenant_id: UUID, template_id: UUID, actor_id: UUID, transition_key: str
    ) -> ExtractionTemplate:
        tenant_id = self._tenant(tenant_id)
        actor_id = _uuid(actor_id, "actor_id")
        template = self.get_template(tenant_id, template_id)
        if (
            not ExtractionTemplateZone.objects.for_tenant(tenant_id)
            .filter(template=template, is_deleted=False)
            .exists()
        ):
            raise DocumentIntelligenceError("zones_required", "At least one valid zone is required.")
        try:
            adapter = self.providers.resolve_ocr(tenant_id, template.engine)
        except ProviderUnavailable as exc:
            raise DocumentIntelligenceError(
                "provider_unavailable", "The template OCR provider is unavailable."
            ) from exc
        self._provider_ready(tenant_id, adapter)
        template = TEMPLATE_STATE_MACHINE.apply(
            template,
            "activate",
            tenant_id=tenant_id,
            transition_key=_required_text(transition_key, "transition_key", 255),
            metadata=_transition_metadata(actor_id, "Template activated"),
        )
        template.activated_at = timezone.now()
        template.save(update_fields=["activated_at", "updated_at"])
        publish_domain_event(
            tenant_id,
            "document_intelligence.template.activated",
            "extraction_template",
            template.id,
            actor_id=actor_id,
            payload={"status": template.status, "engine": template.engine},
        )
        return template

    def deactivate_template(
        self, tenant_id: UUID, template_id: UUID, actor_id: UUID, transition_key: str
    ) -> ExtractionTemplate:
        template = self.get_template(tenant_id, template_id)
        return TEMPLATE_STATE_MACHINE.apply(
            template,
            "deactivate",
            tenant_id=self._tenant(tenant_id),
            transition_key=_required_text(transition_key, "transition_key", 255),
            metadata=_transition_metadata(_uuid(actor_id, "actor_id"), "Template deactivated"),
        )

    def archive_template(self, tenant_id: UUID, template_id: UUID, actor_id: UUID) -> None:
        tenant_id = self._tenant(tenant_id)
        del actor_id
        with transaction.atomic():
            template = (
                ExtractionTemplate.objects.for_tenant(tenant_id).select_for_update().filter(pk=template_id).first()
            )
            if template is None:
                raise DocumentIntelligenceError("resource_not_found", "Template not found.", status_code=404)
            if template.status == TemplateStatus.ACTIVE:
                raise DocumentIntelligenceError(
                    "illegal_transition", "Active template cannot be archived.", status_code=409
                )
            template.is_deleted = True
            template.deleted_at = timezone.now()
            template.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def validate_zones(
        self,
        tenant_id: UUID,
        template_id: UUID,
        zones: Sequence[Mapping[str, object]],
        *,
        _locked_template: ExtractionTemplate | None = None,
    ) -> list[dict[str, object]]:
        tenant_id = self._tenant(tenant_id)
        with transaction.atomic():
            template = (
                _locked_template
                or ExtractionTemplate.objects.for_tenant(tenant_id).select_for_update().filter(pk=template_id).first()
            )
            if template is None:
                raise DocumentIntelligenceError("resource_not_found", "Template not found.", status_code=404)
            normalized: list[dict[str, object]] = []
            names: set[str] = set()
            keys: set[str] = set()
            for item in zones:
                if not isinstance(item, Mapping):
                    raise DocumentIntelligenceError("validation_error", "Every zone must be an object.")
                zone_name = _required_text(item.get("zone_name"), "zone_name", 100)
                extraction_key = _required_text(item.get("extraction_key"), "extraction_key", 100)
                if zone_name.lower() in names or extraction_key.lower() in keys:
                    raise DocumentIntelligenceError("duplicate_zone", "Zone names and extraction keys must be unique.")
                names.add(zone_name.lower())
                keys.add(extraction_key.lower())
                try:
                    x, y = Decimal(str(item.get("x"))), Decimal(str(item.get("y")))
                    width, height = Decimal(str(item.get("width"))), Decimal(str(item.get("height")))
                    page_number = int(item.get("page_number", 1))
                except (ValueError, TypeError) as exc:
                    raise DocumentIntelligenceError("validation_error", "Zone coordinates are invalid.") from exc
                if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1 or page_number <= 0:
                    raise DocumentIntelligenceError(
                        "zone_bounds", "Zone coordinates must be normalized within the page."
                    )
                candidate = {
                    "zone_name": zone_name,
                    "extraction_key": extraction_key,
                    "zone_type": str(item.get("zone_type", "")),
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "page_number": page_number,
                    "expected_data_type": str(item.get("expected_data_type", "string")),
                    "is_required": bool(item.get("is_required", False)),
                }
                for other in normalized:
                    if other["page_number"] != page_number:
                        continue
                    overlaps_horizontally = x < other["x"] + other["width"] and x + width > other["x"]
                    overlaps_vertically = y < other["y"] + other["height"] and y + height > other["y"]
                    if overlaps_horizontally and overlaps_vertically:  # type: ignore[operator]
                        raise DocumentIntelligenceError("zone_overlap", "Zones on the same page cannot overlap.")
                normalized.append(candidate)
            return normalized

    def match_template(
        self,
        tenant_id: UUID,
        document_id: UUID,
        version_id: UUID,
        template_id: UUID | None = None,
    ) -> TemplateMatchResult:
        tenant_id = self._tenant(tenant_id)
        document_id = _uuid(document_id, "document_id")
        version_id = _uuid(version_id, "version_id")
        self._document(tenant_id, document_id, version_id)
        templates_query = ExtractionTemplate.objects.for_tenant(tenant_id).filter(
            status=TemplateStatus.ACTIVE, is_deleted=False
        )
        if template_id is not None:
            templates_query = templates_query.filter(pk=_uuid(template_id, "template_id"))
        templates = list(templates_query)
        if not templates:
            raise DocumentIntelligenceError("template_unavailable", "No active extraction template is available.")
        best: TemplateMatchResult | None = None
        for engine in sorted({template.engine for template in templates}):
            candidates = [template for template in templates if template.engine == engine]
            try:
                adapter = self.providers.resolve_ocr(tenant_id, engine)

                def match_with_fresh_stream() -> TemplateMatchResult:
                    content = self.dms.open_content(tenant_id, document_id, version_id)
                    with closing(content):
                        return adapter.match(content, candidates, f"match:{document_id}:{version_id}:{engine}")

                result = self._execute_dependency(tenant_id, f"ocr.{engine}.match", match_with_fresh_stream)
            except ProviderUnavailable:
                continue
            if not isinstance(result, TemplateMatchResult):
                raise InvalidProviderOutput("template matcher omitted validated evidence")
            if result.template_id is not None and result.template_id not in {template.id for template in candidates}:
                raise InvalidProviderOutput("template matcher returned a foreign template")
            if best is None or result.confidence > best.confidence:
                best = result
        if best is None:
            raise DocumentIntelligenceError(
                "provider_unavailable", "No template matcher is available.", status_code=503
            )
        if best.template_id is not None:
            template = next(item for item in templates if item.id == best.template_id)
            if best.confidence < template.match_threshold:
                best = TemplateMatchResult(None, Decimal("0.0000"), best.processing_time_ms)
            else:
                publish_domain_event(
                    tenant_id,
                    "document_intelligence.template.matched",
                    "extraction_template",
                    template.id,
                    actor_id=None,
                    payload={
                        "status": template.status,
                        "engine": template.engine,
                        "template_id": str(template.id),
                        "matched": True,
                        "duration_ms": best.processing_time_ms,
                    },
                )
        return best

    def extract_by_template(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        document_id: UUID,
        version_id: UUID,
        template_id: UUID,
        idempotency_key: str,
    ) -> AcceptedWork:
        return DocumentExtractionService(
            dms_gateway=self.dms,
            provider_resolver=self.providers,
            entitlement_service=self.entitlements,
            quota_service=self.quotas,
        ).extract_by_template(tenant_id, actor_id, document_id, version_id, template_id, idempotency_key)

    def get_template(self, tenant_id: UUID, template_id: UUID) -> ExtractionTemplate:
        value = (
            ExtractionTemplate.objects.for_tenant(self._tenant(tenant_id))
            .prefetch_related("zones")
            .filter(pk=template_id, is_deleted=False)
            .first()
        )
        if value is None:
            raise DocumentIntelligenceError("resource_not_found", "Template not found.", status_code=404)
        return value

    def list_templates(self, tenant_id: UUID, filters: object) -> QuerySet[ExtractionTemplate]:
        queryset = ExtractionTemplate.objects.for_tenant(self._tenant(tenant_id)).filter(is_deleted=False)
        return filters.apply(queryset) if hasattr(filters, "apply") else queryset

    def create_zone(
        self, tenant_id: UUID, template_id: UUID, actor_id: UUID, data: Mapping[str, object]
    ) -> ExtractionTemplateZone:
        template = self.get_template(tenant_id, template_id)
        zones = list(
            ExtractionTemplateZone.objects.for_tenant(self._tenant(tenant_id))
            .filter(template=template, is_deleted=False)
            .values(
                "zone_name",
                "extraction_key",
                "zone_type",
                "x",
                "y",
                "width",
                "height",
                "page_number",
                "expected_data_type",
                "is_required",
            )
        )
        zones.append(dict(data))
        result = self.replace_zones(tenant_id, template.id, actor_id, zones)
        return result[-1]

    def update_zone(
        self, tenant_id: UUID, zone_id: UUID, actor_id: UUID, data: Mapping[str, object]
    ) -> ExtractionTemplateZone:
        tenant_id = self._tenant(tenant_id)
        zone = ExtractionTemplateZone.objects.for_tenant(tenant_id).filter(pk=zone_id, is_deleted=False).first()
        if zone is None:
            raise DocumentIntelligenceError("resource_not_found", "Template zone not found.", status_code=404)
        zones = list(
            ExtractionTemplateZone.objects.for_tenant(tenant_id)
            .filter(template_id=zone.template_id, is_deleted=False)
            .values(
                "id",
                "zone_name",
                "extraction_key",
                "zone_type",
                "x",
                "y",
                "width",
                "height",
                "page_number",
                "expected_data_type",
                "is_required",
            )
        )
        payload: list[dict[str, object]] = []
        for current in zones:
            current_id = current.pop("id")
            if current_id == zone.id:
                current.update(data)
            payload.append(current)
        updated = self.replace_zones(tenant_id, zone.template_id, actor_id, payload)
        return next(item for item in updated if item.zone_name == str(data.get("zone_name", zone.zone_name)))

    def archive_zone(self, tenant_id: UUID, zone_id: UUID, actor_id: UUID) -> None:
        tenant_id = self._tenant(tenant_id)
        del actor_id
        with transaction.atomic():
            zone = (
                ExtractionTemplateZone.objects.for_tenant(tenant_id)
                .select_for_update()
                .filter(pk=zone_id, is_deleted=False)
                .first()
            )
            if zone is None:
                raise DocumentIntelligenceError("resource_not_found", "Template zone not found.", status_code=404)
            template = ExtractionTemplate.objects.for_tenant(tenant_id).select_for_update().get(pk=zone.template_id)
            if template.status not in {TemplateStatus.DRAFT, TemplateStatus.INACTIVE}:
                raise DocumentIntelligenceError(
                    "immutable_template", "Template zone cannot be archived.", status_code=409
                )
            zone.is_deleted = True
            zone.deleted_at = timezone.now()
            zone.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


_CONFIGURATION_ENVIRONMENTS = frozenset({"development", "self-hosted", "saas"})
_PLATFORM_MIME_TYPES = frozenset({"application/pdf", "image/png", "image/jpeg", "image/tiff", "image/bmp"})
_PLATFORM_EXTRACTION_TYPES = frozenset({"text", "structured", "table", "zone"})
_PLATFORM_CLASSIFIER_PROVIDERS = frozenset({"local_naive_bayes"})

_DEFAULT_CONFIGURATION: dict[str, Any] = {
    "limits": {
        "max_document_bytes": 52_428_800,
        "max_pages": 10_000,
        "max_text_characters": 20_000_000,
        "max_structured_bytes": 20_000_000,
        "max_categories": 1_000,
        "category_schema": "lowercase_slug_v1",
        "category_slug_max_length": 80,
        "content_handle_max_length": 1_000,
        "page_dimension_max": 1_000_000,
        "search_max_length": 100,
    },
    "providers": {
        "allowed_mime_types": sorted(_PLATFORM_MIME_TYPES),
        "allowed_extraction_types": sorted(_PLATFORM_EXTRACTION_TYPES),
        "allowed_ocr_engines": ["tesseract"],
        "default_ocr_engine": "tesseract",
        "default_classifier_provider": "local_naive_bayes",
        "artifact_root_environment_variable": "DOCUMENT_INTELLIGENCE_ARTIFACT_ROOT",
    },
    "extraction": {"max_active": 5, "stale_job_hours": 24},
    "classifier": {
        "feature_buckets": 1_024,
        "provider_max_categories": 100,
        "minimum_training_documents": 50,
        "minimum_documents_per_category": 5,
        "activation_accuracy_threshold": 0.8,
        "secondary_confidence_threshold": 0.3,
    },
    "review": {"low_confidence_threshold": 0.5, "note_max_length": 4_000},
    "templates": {"default_engine": "tesseract", "default_match_threshold": 0.7},
    "resilience": {
        "stream_chunk_size_bytes": 1_048_576,
        "timeout_seconds": 300.0,
        "max_attempts": 3,
        "initial_backoff_seconds": 0.25,
        "max_backoff_seconds": 4.0,
        "jitter_ratio": 0.2,
        "circuit_failure_threshold": 5,
        "circuit_recovery_seconds": 30.0,
    },
    "health": {"stale_after_seconds": 30},
    "observability": {
        "provider_duration_buckets_seconds": [0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
        "queue_delay_buckets_seconds": [0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 300.0],
    },
    "editor": {
        "new_zone": {
            "x": 0.1,
            "y": 0.1,
            "width": 0.3,
            "height": 0.1,
            "page_number": 1,
            "zone_type": "text",
            "expected_data_type": "string",
            "is_required": False,
        },
        "coordinate_snap": 0.01,
        "coordinate_precision": 4,
        "undo_history_limit": 20,
        "zoom_min_percent": 70,
        "zoom_max_percent": 150,
        "zoom_step_percent": 10,
    },
    "ui": {
        "page_size": 25,
        "template_zone_page_size": 100,
        "poll_interval_ms": 5_000,
        "stale_after_ms": 15_000,
        "confidence_filter_presets": [0.5, 0.8, 0.95],
        "positive_statuses": ["completed", "active", "confirmed"],
        "warning_statuses": ["needs_review", "pending", "timed_out"],
        "navigation_order": {
            "extractions": 300,
            "classifications": 310,
            "training": 320,
            "templates": 330,
            "health": 340,
            "configuration": 350,
        },
    },
    "feature_flags": {
        "auto_classification_enabled": False,
        "rollout_percentage": 0,
        "allowed_roles": [],
        "allowed_cohorts": [],
    },
    "workflows": {
        "extraction": [
            {"command": "start", "from": "queued", "to": "processing"},
            {"command": "cancel", "from": "queued", "to": "cancelled"},
            {"command": "complete", "from": "processing", "to": "completed"},
            {"command": "require_review", "from": "processing", "to": "needs_review"},
            {"command": "fail", "from": "processing", "to": "failed"},
            {"command": "time_out", "from": "processing", "to": "timed_out"},
            {"command": "cancel", "from": "processing", "to": "cancelled"},
            {"command": "retry", "from": "failed", "to": "queued"},
            {"command": "retry", "from": "timed_out", "to": "queued"},
        ],
        "classification": [
            {"command": "start", "from": "queued", "to": "processing"},
            {"command": "cancel", "from": "queued", "to": "cancelled"},
            {"command": "complete", "from": "processing", "to": "completed"},
            {"command": "fail", "from": "processing", "to": "failed"},
            {"command": "time_out", "from": "processing", "to": "timed_out"},
            {"command": "cancel", "from": "processing", "to": "cancelled"},
            {"command": "retry", "from": "failed", "to": "queued"},
            {"command": "retry", "from": "timed_out", "to": "queued"},
        ],
        "training": [
            {"command": "start", "from": "queued", "to": "training"},
            {"command": "cancel", "from": "queued", "to": "cancelled"},
            {"command": "complete", "from": "training", "to": "completed"},
            {"command": "fail", "from": "training", "to": "failed"},
            {"command": "time_out", "from": "training", "to": "timed_out"},
            {"command": "cancel", "from": "training", "to": "cancelled"},
            {"command": "retry", "from": "failed", "to": "queued"},
            {"command": "retry", "from": "timed_out", "to": "queued"},
        ],
        "model_version": [
            {"command": "activate", "from": "candidate", "to": "active"},
            {"command": "fail", "from": "candidate", "to": "failed"},
            {"command": "retire", "from": "active", "to": "retired"},
            {"command": "rollback", "from": "retired", "to": "active"},
        ],
        "template": [
            {"command": "activate", "from": "draft", "to": "active"},
            {"command": "deactivate", "from": "active", "to": "inactive"},
            {"command": "retire", "from": "active", "to": "retired"},
            {"command": "activate", "from": "inactive", "to": "active"},
            {"command": "retire", "from": "inactive", "to": "retired"},
            {"command": "retire", "from": "draft", "to": "retired"},
        ],
    },
}

_NUMERIC_CONFIGURATION_BOUNDS: dict[str, tuple[float, float, bool]] = {
    "limits.max_document_bytes": (1_048_576, 1_073_741_824, True),
    "limits.max_pages": (1, 100_000, True),
    "limits.max_text_characters": (1_000, 100_000_000, True),
    "limits.max_structured_bytes": (1_000, 100_000_000, True),
    "limits.max_categories": (1, 10_000, True),
    "limits.category_slug_max_length": (1, 128, True),
    "limits.content_handle_max_length": (64, 4_096, True),
    "limits.page_dimension_max": (1, 2_000_000, True),
    "limits.search_max_length": (1, 1_000, True),
    "extraction.max_active": (1, 100, True),
    "extraction.stale_job_hours": (1, 720, True),
    "classifier.feature_buckets": (128, 65_536, True),
    "classifier.provider_max_categories": (1, 1_000, True),
    "classifier.minimum_training_documents": (10, 100_000, True),
    "classifier.minimum_documents_per_category": (2, 10_000, True),
    "classifier.activation_accuracy_threshold": (0.5, 1.0, False),
    "classifier.secondary_confidence_threshold": (0.0, 1.0, False),
    "review.low_confidence_threshold": (0.0, 1.0, False),
    "review.note_max_length": (1, 20_000, True),
    "templates.default_match_threshold": (0.0, 1.0, False),
    "resilience.stream_chunk_size_bytes": (4_096, 16_777_216, True),
    "resilience.timeout_seconds": (0.1, 3_600.0, False),
    "resilience.max_attempts": (1, 10, True),
    "resilience.initial_backoff_seconds": (0.0, 60.0, False),
    "resilience.max_backoff_seconds": (0.0, 60.0, False),
    "resilience.jitter_ratio": (0.0, 1.0, False),
    "resilience.circuit_failure_threshold": (1, 100, True),
    "resilience.circuit_recovery_seconds": (0.1, 3_600.0, False),
    "health.stale_after_seconds": (1, 3_600, True),
    "editor.new_zone.x": (0.0, 1.0, False),
    "editor.new_zone.y": (0.0, 1.0, False),
    "editor.new_zone.width": (0.001, 1.0, False),
    "editor.new_zone.height": (0.001, 1.0, False),
    "editor.new_zone.page_number": (1, 100_000, True),
    "editor.coordinate_snap": (0.0001, 0.25, False),
    "editor.coordinate_precision": (1, 6, True),
    "editor.undo_history_limit": (1, 200, True),
    "editor.zoom_min_percent": (10, 100, True),
    "editor.zoom_max_percent": (100, 500, True),
    "editor.zoom_step_percent": (1, 100, True),
    "ui.page_size": (1, 100, True),
    "ui.template_zone_page_size": (1, 500, True),
    "ui.poll_interval_ms": (1_000, 300_000, True),
    "ui.stale_after_ms": (1_000, 3_600_000, True),
    "feature_flags.rollout_percentage": (0, 100, True),
}


def default_configuration_document() -> dict[str, Any]:
    """Return an isolated API default; callers can never mutate the schema template."""
    return deepcopy(_DEFAULT_CONFIGURATION)


def _configuration_value(document: Mapping[str, Any], path: str) -> Any:
    value: Any = document
    for component in path.split("."):
        if not isinstance(value, Mapping) or component not in value:
            raise DocumentIntelligenceError("invalid_configuration", f"Missing configuration field: {path}.")
        value = value[component]
    return value


def _validate_configuration_shape(value: object, template: object, path: str = "") -> None:
    if isinstance(template, dict):
        if not isinstance(value, Mapping):
            raise DocumentIntelligenceError("invalid_configuration", f"{path or 'document'} must be an object.")
        expected = set(template)
        supplied = set(value)
        if expected != supplied:
            missing = sorted(expected - supplied)
            unknown = sorted(supplied - expected)
            raise DocumentIntelligenceError(
                "invalid_configuration",
                f"{path or 'document'} has invalid fields.",
                detail={"missing": missing, "unknown": unknown},
            )
        for key, child_template in template.items():
            child_path = f"{path}.{key}" if path else key
            _validate_configuration_shape(value[key], child_template, child_path)
        return
    if isinstance(template, list):
        if not isinstance(value, list):
            raise DocumentIntelligenceError("invalid_configuration", f"{path} must be an array.")
        return
    expected_type = type(template)
    if expected_type is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DocumentIntelligenceError("invalid_configuration", f"{path} must be numeric.")
        return
    if not isinstance(value, expected_type):
        raise DocumentIntelligenceError("invalid_configuration", f"{path} must be {expected_type.__name__}.")


def _validate_string_array(value: object, path: str, *, maximum_items: int, maximum_length: int) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise DocumentIntelligenceError("invalid_configuration", f"{path} exceeds its safe item limit.")
    if any(not isinstance(item, str) or not item or len(item) > maximum_length for item in value):
        raise DocumentIntelligenceError("invalid_configuration", f"{path} contains an invalid value.")
    if len(value) != len(set(value)):
        raise DocumentIntelligenceError("invalid_configuration", f"{path} contains duplicate values.")
    return value


def validate_configuration_document(document: object, *, environment: str) -> dict[str, Any]:
    """Validate and normalize the complete allow-listed configuration server-side."""
    if environment not in _CONFIGURATION_ENVIRONMENTS:
        raise DocumentIntelligenceError("invalid_configuration", "environment is not supported.")
    if not isinstance(document, Mapping):
        raise DocumentIntelligenceError("invalid_configuration", "Configuration document must be an object.")
    normalized = deepcopy(dict(document))
    _validate_configuration_shape(normalized, _DEFAULT_CONFIGURATION)

    for path, (minimum, maximum, integer_only) in _NUMERIC_CONFIGURATION_BOUNDS.items():
        value = _configuration_value(normalized, path)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise DocumentIntelligenceError("invalid_configuration", f"{path} must be a finite number.")
        if integer_only and not isinstance(value, int):
            raise DocumentIntelligenceError("invalid_configuration", f"{path} must be an integer.")
        if value < minimum or value > maximum:
            raise DocumentIntelligenceError("invalid_configuration", f"{path} must be between {minimum} and {maximum}.")

    if normalized["limits"]["category_schema"] != "lowercase_slug_v1":
        raise DocumentIntelligenceError("invalid_configuration", "limits.category_schema is not supported.")
    mime_types = set(
        _validate_string_array(
            normalized["providers"]["allowed_mime_types"],
            "providers.allowed_mime_types",
            maximum_items=len(_PLATFORM_MIME_TYPES),
            maximum_length=100,
        )
    )
    if not mime_types or not mime_types <= _PLATFORM_MIME_TYPES:
        raise DocumentIntelligenceError("invalid_configuration", "An unsupported MIME type was configured.")
    extraction_types = set(
        _validate_string_array(
            normalized["providers"]["allowed_extraction_types"],
            "providers.allowed_extraction_types",
            maximum_items=len(_PLATFORM_EXTRACTION_TYPES),
            maximum_length=30,
        )
    )
    if not extraction_types or not extraction_types <= _PLATFORM_EXTRACTION_TYPES:
        raise DocumentIntelligenceError("invalid_configuration", "An unsupported extraction type was configured.")
    engines = _validate_string_array(
        normalized["providers"]["allowed_ocr_engines"],
        "providers.allowed_ocr_engines",
        maximum_items=20,
        maximum_length=50,
    )
    if normalized["providers"]["default_ocr_engine"] not in engines:
        raise DocumentIntelligenceError("invalid_configuration", "providers.default_ocr_engine must be allow-listed.")
    if normalized["templates"]["default_engine"] not in engines:
        raise DocumentIntelligenceError("invalid_configuration", "templates.default_engine must be allow-listed.")
    if normalized["providers"]["default_classifier_provider"] not in _PLATFORM_CLASSIFIER_PROVIDERS:
        raise DocumentIntelligenceError("invalid_configuration", "Classifier provider is not supported.")
    env_ref = normalized["providers"]["artifact_root_environment_variable"]
    if not isinstance(env_ref, str) or re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", env_ref) is None:
        raise DocumentIntelligenceError("invalid_configuration", "Artifact root environment reference is invalid.")

    if (
        normalized["classifier"]["minimum_documents_per_category"]
        > normalized["classifier"]["minimum_training_documents"]
    ):
        raise DocumentIntelligenceError(
            "invalid_configuration", "Per-category training minimum exceeds the total minimum."
        )
    if normalized["classifier"]["provider_max_categories"] > normalized["limits"]["max_categories"]:
        raise DocumentIntelligenceError(
            "invalid_configuration", "Provider category capacity exceeds the tenant category limit."
        )
    if normalized["resilience"]["initial_backoff_seconds"] > normalized["resilience"]["max_backoff_seconds"]:
        raise DocumentIntelligenceError("invalid_configuration", "Retry backoff bounds are reversed.")
    if normalized["editor"]["zoom_min_percent"] >= normalized["editor"]["zoom_max_percent"]:
        raise DocumentIntelligenceError("invalid_configuration", "Editor zoom bounds are invalid.")
    zone = normalized["editor"]["new_zone"]
    if zone["x"] + zone["width"] > 1 or zone["y"] + zone["height"] > 1:
        raise DocumentIntelligenceError("invalid_configuration", "Default editor zone exceeds the page bounds.")
    if zone["zone_type"] not in {"text", "table", "checkbox", "barcode"}:
        raise DocumentIntelligenceError("invalid_configuration", "Default editor zone type is invalid.")
    if zone["expected_data_type"] not in {"string", "integer", "decimal", "date", "boolean", "array"}:
        raise DocumentIntelligenceError("invalid_configuration", "Default editor data type is invalid.")

    for path in ("observability.provider_duration_buckets_seconds", "observability.queue_delay_buckets_seconds"):
        buckets = _configuration_value(normalized, path)
        if (
            not isinstance(buckets, list)
            or not 1 <= len(buckets) <= 30
            or any(
                isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or item <= 0
                for item in buckets
            )
            or buckets != sorted(set(buckets))
        ):
            raise DocumentIntelligenceError("invalid_configuration", f"{path} must be unique and ascending.")
    confidence_presets = normalized["ui"]["confidence_filter_presets"]
    if (
        not isinstance(confidence_presets, list)
        or not 1 <= len(confidence_presets) <= 10
        or any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(item)
            or item < 0
            or item > 1
            for item in confidence_presets
        )
        or confidence_presets != sorted(set(confidence_presets))
    ):
        raise DocumentIntelligenceError("invalid_configuration", "Confidence filter presets are invalid.")
    for key in ("positive_statuses", "warning_statuses"):
        _validate_string_array(normalized["ui"][key], f"ui.{key}", maximum_items=30, maximum_length=30)
    if set(normalized["ui"]["positive_statuses"]) & set(normalized["ui"]["warning_statuses"]):
        raise DocumentIntelligenceError("invalid_configuration", "Semantic status groups cannot overlap.")
    _validate_string_array(
        normalized["feature_flags"]["allowed_roles"],
        "feature_flags.allowed_roles",
        maximum_items=100,
        maximum_length=100,
    )
    _validate_string_array(
        normalized["feature_flags"]["allowed_cohorts"],
        "feature_flags.allowed_cohorts",
        maximum_items=100,
        maximum_length=100,
    )
    if (
        not normalized["feature_flags"]["auto_classification_enabled"]
        and normalized["feature_flags"]["rollout_percentage"] != 0
    ):
        raise DocumentIntelligenceError("invalid_configuration", "Disabled auto-classification must have zero rollout.")
    for workflow, transitions in normalized["workflows"].items():
        if not isinstance(transitions, list) or not transitions or len(transitions) > 50:
            raise DocumentIntelligenceError("invalid_configuration", f"workflows.{workflow} is invalid.")
        for transition_config in transitions:
            if not isinstance(transition_config, Mapping) or set(transition_config) != {"command", "from", "to"}:
                raise DocumentIntelligenceError(
                    "invalid_configuration", f"workflows.{workflow} contains an invalid transition."
                )
            if any(
                not isinstance(transition_config[field], str)
                or not transition_config[field]
                or len(transition_config[field]) > 30
                for field in ("command", "from", "to")
            ):
                raise DocumentIntelligenceError(
                    "invalid_configuration", f"workflows.{workflow} contains an invalid transition."
                )
    return normalized


def _deep_merge(base: Mapping[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(base))
    for key, value in changes.items():
        if key in result and isinstance(result[key], Mapping) and isinstance(value, Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _configuration_diff(before: object, after: object, path: str = "") -> list[dict[str, Any]]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        changes: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            child_path = f"{path}.{key}" if path else key
            changes.extend(_configuration_diff(before.get(key), after.get(key), child_path))
        return changes
    if before != after:
        return [{"path": path, "before": deepcopy(before), "after": deepcopy(after)}]
    return []


class ConfigurationService:
    """Govern tenant configuration as an atomic, versioned, auditable document."""

    @staticmethod
    def resolve_environment(environment: str | None = None) -> str:
        resolved = environment or str(getattr(settings, "SARAISE_MODE", ""))
        if resolved not in _CONFIGURATION_ENVIRONMENTS:
            raise DocumentIntelligenceError(
                "configuration_unavailable",
                "The runtime configuration environment is unavailable.",
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return resolved

    @staticmethod
    def _correlation(value: object | None) -> str:
        correlation_id = str(value or get_correlation_id() or uuid.uuid4()).strip()
        if not correlation_id or len(correlation_id) > 64:
            raise DocumentIntelligenceError("invalid_configuration", "correlation_id is invalid.")
        return correlation_id

    @staticmethod
    def _reason(value: object) -> str:
        return _required_text(value, "change_reason", 500)

    def get_record(self, tenant_id: UUID | str, environment: str | None = None) -> Any:
        from .models import DocumentIntelligenceConfiguration

        tenant = _uuid(tenant_id, "tenant_id")
        resolved = self.resolve_environment(environment)
        record = DocumentIntelligenceConfiguration.objects.for_tenant(tenant).filter(environment=resolved).first()
        if record is None:
            # First access atomically materializes the governed default as real
            # tenant data.  This is not an in-memory fallback: validation,
            # version history, immutable audit evidence, and tenant isolation
            # are identical to an operator-created configuration.
            try:
                self.save(
                    tenant,
                    uuid.UUID(int=0),
                    default_configuration_document(),
                    environment=resolved,
                    change_reason="System initialized validated tenant defaults",
                    correlation_id=get_correlation_id() or uuid.uuid4(),
                    operation="initialize",
                )
            except DocumentIntelligenceError as exc:
                if exc.error_code != "configuration_conflict":
                    raise
            record = DocumentIntelligenceConfiguration.objects.for_tenant(tenant).filter(environment=resolved).first()
            if record is None:
                raise DocumentIntelligenceError(
                    "configuration_unavailable",
                    "Tenant document-intelligence configuration could not be initialized.",
                    status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        try:
            validate_configuration_document(record.document, environment=resolved)
        except DocumentIntelligenceError as exc:
            raise DocumentIntelligenceError(
                "configuration_unavailable",
                "Tenant document-intelligence configuration is invalid.",
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc
        return record

    def get_effective(self, tenant_id: UUID | str, environment: str | None = None) -> dict[str, Any]:
        return deepcopy(self.get_record(tenant_id, environment).document)

    def get_value(self, tenant_id: UUID | str, dotted_path: str, environment: str | None = None) -> Any:
        return deepcopy(_configuration_value(self.get_effective(tenant_id, environment), dotted_path))

    def save(
        self,
        tenant_id: UUID | str,
        actor_id: UUID | str,
        document: Mapping[str, Any],
        *,
        environment: str | None = None,
        change_reason: object,
        correlation_id: object | None = None,
        partial: bool = False,
        operation: str = "update",
    ) -> Any:
        from .models import ConfigurationAudit, ConfigurationVersion, DocumentIntelligenceConfiguration

        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        resolved = self.resolve_environment(environment)
        reason = self._reason(change_reason)
        correlation = self._correlation(correlation_id)
        if operation not in ConfigurationAudit.Operation.values:
            raise DocumentIntelligenceError("invalid_configuration", "Configuration operation is invalid.")
        with transaction.atomic():
            current = (
                DocumentIntelligenceConfiguration.objects.for_tenant(tenant)
                .select_for_update()
                .filter(environment=resolved)
                .first()
            )
            previous = deepcopy(current.document) if current is not None else None
            candidate = (
                _deep_merge(previous or default_configuration_document(), document) if partial else dict(document)
            )
            normalized = validate_configuration_document(candidate, environment=resolved)
            if current is not None and previous == normalized:
                return current
            version = 1 if current is None else current.version + 1
            effective_operation = ConfigurationAudit.Operation.INITIALIZE if current is None else operation
            if current is None:
                try:
                    current = DocumentIntelligenceConfiguration.objects.create(
                        tenant_id=tenant,
                        environment=resolved,
                        version=version,
                        document=normalized,
                        created_by=actor,
                        updated_by=actor,
                    )
                except IntegrityError as exc:
                    raise DocumentIntelligenceError(
                        "configuration_conflict",
                        "Configuration was initialized concurrently; reload before retrying.",
                        status_code=http_status.HTTP_409_CONFLICT,
                    ) from exc
            else:
                current.version = version
                current.document = normalized
                current.updated_by = actor
                current.save(update_fields=["version", "document", "updated_by", "updated_at"])
            ConfigurationVersion.objects.create(
                tenant_id=tenant,
                environment=resolved,
                version=version,
                document=normalized,
                created_by=actor,
                correlation_id=correlation,
                change_reason=reason,
            )
            ConfigurationAudit.objects.create(
                tenant_id=tenant,
                environment=resolved,
                version=version,
                operation=effective_operation,
                previous_document=previous,
                new_document=normalized,
                created_by=actor,
                correlation_id=correlation,
                change_reason=reason,
            )
        return current

    def versions(self, tenant_id: UUID | str, environment: str | None = None) -> QuerySet[Any]:
        from .models import ConfigurationVersion

        tenant = _uuid(tenant_id, "tenant_id")
        resolved = self.resolve_environment(environment)
        return ConfigurationVersion.objects.for_tenant(tenant).filter(environment=resolved).order_by("-version")

    def audits(self, tenant_id: UUID | str, environment: str | None = None) -> QuerySet[Any]:
        from .models import ConfigurationAudit

        tenant = _uuid(tenant_id, "tenant_id")
        resolved = self.resolve_environment(environment)
        return ConfigurationAudit.objects.for_tenant(tenant).filter(environment=resolved).order_by("-version")

    def rollback(
        self,
        tenant_id: UUID | str,
        actor_id: UUID | str,
        version: int,
        *,
        environment: str | None = None,
        change_reason: object,
        correlation_id: object | None = None,
    ) -> Any:
        from .models import ConfigurationVersion

        tenant = _uuid(tenant_id, "tenant_id")
        resolved = self.resolve_environment(environment)
        target = ConfigurationVersion.objects.for_tenant(tenant).filter(environment=resolved, version=version).first()
        if target is None:
            raise DocumentIntelligenceError("resource_not_found", "Configuration version not found.", status_code=404)
        return self.save(
            tenant,
            actor_id,
            target.document,
            environment=resolved,
            change_reason=change_reason,
            correlation_id=correlation_id,
            operation="rollback",
        )

    def export_document(self, tenant_id: UUID | str, environment: str | None = None) -> dict[str, Any]:
        record = self.get_record(tenant_id, environment)
        return {
            "schema_version": 1,
            "module": "document_intelligence",
            "environment": record.environment,
            "version": record.version,
            "exported_at": timezone.now().isoformat(),
            "document": deepcopy(record.document),
        }

    def import_document(
        self,
        tenant_id: UUID | str,
        actor_id: UUID | str,
        payload: Mapping[str, Any],
        *,
        change_reason: object,
        correlation_id: object | None = None,
    ) -> Any:
        allowed = {"schema_version", "module", "environment", "version", "exported_at", "document"}
        if set(payload) - allowed:
            raise DocumentIntelligenceError("invalid_configuration", "Import document contains unknown fields.")
        if payload.get("schema_version") != 1 or payload.get("module") != "document_intelligence":
            raise DocumentIntelligenceError("invalid_configuration", "Import document contract is unsupported.")
        if not isinstance(payload.get("document"), Mapping):
            raise DocumentIntelligenceError("invalid_configuration", "Import document has no configuration object.")
        return self.save(
            tenant_id,
            actor_id,
            payload["document"],
            environment=str(payload.get("environment", "")),
            change_reason=change_reason,
            correlation_id=correlation_id,
            operation="import",
        )

    def simulate(
        self,
        tenant_id: UUID | str,
        document: Mapping[str, Any],
        *,
        environment: str | None = None,
        partial: bool = False,
    ) -> dict[str, Any]:
        resolved = self.resolve_environment(environment)
        try:
            current = self.get_effective(tenant_id, resolved)
        except DocumentIntelligenceError as exc:
            if exc.error_code != "configuration_unavailable":
                raise
            current = default_configuration_document()
        candidate = _deep_merge(current, document) if partial else dict(document)
        normalized = validate_configuration_document(candidate, environment=resolved)
        return {
            "valid": True,
            "normalized_document": normalized,
            "changes": _configuration_diff(current, normalized),
            "requires_restart": False,
        }


__all__ = [
    "AcceptedWork",
    "ConfigurationService",
    "DocumentClassificationService",
    "DocumentExtractionService",
    "DocumentIntelligenceError",
    "ProcessingFailure",
    "TemplateMatchingService",
    "default_configuration_document",
    "validate_configuration_document",
]
