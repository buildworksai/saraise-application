"""Durable fixed-assets job handlers with explicit tenant context."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import (
    HandlerAlreadyRegistered,
    HandlerNotRegistered,
    get_handler,
    register_handler,
)
from src.core.tenancy import tenant_context_worker

from .services import DepreciationService

POST_LINE_COMMAND = "fixed_assets.post_line"
POST_DUE_COMMAND = "fixed_assets.post_due_lines"


@tenant_context_worker
def post_line_worker(*, tenant_id: UUID, line_id: UUID, actor_id: str, job_id: UUID) -> dict[str, str]:
    line = DepreciationService.post_line(
        tenant_id,
        line_id,
        actor_id,
        job_id,
        transition_key=f"job:{job_id}:line:{line_id}",
    )
    return {"line_id": str(line.id), "status": str(line.status)}


@tenant_context_worker
def post_due_worker(
    *, tenant_id: UUID, through_date: date, actor_id: str, job_id: UUID
) -> dict[str, list[str]]:
    return DepreciationService.post_due_lines(tenant_id, through_date, actor_id, job_id)


def _post_line_handler(job: AsyncJob) -> dict[str, str]:
    return post_line_worker(
        tenant_id=job.tenant_id,
        line_id=UUID(str(job.payload["line_id"])),
        actor_id=job.actor_id,
        job_id=job.id,
    )


def _post_due_handler(job: AsyncJob) -> dict[str, list[str]]:
    return post_due_worker(
        tenant_id=job.tenant_id,
        through_date=date.fromisoformat(str(job.payload["through_date"])),
        actor_id=job.actor_id,
        job_id=job.id,
    )


def register_handlers() -> None:
    """Install handlers idempotently without permitting a competing owner."""

    for command, candidate in (
        (POST_LINE_COMMAND, _post_line_handler),
        (POST_DUE_COMMAND, _post_due_handler),
    ):
        try:
            current = get_handler(command)
        except HandlerNotRegistered:
            current = None
        if current is None:
            try:
                register_handler(command, candidate)
            except HandlerAlreadyRegistered:
                current = get_handler(command)
                if current is not candidate:
                    raise
        elif current is not candidate:
            raise RuntimeError(f"A different handler is already registered for {command!r}.")


__all__ = [
    "POST_DUE_COMMAND",
    "POST_LINE_COMMAND",
    "post_due_worker",
    "post_line_worker",
    "register_handlers",
]
