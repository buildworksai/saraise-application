"""Durable async-job integration for query executions."""

from __future__ import annotations

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import HandlerAlreadyRegistered, get_handler, register_handler
from src.core.tenancy import tenant_context_worker

from .services import ExecutionService

COMMAND = "business_intelligence.execute_query"


@tenant_context_worker
def execute_query_execution(*, tenant_id: object, execution_id: object):
    """Run one domain execution with the canonical worker isolation contract."""
    return ExecutionService.execute_job(tenant_id, execution_id)


def execute_query_job(job: AsyncJob) -> dict[str, object]:
    """Validate a durable command payload and dispatch its tenant-bound work."""
    execution_id = job.payload.get("execution_id")
    tenant_id = job.payload.get("tenant_id")
    if not execution_id or not tenant_id or str(tenant_id) != str(job.tenant_id):
        raise ValueError("BI job payload is missing a valid tenant or execution identifier")
    execution = execute_query_execution(tenant_id=job.tenant_id, execution_id=execution_id)
    return {"execution_id": str(execution.id), "status": execution.status}


def register_job_handlers() -> None:
    """Register idempotently across Django autoreloader invocations."""
    try:
        register_handler(COMMAND, execute_query_job)
    except HandlerAlreadyRegistered:
        existing = get_handler(COMMAND)
        if (getattr(existing, "__module__", ""), getattr(existing, "__qualname__", "")) != (
            __name__,
            execute_query_job.__qualname__,
        ):
            raise


__all__ = ["COMMAND", "execute_query_execution", "execute_query_job", "register_job_handlers"]
