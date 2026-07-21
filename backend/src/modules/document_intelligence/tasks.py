"""Durable command handlers and tenant-context worker entry points."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from uuid import UUID

from django.utils import timezone

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import register_handler
from src.core.tenancy import tenant_context_worker

from .models import (
    ClassificationStatus,
    DocumentClassification,
    DocumentExtraction,
    ExtractionStatus,
)
from .services import DocumentClassificationService, DocumentExtractionService


def _uuid_payload(payload: Mapping[str, object], key: str) -> UUID:
    try:
        return UUID(str(payload[key]))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"durable job payload requires UUID field {key!r}") from exc


@tenant_context_worker
def run_extraction_task(*, tenant_id: UUID, extraction_id: UUID, async_job_id: UUID) -> dict[str, str]:
    extraction = DocumentExtractionService().run_extraction(tenant_id, extraction_id, async_job_id)
    return {"extraction_id": str(extraction.id), "status": extraction.status}


@tenant_context_worker
def run_classification_task(*, tenant_id: UUID, classification_id: UUID, async_job_id: UUID) -> dict[str, str]:
    classification = DocumentClassificationService().run_classification(tenant_id, classification_id, async_job_id)
    return {"classification_id": str(classification.id), "status": classification.status}


@tenant_context_worker
def run_training_task(*, tenant_id: UUID, training_job_id: UUID, async_job_id: UUID) -> dict[str, str]:
    training = DocumentClassificationService().run_training(tenant_id, training_job_id, async_job_id)
    return {"training_job_id": str(training.id), "status": training.status}


@tenant_context_worker
def cancel_stale_jobs_task(*, tenant_id: UUID, cutoff: datetime | None = None) -> dict[str, int]:
    cutoff = cutoff or timezone.now() - timedelta(hours=24)
    actor_id = uuid.UUID(int=0)
    extraction_service = DocumentExtractionService()
    classification_service = DocumentClassificationService()
    extraction_ids = list(
        DocumentExtraction.objects.for_tenant(tenant_id)
        .filter(status__in=[ExtractionStatus.QUEUED, ExtractionStatus.PROCESSING], updated_at__lt=cutoff)
        .values_list("id", flat=True)
    )
    classification_ids = list(
        DocumentClassification.objects.for_tenant(tenant_id)
        .filter(status__in=[ClassificationStatus.QUEUED, ClassificationStatus.PROCESSING], updated_at__lt=cutoff)
        .values_list("id", flat=True)
    )
    cancelled_extractions = 0
    for identifier in extraction_ids:
        try:
            extraction_service.cancel_extraction(tenant_id, identifier, actor_id)
            cancelled_extractions += 1
        except Exception:
            continue
    cancelled_classifications = 0
    for identifier in classification_ids:
        try:
            classification_service.cancel_classification(tenant_id, identifier, actor_id)
            cancelled_classifications += 1
        except Exception:
            continue
    cancelled_training = classification_service.cancel_stale_training_jobs(tenant_id, cutoff)
    return {
        "extractions": cancelled_extractions,
        "classifications": cancelled_classifications,
        "training_jobs": cancelled_training,
    }


@tenant_context_worker
def enforce_retention_task(*, tenant_id: UUID, cutoff: datetime) -> dict[str, int]:
    """Soft-archive terminal evidence older than a policy-supplied cutoff."""
    if timezone.is_naive(cutoff):
        raise ValueError("retention cutoff must be timezone-aware")
    actor_id = uuid.UUID(int=0)
    extraction_service = DocumentExtractionService()
    classification_service = DocumentClassificationService()
    extraction_ids = list(
        DocumentExtraction.objects.for_tenant(tenant_id)
        .filter(
            status__in=[
                ExtractionStatus.COMPLETED,
                ExtractionStatus.NEEDS_REVIEW,
                ExtractionStatus.FAILED,
                ExtractionStatus.CANCELLED,
                ExtractionStatus.TIMED_OUT,
            ],
            is_deleted=False,
            completed_at__lt=cutoff,
        )
        .values_list("id", flat=True)
    )
    classification_ids = list(
        DocumentClassification.objects.for_tenant(tenant_id)
        .filter(
            status__in=[
                ClassificationStatus.COMPLETED,
                ClassificationStatus.FAILED,
                ClassificationStatus.CANCELLED,
                ClassificationStatus.TIMED_OUT,
            ],
            is_deleted=False,
            completed_at__lt=cutoff,
        )
        .values_list("id", flat=True)
    )
    for identifier in extraction_ids:
        extraction_service.archive_extraction(tenant_id, identifier, actor_id)
    for identifier in classification_ids:
        classification_service.archive_classification(tenant_id, identifier, actor_id)
    return {"extractions": len(extraction_ids), "classifications": len(classification_ids)}


@register_handler("document_intelligence.extract")
def _extract_handler(job: AsyncJob) -> dict[str, str]:
    return run_extraction_task(
        tenant_id=job.tenant_id,
        extraction_id=_uuid_payload(job.payload, "extraction_id"),
        async_job_id=job.id,
    )


@register_handler("document_intelligence.classify")
def _classification_handler(job: AsyncJob) -> dict[str, str]:
    return run_classification_task(
        tenant_id=job.tenant_id,
        classification_id=_uuid_payload(job.payload, "classification_id"),
        async_job_id=job.id,
    )


@register_handler("document_intelligence.train_classifier")
def _training_handler(job: AsyncJob) -> dict[str, str]:
    return run_training_task(
        tenant_id=job.tenant_id,
        training_job_id=_uuid_payload(job.payload, "training_job_id"),
        async_job_id=job.id,
    )


@register_handler("document_intelligence.cancel_stale_jobs")
def _stale_handler(job: AsyncJob) -> dict[str, int]:
    cutoff_value = job.payload.get("cutoff")
    cutoff = datetime.fromisoformat(str(cutoff_value).replace("Z", "+00:00")) if cutoff_value else None
    return cancel_stale_jobs_task(tenant_id=job.tenant_id, cutoff=cutoff)


@register_handler("document_intelligence.enforce_retention")
def _retention_handler(job: AsyncJob) -> dict[str, int]:
    cutoff_value = job.payload.get("cutoff")
    if not cutoff_value:
        raise ValueError("retention command requires a policy cutoff")
    cutoff = datetime.fromisoformat(str(cutoff_value).replace("Z", "+00:00"))
    return enforce_retention_task(tenant_id=job.tenant_id, cutoff=cutoff)


_policy_lock = threading.RLock()
_auto_classification_policy: Callable[[UUID], bool] = lambda tenant_id: False


def configure_auto_classification_policy(policy: Callable[[UUID], bool]) -> None:
    """Install the tenant-scoped policy projection used by DMS consumers."""
    if not callable(policy):
        raise TypeError("auto-classification policy must be callable")
    global _auto_classification_policy
    with _policy_lock:
        _auto_classification_policy = policy


def consume_dms_document_uploaded(
    tenant_id: UUID,
    *,
    document_id: UUID,
    document_version_id: UUID,
    actor_id: UUID,
    event_id: UUID,
) -> object | None:
    """Idempotently request classification only when tenant policy enables it."""
    with _policy_lock:
        enabled = _auto_classification_policy(tenant_id)
    if enabled is not True:
        return None
    return DocumentClassificationService().request_classification(
        tenant_id,
        actor_id,
        document_id,
        document_version_id,
        f"dms.document.uploaded:{event_id}",
    )


def consume_dms_version_created(
    tenant_id: UUID,
    *,
    document_id: UUID,
    document_version_id: UUID,
    actor_id: UUID,
    event_id: UUID,
) -> object | None:
    return consume_dms_document_uploaded(
        tenant_id,
        document_id=document_id,
        document_version_id=document_version_id,
        actor_id=actor_id,
        event_id=event_id,
    )


__all__ = [
    "cancel_stale_jobs_task",
    "configure_auto_classification_policy",
    "consume_dms_document_uploaded",
    "consume_dms_version_created",
    "enforce_retention_task",
    "run_classification_task",
    "run_extraction_task",
    "run_training_task",
]
