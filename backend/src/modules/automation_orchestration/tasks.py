"""Durable async command handlers for orchestration workers.

Broker messages contain only tenant identity and durable aggregate IDs.  Each
entry point restores PostgreSQL tenant context before invoking the service
engine, making eager tests and production workers share the same isolation
boundary.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone as datetime_timezone
from typing import Any

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import (
    HandlerAlreadyRegistered,
    HandlerNotRegistered,
    get_handler,
    register_handler,
)
from src.core.tenancy import tenant_context_worker

from .services import (
    EXECUTE_RUN_COMMAND,
    EXECUTE_TASK_COMMAND,
    SCAN_SCHEDULES_COMMAND,
    ExecutionService,
    ScheduleService,
)


def _payload_uuid(job: AsyncJob, field_name: str) -> uuid.UUID:
    raw = job.payload.get(field_name)
    try:
        return raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"Async job {job.id} has an invalid {field_name}") from exc


@tenant_context_worker
def execute_run_worker(*, tenant_id: uuid.UUID, run_id: uuid.UUID) -> dict[str, Any]:
    run = ExecutionService.execute_run(tenant_id, run_id)
    return {"run_id": str(run.id), "status": run.status}


@tenant_context_worker
def execute_task_worker(*, tenant_id: uuid.UUID, attempt_id: uuid.UUID) -> dict[str, Any]:
    attempt = ExecutionService.execute_task(tenant_id, attempt_id)
    return {
        "attempt_id": str(attempt.id),
        "task_run_id": str(attempt.task_run_id),
        "status": attempt.status,
        "error_code": attempt.error_code,
    }


@tenant_context_worker
def scan_schedules_worker(
    *,
    tenant_id: uuid.UUID,
    now: datetime,
    batch_size: int = 100,
) -> dict[str, Any]:
    if now.tzinfo is None:
        raise ValueError("schedule scan timestamp must be timezone-aware")
    claims = ScheduleService.claim_due_schedules(tenant_id, now, batch_size)
    enqueued: list[str] = []
    skipped: list[str] = []
    for claim in claims:
        if not claim.should_enqueue:
            skipped.append(str(claim.schedule_id))
            continue
        run = ScheduleService.enqueue_due_schedule(tenant_id, claim.schedule_id, claim.scheduled_for)
        if run is None:
            skipped.append(str(claim.schedule_id))
        else:
            enqueued.append(str(run.id))
    from .health import mark_schedule_scanner_healthy

    mark_schedule_scanner_healthy()
    return {
        "claimed": len(claims),
        "enqueued_run_ids": enqueued,
        "skipped_schedule_ids": skipped,
    }


def _execute_run_handler(job: AsyncJob) -> dict[str, Any]:
    return execute_run_worker(tenant_id=job.tenant_id, run_id=_payload_uuid(job, "run_id"))


def _execute_task_handler(job: AsyncJob) -> dict[str, Any]:
    return execute_task_worker(tenant_id=job.tenant_id, attempt_id=_payload_uuid(job, "attempt_id"))


def _scan_schedules_handler(job: AsyncJob) -> dict[str, Any]:
    raw_now = job.payload.get("now")
    if raw_now in (None, ""):
        now = datetime.now(tz=datetime_timezone.utc)
    else:
        try:
            now = datetime.fromisoformat(str(raw_now))
        except ValueError as exc:
            raise ValueError(f"Async job {job.id} has an invalid schedule scan timestamp") from exc
    batch_size = job.payload.get("batch_size", 100)
    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise ValueError(f"Async job {job.id} has an invalid batch_size")
    return scan_schedules_worker(tenant_id=job.tenant_id, now=now, batch_size=batch_size)


_COMMAND_HANDLERS = {
    EXECUTE_RUN_COMMAND: _execute_run_handler,
    EXECUTE_TASK_COMMAND: _execute_task_handler,
    SCAN_SCHEDULES_COMMAND: _scan_schedules_handler,
}


def register_async_handlers() -> None:
    """Register stable commands idempotently across Django autoreload."""

    for command, handler in _COMMAND_HANDLERS.items():
        try:
            existing = get_handler(command)
        except HandlerNotRegistered:
            register_handler(command, handler)
            continue
        if existing is not handler:
            raise HandlerAlreadyRegistered(f"Async command {command!r} is already owned by a different handler")


__all__ = [
    "execute_run_worker",
    "execute_task_worker",
    "register_async_handlers",
    "scan_schedules_worker",
]
