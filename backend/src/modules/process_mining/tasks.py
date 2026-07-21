"""Durable command handlers with mandatory worker tenant context."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import register_handler
from src.core.tenancy import tenant_context_worker

from .services import BottleneckService, ConformanceService, EventLogService, ExportService, ProcessDiscoveryService


def _uuid(payload: Mapping[str, object], key: str) -> UUID:
    try:
        return UUID(str(payload[key]))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"Durable payload requires UUID field {key!r}.") from exc


@tenant_context_worker
def export_event_log_task(*, tenant_id: UUID, export_id: UUID, async_job_id: UUID) -> dict[str, str]:
    value = ExportService().run_export(tenant_id, export_id, async_job_id)
    return {"export_id": str(value.id), "status": value.status, "sha256": value.sha256}


@tenant_context_worker
def discover_process_task(*, tenant_id: UUID, discovery_id: UUID, async_job_id: UUID) -> dict[str, str]:
    value = ProcessDiscoveryService().run_discovery(tenant_id, discovery_id, async_job_id)
    return {"discovery_id": str(value.id), "status": value.status}


@tenant_context_worker
def check_conformance_task(*, tenant_id: UUID, check_id: UUID, async_job_id: UUID) -> dict[str, str]:
    value = ConformanceService().run_check(tenant_id, check_id, async_job_id)
    return {"check_id": str(value.id), "status": value.status}


@tenant_context_worker
def analyze_bottlenecks_task(*, tenant_id: UUID, analysis_id: UUID, async_job_id: UUID) -> dict[str, str]:
    value = BottleneckService().run_analysis(tenant_id, analysis_id, async_job_id)
    return {"analysis_id": str(value.id), "status": value.status}


@tenant_context_worker
def purge_events_task(*, tenant_id: UUID, retention_days: int, actor_id: UUID) -> dict[str, int]:
    count = EventLogService().purge_expired_events(tenant_id, retention_days, actor_id)
    return {"purged": count}


@register_handler("process_mining.export_event_log")
def _export_handler(job: AsyncJob) -> dict[str, str]:
    return export_event_log_task(tenant_id=job.tenant_id, export_id=_uuid(job.payload, "export_id"), async_job_id=job.id)


@register_handler("process_mining.discover_process")
def _discovery_handler(job: AsyncJob) -> dict[str, str]:
    return discover_process_task(tenant_id=job.tenant_id, discovery_id=_uuid(job.payload, "discovery_id"), async_job_id=job.id)


@register_handler("process_mining.check_conformance")
def _conformance_handler(job: AsyncJob) -> dict[str, str]:
    return check_conformance_task(tenant_id=job.tenant_id, check_id=_uuid(job.payload, "check_id"), async_job_id=job.id)


@register_handler("process_mining.analyze_bottlenecks")
def _bottleneck_handler(job: AsyncJob) -> dict[str, str]:
    return analyze_bottlenecks_task(tenant_id=job.tenant_id, analysis_id=_uuid(job.payload, "analysis_id"), async_job_id=job.id)


@register_handler("process_mining.purge_events")
def _purge_handler(job: AsyncJob) -> dict[str, int]:
    days = job.payload.get("retention_days", 365)
    if isinstance(days, bool) or not isinstance(days, int):
        raise ValueError("retention_days must be an integer")
    return purge_events_task(tenant_id=job.tenant_id, retention_days=days, actor_id=_uuid(job.payload, "actor_id"))


__all__ = ["analyze_bottlenecks_task", "check_conformance_task", "discover_process_task", "export_event_log_task", "purge_events_task"]
