"""Transactional services and execution registry for durable async jobs."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, TypeVar

from django.db import IntegrityError, transaction
from django.utils import timezone

from src.core.middleware.correlation import get_correlation_id

from .models import AsyncJob, JobStatus, JobTransition, OutboxEvent

JobHandler = Callable[[AsyncJob], Any]
HandlerT = TypeVar("HandlerT", bound=JobHandler)


class AsyncJobError(RuntimeError):
    """Base error for async job orchestration."""


class InvalidJobTransition(AsyncJobError):
    """Raised when a requested state transition is not allowed."""


class ConcurrentJobTransition(AsyncJobError):
    """Raised when an expected state no longer matches the stored state."""


class HandlerNotRegistered(AsyncJobError):
    """Raised when a queued command has no executable handler."""


class HandlerAlreadyRegistered(AsyncJobError):
    """Raised when a command registration would silently replace a handler."""


class JobAlreadyRunning(AsyncJobError):
    """Raised when an at-least-once delivery overlaps active execution."""


class JobExecutionError(AsyncJobError):
    """Raised after a handler failure has been durably recorded."""


TERMINAL_STATUSES = frozenset(
    {
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.TIMED_OUT,
    }
)

ALLOWED_TRANSITIONS: Mapping[str, frozenset[str]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.TIMED_OUT,
            JobStatus.RETRYING,
        }
    ),
    JobStatus.RETRYING: frozenset(
        {
            JobStatus.QUEUED,
            JobStatus.RUNNING,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.TIMED_OUT,
        }
    ),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
    JobStatus.TIMED_OUT: frozenset(),
}

_handlers: dict[str, JobHandler] = {}
_handler_lock = threading.RLock()


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _actor_identifier(value: uuid.UUID | str) -> str:
    actor_id = _required_text(str(value), "actor_id")
    if len(actor_id) > 255:
        raise ValueError("actor_id must not exceed 255 characters")
    return actor_id


def _as_uuid(value: uuid.UUID | str, field_name: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc


def register_handler(
    command: str,
    handler: HandlerT | None = None,
    *,
    replace: bool = False,
) -> HandlerT | Callable[[HandlerT], HandlerT]:
    """Register a command handler, directly or as a decorator.

    Replacement is explicit so importing two paid modules cannot silently make
    the winner depend on import order.
    """

    normalized_command = _required_text(command, "command")

    def decorator(candidate: HandlerT) -> HandlerT:
        if not callable(candidate):
            raise TypeError("handler must be callable")
        with _handler_lock:
            if normalized_command in _handlers and not replace:
                raise HandlerAlreadyRegistered(f"A handler is already registered for {normalized_command!r}")
            _handlers[normalized_command] = candidate
        return candidate

    if handler is None:
        return decorator
    return decorator(handler)


def unregister_handler(command: str) -> JobHandler | None:
    """Remove and return a registered handler; primarily useful for extensions and tests."""
    with _handler_lock:
        return _handlers.pop(command, None)


def get_handler(command: str) -> JobHandler:
    """Return the registered handler or fail explicitly."""
    with _handler_lock:
        try:
            return _handlers[command]
        except KeyError as exc:
            raise HandlerNotRegistered(f"No async job handler is registered for {command!r}") from exc


def _create_outbox_event(job: AsyncJob, event_type: str) -> OutboxEvent:
    """Create the durable broker message for a job while inside its state transaction."""
    return OutboxEvent.objects.create(
        tenant_id=job.tenant_id,
        aggregate_type="async_job",
        aggregate_id=job.id,
        event_type=event_type,
        payload={
            "job_id": str(job.id),
            "tenant_id": str(job.tenant_id),
            "command": job.command,
            "correlation_id": job.correlation_id,
        },
    )


def enqueue(
    tenant_id: uuid.UUID | str,
    actor_id: uuid.UUID | str,
    command: str,
    payload: dict[str, Any],
    idempotency_key: str,
) -> AsyncJob:
    """Atomically persist a job and its broker outbox event.

    The database uniqueness constraint is the final authority for concurrent
    callers. Only the caller that creates the job creates its transition and
    outbox rows; every duplicate receives the already durable job.
    """

    tenant_uuid = _as_uuid(tenant_id, "tenant_id")
    actor_identifier = _actor_identifier(actor_id)
    normalized_command = _required_text(command, "command")
    normalized_key = _required_text(idempotency_key, "idempotency_key")
    if len(normalized_command) > 255:
        raise ValueError("command must not exceed 255 characters")
    if len(normalized_key) > 255:
        raise ValueError("idempotency_key must not exceed 255 characters")
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dictionary")

    with transaction.atomic():
        existing = AsyncJob.objects.filter(tenant_id=tenant_uuid, idempotency_key=normalized_key).first()
        if existing is not None:
            return existing

        try:
            # The savepoint keeps the outer transaction usable if another
            # transaction wins the unique-key race.
            with transaction.atomic():
                job = AsyncJob.objects.create(
                    tenant_id=tenant_uuid,
                    actor_id=actor_identifier,
                    command=normalized_command,
                    idempotency_key=normalized_key,
                    payload=payload,
                    correlation_id=get_correlation_id() or str(uuid.uuid4()),
                )
        except IntegrityError:
            existing = AsyncJob.objects.filter(tenant_id=tenant_uuid, idempotency_key=normalized_key).first()
            if existing is None:
                raise
            return existing

        JobTransition.objects.create(
            tenant_id=tenant_uuid,
            job=job,
            from_status="",
            to_status=JobStatus.QUEUED,
            actor_id=actor_identifier,
            reason="Job enqueued",
        )
        _create_outbox_event(job, "async_job.enqueued")
        return job


def _transition_locked(
    job: AsyncJob,
    to_status: str,
    *,
    result: Any = None,
    error_message: str = "",
    reason: str = "",
    actor_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AsyncJob:
    from_status = job.status
    if from_status in TERMINAL_STATUSES:
        raise InvalidJobTransition(f"Terminal job {job.id} in state {from_status!r} is immutable")
    if to_status not in ALLOWED_TRANSITIONS.get(from_status, frozenset()):
        raise InvalidJobTransition(f"Cannot transition job {job.id} from {from_status!r} to {to_status!r}")

    now = timezone.now()
    update_fields = {"status", "updated_at"}
    job.status = to_status
    if to_status == JobStatus.RUNNING:
        job.attempts += 1
        job.started_at = now
        job.completed_at = None
        job.error_message = ""
        update_fields.update({"attempts", "started_at", "completed_at", "error_message"})
    if to_status == JobStatus.SUCCEEDED:
        job.result = result
        job.error_message = ""
        job.completed_at = now
        update_fields.update({"result", "error_message", "completed_at"})
    elif to_status in TERMINAL_STATUSES:
        job.error_message = error_message
        job.completed_at = now
        update_fields.update({"error_message", "completed_at"})
    elif to_status == JobStatus.RETRYING:
        job.error_message = error_message
        update_fields.add("error_message")

    job.save(update_fields=sorted(update_fields))
    JobTransition.objects.create(
        tenant_id=job.tenant_id,
        job=job,
        from_status=from_status,
        to_status=to_status,
        actor_id=actor_id,
        reason=reason,
        metadata=metadata or {},
    )
    return job


def transition(
    job_id: uuid.UUID | str,
    tenant_id: uuid.UUID | str,
    to_status: str,
    *,
    expected_status: str | None = None,
    result: Any = None,
    error_message: str = "",
    reason: str = "",
    actor_id: uuid.UUID | str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AsyncJob:
    """Apply and audit one guarded state transition under a row lock."""

    tenant_uuid = _as_uuid(tenant_id, "tenant_id")
    job_uuid = _as_uuid(job_id, "job_id")
    actor_identifier = _actor_identifier(actor_id) if actor_id is not None else None
    if to_status not in JobStatus.values:
        raise InvalidJobTransition(f"Unknown async job status {to_status!r}")

    with transaction.atomic():
        job = AsyncJob.objects.select_for_update().get(id=job_uuid, tenant_id=tenant_uuid)
        if expected_status is not None and job.status != expected_status:
            raise ConcurrentJobTransition(f"Expected job {job.id} to be {expected_status!r}, but it is {job.status!r}")
        job = _transition_locked(
            job,
            to_status,
            result=result,
            error_message=error_message,
            reason=reason,
            actor_id=actor_identifier,
            metadata=metadata,
        )
        if to_status == JobStatus.RETRYING:
            _create_outbox_event(job, "async_job.retry_requested")
        return job


def execute(job_id: uuid.UUID | str, tenant_id: uuid.UUID | str) -> AsyncJob:
    """Claim and execute a job exactly once per non-overlapping delivery.

    Brokers are at-least-once. A redelivery after completion returns the stored
    terminal job without invoking the handler. Extension handlers must use
    ``job.id`` as their idempotency token for external side effects because no
    database can atomically commit an arbitrary third-party operation.
    """

    tenant_uuid = _as_uuid(tenant_id, "tenant_id")
    job_uuid = _as_uuid(job_id, "job_id")

    with transaction.atomic():
        job = AsyncJob.objects.select_for_update().get(id=job_uuid, tenant_id=tenant_uuid)
        if job.status in TERMINAL_STATUSES:
            return job
        if job.status == JobStatus.RUNNING:
            raise JobAlreadyRunning(f"Job {job.id} is already running")
        handler = get_handler(job.command)
        _transition_locked(job, JobStatus.RUNNING, reason="Handler claimed job")

    try:
        result = handler(job)
    except Exception as exc:
        transition(
            job.id,
            tenant_uuid,
            JobStatus.FAILED,
            expected_status=JobStatus.RUNNING,
            error_message=str(exc),
            reason="Handler raised an exception",
        )
        raise JobExecutionError(f"Handler for job {job.id} failed") from exc

    return transition(
        job.id,
        tenant_uuid,
        JobStatus.SUCCEEDED,
        expected_status=JobStatus.RUNNING,
        result=result,
        reason="Handler completed",
    )


def recover_stale_jobs(
    tenant_id: uuid.UUID | str,
    *,
    stale_before: datetime,
) -> list[AsyncJob]:
    """Move stale running jobs to retrying so a scheduler can re-enqueue them."""

    tenant_uuid = _as_uuid(tenant_id, "tenant_id")
    stale_ids = list(
        AsyncJob.objects.filter(
            tenant_id=tenant_uuid,
            status=JobStatus.RUNNING,
            updated_at__lt=stale_before,
        ).values_list("id", flat=True)
    )
    recovered: list[AsyncJob] = []
    for job_id in stale_ids:
        try:
            recovered.append(
                transition(
                    job_id,
                    tenant_uuid,
                    JobStatus.RETRYING,
                    expected_status=JobStatus.RUNNING,
                    error_message="Execution lease expired",
                    reason="Recovered stale running job",
                )
            )
        except ConcurrentJobTransition:
            # Another worker recovered or completed it after the candidate scan.
            continue
    return recovered
