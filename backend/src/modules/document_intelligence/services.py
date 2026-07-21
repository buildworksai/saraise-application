"""Tenant-safe application services for document intelligence.

All domain mutation lives here.  Controllers perform only primitive request
validation and serialization; workers call the same services under canonical
tenant context.  Document bytes remain streamed from DMS into configured
adapters and are never persisted or logged by this module.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

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

DEFAULT_MAX_ACTIVE_EXTRACTIONS = 5
LOW_CONFIDENCE_THRESHOLD = Decimal("0.5000")
ACTIVATION_ACCURACY_THRESHOLD = Decimal("0.8000")
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
    ) -> None:
        self.dms = dms_gateway or get_dms_gateway()
        self.providers = provider_resolver or get_provider_resolver()
        self.entitlements = entitlement_service or EntitlementService()
        self.quotas = quota_service or QuotaService()

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

    def _consume_quota(self, tenant_id: UUID, resource: str, cost: int) -> None:
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

    def _document(self, tenant_id: UUID, document_id: UUID, version_id: UUID) -> DocumentDescriptor:
        try:
            descriptor = self.dms.get_document(tenant_id, document_id, version_id)
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
        return descriptor

    @staticmethod
    def _provider_ready(adapter: object) -> None:
        try:
            health = adapter.health()  # type: ignore[attr-defined]
        except Exception as exc:
            raise DocumentIntelligenceError("provider_unavailable", "The provider is unavailable.") from exc
        if not getattr(health, "available", False):
            raise DocumentIntelligenceError("provider_unavailable", "The provider is unavailable.")


class DocumentExtractionService(_ServiceBase):
    """Request, execute, retry, cancel, archive, and query extractions."""

    def __init__(self, *, concurrency_policy: Callable[[UUID], int] | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.concurrency_policy = concurrency_policy or (lambda tenant_id: DEFAULT_MAX_ACTIVE_EXTRACTIONS)

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

        descriptor = self._document(tenant_id, document_id, version_id)
        try:
            adapter = self.providers.resolve_ocr(tenant_id, engine)
        except ProviderUnavailable as exc:
            raise DocumentIntelligenceError("provider_unavailable", "The OCR provider is not configured.") from exc
        self._provider_ready(adapter)
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
            self._consume_quota(tenant_id, "document_intelligence.pages_processed", descriptor.page_count)
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
            self._provider_ready(adapter)
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
            content = self.dms.open_content(tenant_id, extraction.document_id, extraction.document_version_id)
            with closing(content):
                result = adapter.extract(content, request, str(job_id))
            if not isinstance(result, OCRResult):
                raise InvalidProviderOutput("OCR adapter omitted validated result evidence")
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
            needs_review = result.confidence < LOW_CONFIDENCE_THRESHOLD
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
                "durable_job_missing", extra={"tenant_id": str(tenant_id), "extraction_id": str(extraction.id)}
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
        self.classifier_provider_policy = classifier_provider_policy or (lambda tenant_id: "local_naive_bayes")

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
        self._provider_ready(adapter)
        self._require_entitlement(tenant_id, "document_intelligence.classification:create")
        classification_id = uuid.uuid4()
        command = "document_intelligence.classify"
        with transaction.atomic():
            self._consume_quota(tenant_id, "document_intelligence.pages_processed", descriptor.page_count)
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
            self._provider_ready(adapter)
            self._document(tenant_id, classification.document_id, classification.document_version_id)
            content = self.dms.open_content(tenant_id, classification.document_id, classification.document_version_id)
            with closing(content):
                result = adapter.classify(content, classification.model_version, str(job_id))
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
                    if len(result.scores) > 1 and result.scores[1].confidence > Decimal("0.3000")
                    else None
                )
                locked.category = primary.category
                locked.confidence = primary.confidence
                locked.secondary_category = secondary.category if secondary else ""
                locked.secondary_confidence = secondary.confidence if secondary else None
                locked.needs_review = primary.confidence < LOW_CONFIDENCE_THRESHOLD
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
        if len(note) > 4000:
            raise DocumentIntelligenceError("validation_error", "review note exceeds 4000 characters.")
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
        if len(normalized) < 50:
            raise DocumentIntelligenceError("training_minimum", "At least 50 training documents are required.")
        if any(count < 5 for count in counts.values()):
            raise DocumentIntelligenceError("category_minimum", "Every category requires at least five documents.")
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
        self._provider_ready(adapter)
        self._require_entitlement(tenant_id, "document_intelligence.training:create")
        training_id = uuid.uuid4()
        command = "document_intelligence.train_classifier"
        with transaction.atomic():
            self._consume_quota(tenant_id, "document_intelligence.training_documents", len(normalized))
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
        try:
            adapter = self.providers.resolve_classifier(tenant_id, provider_key)
            self._provider_ready(adapter)
            result = adapter.train(training.training_items, training.requested_version, str(job_id))
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
        except Exception as exc:
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
            if target.accuracy <= ACTIVATION_ACCURACY_THRESHOLD:
                raise DocumentIntelligenceError("accuracy_threshold", "Model accuracy must be greater than 0.8000.")
            try:
                adapter = self.providers.resolve_classifier(tenant_id, target.provider_key)
                ready = adapter.validate_artifact(target.artifact_ref, target.artifact_checksum)
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
        with transaction.atomic():
            template = ExtractionTemplate.objects.create(
                tenant_id=tenant_id,
                created_by=actor_id,
                name=_required_text(data.get("name"), "name", 255),
                description=str(data.get("description", "")).strip(),
                document_category=str(data.get("document_category", "")).strip(),
                engine=_required_text(data.get("engine"), "engine", 50),
                match_threshold=Decimal(str(data.get("match_threshold", "0.7000"))),
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
            clone = ExtractionTemplate.objects.create(
                tenant_id=tenant_id,
                created_by=actor_id,
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
        self._provider_ready(adapter)
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
                content = self.dms.open_content(tenant_id, document_id, version_id)
                with closing(content):
                    result = adapter.match(content, candidates, f"match:{document_id}:{version_id}:{engine}")
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


__all__ = [
    "AcceptedWork",
    "DocumentClassificationService",
    "DocumentExtractionService",
    "DocumentIntelligenceError",
    "ProcessingFailure",
    "TemplateMatchingService",
]
