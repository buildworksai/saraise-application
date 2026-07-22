"""Durable data-migration command handlers."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import register_handler
from src.core.tenancy import tenant_context_worker

from .services import MigrationExecutionService, RollbackService, SourceInspectionService


def _uuid(payload: Mapping[str, object], key: str) -> UUID:
    try:
        return UUID(str(payload[key]))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"durable data-migration payload requires UUID field {key!r}") from exc


@tenant_context_worker
def execute_run_task(*, tenant_id: UUID, run_id: UUID) -> dict[str, str]:
    run = MigrationExecutionService.execute(tenant_id, run_id)
    return {"run_id": str(run.id), "status": run.status}


@tenant_context_worker
def inspect_source_task(*, tenant_id: UUID, job_id: UUID, job_version_id: UUID) -> dict[str, object]:
    profile = SourceInspectionService.inspect(tenant_id, job_id, job_version_id)
    return profile.as_dict() if hasattr(profile, "as_dict") else dict(profile)


@tenant_context_worker
def execute_rollback_task(*, tenant_id: UUID, rollback_id: UUID) -> dict[str, str]:
    rollback = RollbackService.execute(tenant_id, rollback_id)
    return {"rollback_id": str(rollback.id), "status": rollback.status}


@register_handler("data_migration.execute")
def _execute_handler(job: AsyncJob) -> dict[str, str]:
    return execute_run_task(tenant_id=job.tenant_id, run_id=_uuid(job.payload, "run_id"))


@register_handler("data_migration.inspect")
def _inspect_handler(job: AsyncJob) -> dict[str, object]:
    return inspect_source_task(
        tenant_id=job.tenant_id,
        job_id=_uuid(job.payload, "job_id"),
        job_version_id=_uuid(job.payload, "job_version_id"),
    )


@register_handler("data_migration.rollback")
def _rollback_handler(job: AsyncJob) -> dict[str, str]:
    return execute_rollback_task(tenant_id=job.tenant_id, rollback_id=_uuid(job.payload, "rollback_id"))


__all__ = ["execute_rollback_task", "execute_run_task", "inspect_source_task"]
