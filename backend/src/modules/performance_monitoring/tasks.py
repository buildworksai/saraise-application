"""Durable tenant-context task handlers for scheduled monitoring work."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from django.utils import timezone

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import enqueue, register_handler
from src.core.tenancy import tenant_context_worker

from .models import LogEntry, Span, Trace
from .services import AlertingService, MetricsCollectionService, SLAMonitoringService


@tenant_context_worker
def evaluate_alerts_task(*, tenant_id: UUID) -> dict[str, object]:
    alerts = AlertingService().evaluate_alerts(tenant_id)
    return {"evaluated_at": timezone.now().isoformat(), "alert_ids": [str(alert.id) for alert in alerts]}


@tenant_context_worker
def snapshot_sla_task(*, tenant_id: UUID, sla_id: UUID) -> dict[str, str]:
    record = SLAMonitoringService().check_sla_compliance(tenant_id, sla_id)
    return {"sla_id": str(sla_id), "compliance_record_id": str(record.id), "status": record.status}


@tenant_context_worker
def enforce_retention_task(*, tenant_id: UUID, cutoff: datetime | None = None) -> dict[str, int]:
    if cutoff is not None and timezone.is_naive(cutoff):
        raise ValueError("Retention cutoff must be timezone-aware.")
    metrics = MetricsCollectionService().purge_expired_data(tenant_id, now=cutoff or timezone.now())
    evidence_cutoff = cutoff or timezone.now() - timedelta(days=30)
    logs, _ = LogEntry._base_manager.filter(tenant_id=tenant_id, timestamp__lt=evidence_cutoff).delete()
    spans, _ = Span._base_manager.filter(tenant_id=tenant_id, started_at__lt=evidence_cutoff).delete()
    traces, _ = Trace._base_manager.filter(tenant_id=tenant_id, started_at__lt=evidence_cutoff).delete()
    return {"metric_data_points": metrics, "logs": logs, "spans": spans, "traces": traces}


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
def _retention_handler(job: AsyncJob) -> dict[str, int]:
    cutoff = (
        datetime.fromisoformat(str(job.payload["cutoff"]).replace("Z", "+00:00")) if job.payload.get("cutoff") else None
    )
    return enforce_retention_task(tenant_id=job.tenant_id, cutoff=cutoff)


__all__ = [
    "enforce_retention_task",
    "evaluate_alerts_task",
    "schedule_alert_evaluation",
    "schedule_retention",
    "schedule_sla_snapshot",
    "snapshot_sla_task",
]
