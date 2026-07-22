"""Durable command handlers for workflow execution and task expiry."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from django.utils import timezone

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import (
    HandlerAlreadyRegistered,
    get_handler,
    register_handler,
)
from src.core.observability.correlation import TaskContext, bind_task_context
from src.core.tenancy import tenant_context_worker

from .services import (
    EXECUTE_INSTANCE_COMMAND,
    EXPIRE_TASKS_COMMAND,
    SaraiseWorkflowExecutionAdapter,
    WorkflowExecutionService,
    WorkflowTaskService,
)


def _task_context(job: AsyncJob) -> TaskContext:
    try:
        correlation_id = UUID(str(job.correlation_id))
    except (TypeError, ValueError):
        # AsyncJob.enqueue always writes a UUID; malformed legacy rows fail the
        # handler rather than executing without trace identity.
        raise ValueError("Workflow job has an invalid correlation identifier")
    return TaskContext(
        correlation_id=correlation_id,
        tenant_id=job.tenant_id,
        actor_id=job.actor_id,
        causation_id=str(job.id),
        job_id=str(job.id),
    )


@tenant_context_worker
def _execute_worker(*, tenant_id: UUID, job: AsyncJob) -> dict[str, Any]:
    with bind_task_context(_task_context(job)):
        try:
            return WorkflowExecutionService.execute_instance_job(tenant_id, job)
        except Exception:
            instance_id = job.payload.get("instance_id")
            if instance_id:
                try:
                    WorkflowExecutionService.fail_instance(
                        tenant_id,
                        instance_id,
                        "WORKER_EXECUTION_FAILED",
                        "Durable workflow execution failed.",
                        f"job:{job.id}:worker-failure",
                    )
                except Exception:
                    # The original exception remains authoritative.  A terminal
                    # or concurrently cancelled instance legitimately rejects
                    # the compensating fail transition.
                    pass
            raise


def execute_instance_handler(job: AsyncJob) -> dict[str, Any]:
    """Core one-job ABI wrapper; tenant identity remains the first worker input."""

    return _execute_worker(tenant_id=job.tenant_id, job=job)


@tenant_context_worker
def _expire_worker(*, tenant_id: UUID, job: AsyncJob) -> dict[str, Any]:
    with bind_task_context(_task_context(job)):
        raw_now = job.payload.get("now")
        if raw_now is None:
            effective_at = timezone.now()
        elif isinstance(raw_now, str):
            try:
                effective_at = datetime.fromisoformat(raw_now.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Task-expiry job contains an invalid timestamp") from exc
        else:
            raise ValueError("Task-expiry job contains an invalid timestamp")
        expired = WorkflowTaskService.expire_due_tasks(tenant_id, effective_at)
        return {"expired_tasks": expired, "evaluated_at": effective_at.isoformat()}


def expire_tasks_handler(job: AsyncJob) -> dict[str, Any]:
    return _expire_worker(tenant_id=job.tenant_id, job=job)


def _register_command(command: str, handler: Any) -> None:
    try:
        existing = get_handler(command)
    except Exception as exc:
        # Only the explicit not-registered path is acceptable, but importing
        # the concrete exception here would make startup sensitive to older
        # core versions. Register and let duplicate protection remain final.
        if exc.__class__.__name__ != "HandlerNotRegistered":
            raise
        try:
            register_handler(command, handler)
        except HandlerAlreadyRegistered:
            if get_handler(command) is not handler:
                raise
    else:
        same_contract = (
            getattr(existing, "__module__", None) == getattr(handler, "__module__", None)
            and getattr(existing, "__name__", None) == getattr(handler, "__name__", None)
        )
        if existing is not handler and not same_contract:
            raise HandlerAlreadyRegistered(f"A different handler is registered for {command!r}")


def _register_orchestration_adapter() -> None:
    from src.modules.automation_orchestration.workflow_adapter import (
        get_workflow_adapter,
        register_workflow_adapter,
    )

    try:
        existing = get_workflow_adapter()
    except RuntimeError:
        register_workflow_adapter(SaraiseWorkflowExecutionAdapter())
        return
    if not isinstance(existing, SaraiseWorkflowExecutionAdapter):
        raise RuntimeError("A different workflow execution adapter is already registered")


def register_async_handlers() -> None:
    """Register durable handlers and the orchestration SPI idempotently."""

    _register_command(EXECUTE_INSTANCE_COMMAND, execute_instance_handler)
    _register_command(EXPIRE_TASKS_COMMAND, expire_tasks_handler)
    _register_orchestration_adapter()


__all__ = [
    "execute_instance_handler",
    "expire_tasks_handler",
    "register_async_handlers",
]
