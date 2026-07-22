"""Durable compliance-risk job handlers.

The foundation owns job lifecycle, retry, timeout, and terminal-state
persistence.  These handlers own only tenant-bound domain orchestration and
return measured outcomes; they never report a notification or workflow as
successful unless its adapter did so.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from datetime import date
from typing import Final
from uuid import UUID

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import HandlerAlreadyRegistered, get_handler, register_handler
from src.core.observability import TaskContext, bind_task_context
from src.core.tenancy import tenant_context_worker

logger = logging.getLogger("saraise.compliance_risk_management")

MARK_CALENDAR_OVERDUE: Final = "compliance_risk.mark_calendar_overdue"
MARK_REMEDIATION_OVERDUE: Final = "compliance_risk.mark_remediation_overdue"
DISPATCH_REMINDERS: Final = "compliance_risk.dispatch_reminders"
GENERATE_RECURRING_CONTROL_TESTS: Final = "compliance_risk.generate_recurring_control_tests"
REGISTERED_COMMANDS: Final = (
    MARK_CALENDAR_OVERDUE,
    MARK_REMEDIATION_OVERDUE,
    DISPATCH_REMINDERS,
    GENERATE_RECURRING_CONTROL_TESTS,
)


def _uuid(value: object, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field} must be a valid UUID") from exc


def _as_of(job: AsyncJob) -> date:
    value = job.payload.get("as_of")
    if not isinstance(value, str):
        raise ValueError("Job payload requires an ISO as_of date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Job payload as_of must be an ISO date") from exc


def _task_context(job: AsyncJob) -> TaskContext:
    return TaskContext(
        correlation_id=_uuid(job.correlation_id, "correlation_id"),
        tenant_id=_uuid(job.tenant_id, "tenant_id"),
        actor_id=str(_uuid(job.actor_id, "actor_id")),
        causation_id=str(job.id),
        job_id=str(job.id),
    )


def _result(value: object, *, count_key: str) -> dict[str, object]:
    """Normalize only measured service results into the durable job document."""

    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, bool):
        raise TypeError("Job service returned a boolean instead of a measured result")
    if isinstance(value, int):
        return {count_key: value}
    if isinstance(value, (list, tuple)):
        return {count_key: len(value)}
    count = getattr(value, "count", None)
    if isinstance(count, int):
        return {count_key: count}
    raise TypeError("Job service returned an unsupported result document")


def _run(job: AsyncJob, operation: str, callback: Callable[[UUID, UUID, date], dict[str, object]]) -> dict[str, object]:
    started = time.monotonic()
    tenant_id = _uuid(job.tenant_id, "tenant_id")
    actor_id = _uuid(job.actor_id, "actor_id")
    try:
        with bind_task_context(_task_context(job)):
            result = callback(tenant_id, actor_id, _as_of(job))
    except Exception as exc:
        logger.error(
            "Compliance-risk job failed",
            extra={
                "event": "compliance_risk.job",
                "domain_module": "compliance_risk_management",
                "tenant_id": str(tenant_id),
                "actor_id": str(actor_id),
                "correlation_id": job.correlation_id,
                "aggregate_type": "async_job",
                "aggregate_id": str(job.id),
                "operation": operation,
                "outcome": "failed",
                "duration_ms": round((time.monotonic() - started) * 1000, 3),
                "error_code": getattr(exc, "code", type(exc).__name__),
                "job_id": str(job.id),
            },
        )
        raise
    logger.info(
        "Compliance-risk job completed",
        extra={
            "event": "compliance_risk.job",
            "domain_module": "compliance_risk_management",
            "tenant_id": str(tenant_id),
            "actor_id": str(actor_id),
            "correlation_id": job.correlation_id,
            "aggregate_type": "async_job",
            "aggregate_id": str(job.id),
            "operation": operation,
            "outcome": "succeeded",
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "job_id": str(job.id),
        },
    )
    return result


@tenant_context_worker
def _mark_calendar_worker(*, tenant_id: UUID, job: AsyncJob) -> dict[str, object]:
    from .services import ComplianceCalendarService

    def execute(tenant: UUID, actor: UUID, as_of: date) -> dict[str, object]:
        value = ComplianceCalendarService.mark_overdue_batch(tenant, actor, as_of, job.id)
        return _result(value, count_key="entries_marked_overdue")

    return _run(job, MARK_CALENDAR_OVERDUE, execute)


def mark_calendar_overdue_handler(job: AsyncJob) -> dict[str, object]:
    return _mark_calendar_worker(tenant_id=_uuid(job.tenant_id, "tenant_id"), job=job)


@tenant_context_worker
def _mark_remediation_worker(*, tenant_id: UUID, job: AsyncJob) -> dict[str, object]:
    from .services import RemediationService

    def execute(tenant: UUID, actor: UUID, as_of: date) -> dict[str, object]:
        value = RemediationService.mark_overdue_batch(tenant, actor, as_of, job.id)
        return _result(value, count_key="actions_marked_overdue")

    return _run(job, MARK_REMEDIATION_OVERDUE, execute)


def mark_remediation_overdue_handler(job: AsyncJob) -> dict[str, object]:
    return _mark_remediation_worker(tenant_id=_uuid(job.tenant_id, "tenant_id"), job=job)


@tenant_context_worker
def _dispatch_reminders_worker(*, tenant_id: UUID, job: AsyncJob) -> dict[str, object]:
    from .services import ComplianceCalendarService

    def execute(tenant: UUID, actor: UUID, as_of: date) -> dict[str, object]:
        value = ComplianceCalendarService.enqueue_due_reminders(
            tenant,
            actor,
            as_of,
            idempotency_key=f"{tenant}:{DISPATCH_REMINDERS}:{as_of.isoformat()}:{job.id}",
        )
        return _result(value, count_key="reminders_queued")

    return _run(job, DISPATCH_REMINDERS, execute)


def dispatch_reminders_handler(job: AsyncJob) -> dict[str, object]:
    return _dispatch_reminders_worker(tenant_id=_uuid(job.tenant_id, "tenant_id"), job=job)


@tenant_context_worker
def _generate_recurring_tests_worker(*, tenant_id: UUID, job: AsyncJob) -> dict[str, object]:
    from .models import Control
    from .services import ControlService

    def execute(tenant: UUID, actor: UUID, as_of: date) -> dict[str, object]:
        controls = list(
            Control.objects.for_tenant(tenant)
            .filter(is_deleted=False, status="active", next_test_due__lte=as_of)
            .order_by("next_test_due", "id")
            .values_list("id", flat=True)
        )
        scheduled = 0
        for control_id in controls:
            outcome = ControlService.schedule_next_test(tenant, actor, control_id, scheduled_for=as_of)
            if outcome is not None:
                scheduled += 1
        return {"controls_evaluated": len(controls), "tests_scheduled": scheduled}

    return _run(job, GENERATE_RECURRING_CONTROL_TESTS, execute)


def generate_recurring_control_tests_handler(job: AsyncJob) -> dict[str, object]:
    return _generate_recurring_tests_worker(tenant_id=_uuid(job.tenant_id, "tenant_id"), job=job)


def _register(command: str, handler: Callable[[AsyncJob], object]) -> None:
    try:
        existing = get_handler(command)
    except Exception as exc:
        if exc.__class__.__name__ != "HandlerNotRegistered":
            raise
        try:
            register_handler(command, handler)
        except HandlerAlreadyRegistered:
            if get_handler(command) is not handler:
                raise
        return
    same_contract = getattr(existing, "__module__", None) == getattr(handler, "__module__", None) and getattr(
        existing, "__name__", None
    ) == getattr(handler, "__name__", None)
    if existing is not handler and not same_contract:
        raise HandlerAlreadyRegistered(f"A different handler is registered for {command!r}")


def register_handlers() -> None:
    """Register all handlers idempotently without replacing extension handlers."""

    for command, handler in (
        (MARK_CALENDAR_OVERDUE, mark_calendar_overdue_handler),
        (MARK_REMEDIATION_OVERDUE, mark_remediation_overdue_handler),
        (DISPATCH_REMINDERS, dispatch_reminders_handler),
        (GENERATE_RECURRING_CONTROL_TESTS, generate_recurring_control_tests_handler),
    ):
        _register(command, handler)


register_handlers()

__all__ = [
    "DISPATCH_REMINDERS",
    "GENERATE_RECURRING_CONTROL_TESTS",
    "MARK_CALENDAR_OVERDUE",
    "MARK_REMEDIATION_OVERDUE",
    "REGISTERED_COMMANDS",
    "dispatch_reminders_handler",
    "generate_recurring_control_tests_handler",
    "mark_calendar_overdue_handler",
    "mark_remediation_overdue_handler",
    "register_handlers",
]
