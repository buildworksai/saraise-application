"""Durable tenant-context task handlers for scheduled monitoring work."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue, register_handler
from src.core.observability import get_correlation_id
from src.core.tenancy import tenant_context_worker

from .models import LogEntry, MetricDataPoint, Span, Trace
from .services import AlertingService, SLAMonitoringService


class EvidenceArchivalUnavailable(RuntimeError):
    """Raised when immutable evidence has no governed archival destination."""


def _evidence_manifest(tenant_id: UUID, cutoff: datetime) -> tuple[dict[str, int], str]:
    querysets = {
        "metric_data_points": MetricDataPoint.objects.for_tenant(tenant_id).filter(timestamp__lt=cutoff),
        "logs": LogEntry.objects.for_tenant(tenant_id).filter(timestamp__lt=cutoff),
        "spans": Span.objects.for_tenant(tenant_id).filter(started_at__lt=cutoff),
        "traces": Trace.objects.for_tenant(tenant_id).filter(started_at__lt=cutoff),
    }
    digest = hashlib.sha256()
    counts: dict[str, int] = {}
    for evidence_type, queryset in querysets.items():
        ids = queryset.order_by("id").values_list("id", flat=True).iterator(chunk_size=2_000)
        count = 0
        for evidence_id in ids:
            digest.update(f"{evidence_type}:{evidence_id}\n".encode())
            count += 1
        counts[evidence_type] = count
    return counts, digest.hexdigest()


@tenant_context_worker
def evaluate_alerts_task(*, tenant_id: UUID) -> dict[str, object]:
    alerts = AlertingService().evaluate_alerts(tenant_id)
    return {"evaluated_at": timezone.now().isoformat(), "alert_ids": [str(alert.id) for alert in alerts]}


@tenant_context_worker
def snapshot_sla_task(*, tenant_id: UUID, sla_id: UUID) -> dict[str, str]:
    record = SLAMonitoringService().check_sla_compliance(tenant_id, sla_id)
    return {"sla_id": str(sla_id), "compliance_record_id": str(record.id), "status": record.status}


@tenant_context_worker
@transaction.atomic
def enforce_retention_task(*, tenant_id: UUID, cutoff: datetime | None = None) -> dict[str, object]:
    """Request archival of expired evidence without mutating source records."""

    from .services import ConfigurationService

    if cutoff is not None and timezone.is_naive(cutoff):
        raise ValueError("Retention cutoff must be timezone-aware.")
    document = ConfigurationService().effective_document(tenant_id, environment="default")
    evidence_policy = document["evidence"]
    if evidence_policy["archival_enabled"] is not True or not evidence_policy["archive_provider"]:
        raise EvidenceArchivalUnavailable("Governed evidence archival is not configured.")
    if cutoff is None:
        cutoff = timezone.now() - timedelta(days=evidence_policy["retention_days"])

    counts, evidence_digest = _evidence_manifest(tenant_id, cutoff)
    archive_request_id = uuid.uuid4()
    OutboxEvent.objects.create(
        id=archive_request_id,
        tenant_id=tenant_id,
        aggregate_type="performance_monitoring.evidence_archive",
        aggregate_id=archive_request_id,
        event_type="performance_monitoring.evidence.archive_requested.v1",
        payload={
            "archive_request_id": str(archive_request_id),
            "tenant_id": str(tenant_id),
            "cutoff": cutoff.isoformat(),
            "provider": evidence_policy["archive_provider"],
            "evidence_counts": counts,
            "evidence_sha256": evidence_digest,
            "correlation_id": get_correlation_id() or str(uuid.uuid4()),
        },
    )
    return {
        "archive_request_id": str(archive_request_id),
        "cutoff": cutoff.isoformat(),
        "evidence_counts": counts,
        "evidence_sha256": evidence_digest,
        "status": "archive_requested",
    }


def schedule_alert_evaluation(tenant_id: UUID, actor_id: UUID, idempotency_key: str) -> AsyncJob:
    return enqueue(tenant_id, actor_id, "performance_monitoring.evaluate_alerts", {}, idempotency_key)


def schedule_sla_snapshot(tenant_id: UUID, actor_id: UUID, sla_id: UUID, idempotency_key: str) -> AsyncJob:
    return enqueue(
        tenant_id,
        actor_id,
        "performance_monitoring.snapshot_sla",
        {"sla_id": str(sla_id)},
        idempotency_key,
    )


def schedule_retention(tenant_id: UUID, actor_id: UUID, cutoff: datetime, idempotency_key: str) -> AsyncJob:
    if timezone.is_naive(cutoff):
        raise ValueError("Retention cutoff must be timezone-aware.")
    return enqueue(
        tenant_id,
        actor_id,
        "performance_monitoring.enforce_retention",
        {"cutoff": cutoff.isoformat()},
        idempotency_key,
    )


@register_handler("performance_monitoring.evaluate_alerts")
def _alerts_handler(job: AsyncJob) -> dict[str, object]:
    return evaluate_alerts_task(tenant_id=job.tenant_id)


@register_handler("performance_monitoring.snapshot_sla")
def _sla_handler(job: AsyncJob) -> dict[str, str]:
    return snapshot_sla_task(tenant_id=job.tenant_id, sla_id=UUID(str(job.payload["sla_id"])))


@register_handler("performance_monitoring.enforce_retention")
def _retention_handler(job: AsyncJob) -> dict[str, object]:
    cutoff = (
        datetime.fromisoformat(str(job.payload["cutoff"]).replace("Z", "+00:00")) if job.payload.get("cutoff") else None
    )
    return enforce_retention_task(tenant_id=job.tenant_id, cutoff=cutoff)


__all__ = [
    "EvidenceArchivalUnavailable",
    "enforce_retention_task",
    "evaluate_alerts_task",
    "schedule_alert_evaluation",
    "schedule_retention",
    "schedule_sla_snapshot",
    "snapshot_sla_task",
]
