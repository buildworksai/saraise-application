"""Durable async command handlers for disaster-recovery workflows."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import register_handler
from src.core.observability import TaskContext, bind_task_context
from src.core.tenancy import tenant_context_worker

from .metrics import BDR_BACKUP_REQUESTS, BDR_JOB_QUEUE_DELAY, BDR_PROVIDER_FAILURES

logger = logging.getLogger("saraise.backup_disaster_recovery.tasks")

BACKUP_REQUEST_COMMAND = "backup_disaster_recovery.backup.request"
RECOVERY_POINT_VERIFY_COMMAND = "backup_disaster_recovery.recovery_point.verify"
RESTORE_VALIDATE_COMMAND = "backup_disaster_recovery.restore.validate"
RESTORE_EXECUTE_COMMAND = "backup_disaster_recovery.restore.execute"
EXERCISE_EXECUTE_COMMAND = "backup_disaster_recovery.exercise.execute"

ASYNC_COMMANDS = (
    BACKUP_REQUEST_COMMAND,
    RECOVERY_POINT_VERIFY_COMMAND,
    RESTORE_VALIDATE_COMMAND,
    RESTORE_EXECUTE_COMMAND,
    EXERCISE_EXECUTE_COMMAND,
)


class InvalidWorkerPayload(ValueError):
    """Raised before a malformed durable command can reach business logic."""


def _metric_error_class(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, InvalidWorkerPayload):
        return "invalid_payload"
    if type(exc).__name__ in {"CircuitBreakerError", "CircuitOpenError"}:
        return "circuit_open"
    return "provider_failure"


def _payload_uuid(job: AsyncJob, key: str) -> UUID:
    try:
        return UUID(str(job.payload[key]))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise InvalidWorkerPayload(f"job payload requires a valid {key}") from exc


def _load_job(tenant_id: UUID, job_id: UUID, expected_command: str) -> AsyncJob:
    job = AsyncJob.objects.filter(tenant_id=tenant_id, id=job_id).first()
    if job is None:
        raise InvalidWorkerPayload("durable job does not exist for tenant")
    if job.command != expected_command:
        raise InvalidWorkerPayload("durable job command does not match worker")
    return job


def _json_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (UUID, datetime, Enum)):
        return str(value.value if isinstance(value, Enum) else value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise InvalidWorkerPayload("service returned a non-serializable result")


def _result_summary(result: object) -> dict[str, object]:
    """Persist an allowlisted result summary, never a raw provider payload."""
    if result is None:
        raise InvalidWorkerPayload("service returned no execution result")
    source: Mapping[str, object]
    if is_dataclass(result) and not isinstance(result, type):
        source = asdict(result)
    elif isinstance(result, Mapping):
        source = result
    else:
        source = {
            key: getattr(result, key)
            for key in ("id", "status", "backup_job_id", "async_job_id")
            if hasattr(result, key)
        }
    allowed = (
        "id",
        "status",
        "backup_job_id",
        "recovery_point_id",
        "restore_run_id",
        "exercise_id",
        "async_job_id",
        "idempotency_key",
    )
    summary = {key: _json_value(source[key]) for key in allowed if key in source}
    if not summary:
        raise InvalidWorkerPayload("service result has no durable identity or status")
    return summary


def _task_context(job: AsyncJob) -> TaskContext:
    causation = job.payload.get("causation_id")
    return TaskContext(
        correlation_id=UUID(str(job.correlation_id)),
        tenant_id=job.tenant_id,
        actor_id=job.actor_id or None,
        causation_id=str(causation) if causation else None,
        job_id=str(job.id),
    )


def _run(
    *,
    tenant_id: UUID,
    job_id: UUID,
    command: str,
    operation: Callable[[AsyncJob], object],
) -> dict[str, object]:
    job = _load_job(tenant_id, job_id, command)
    queued_at = job.created_at
    delay = max(0.0, (datetime.now(tz=queued_at.tzinfo) - queued_at).total_seconds())
    BDR_JOB_QUEUE_DELAY.observe(delay)
    started = time.monotonic()
    with bind_task_context(_task_context(job)):
        try:
            result = operation(job)
        except Exception as exc:
            if command == BACKUP_REQUEST_COMMAND:
                BDR_BACKUP_REQUESTS.labels(result="failed").inc()
            BDR_PROVIDER_FAILURES.labels(adapter="domain", error_class=_metric_error_class(exc)).inc()
            logger.exception(
                "Disaster-recovery worker failed",
                extra={
                    "operation": command,
                    "tenant_id": str(tenant_id),
                    "job_id": str(job_id),
                    "duration": time.monotonic() - started,
                    "result_classification": "failed",
                },
            )
            raise
        summary = _result_summary(result)
        if command == BACKUP_REQUEST_COMMAND:
            BDR_BACKUP_REQUESTS.labels(result="accepted").inc()
        logger.info(
            "Disaster-recovery worker completed",
            extra={
                "operation": command,
                "tenant_id": str(tenant_id),
                "job_id": str(job_id),
                "duration": time.monotonic() - started,
                "result_classification": "completed",
            },
        )
        return summary


@tenant_context_worker
def backup_request_worker(*, tenant_id: UUID, job_id: UUID) -> dict[str, object]:
    def execute(job: AsyncJob) -> object:
        from .services import BackupExecutionFacade

        return BackupExecutionFacade().execute_backup_request(tenant_id, job.id)

    return _run(
        tenant_id=tenant_id,
        job_id=job_id,
        command=BACKUP_REQUEST_COMMAND,
        operation=execute,
    )


@tenant_context_worker
def recovery_point_verify_worker(*, tenant_id: UUID, job_id: UUID) -> dict[str, object]:
    def execute(job: AsyncJob) -> object:
        from .services import RecoveryPointService

        return RecoveryPointService().execute_verification(
            tenant_id,
            _payload_uuid(job, "recovery_point_id"),
            job.id,
        )

    return _run(
        tenant_id=tenant_id,
        job_id=job_id,
        command=RECOVERY_POINT_VERIFY_COMMAND,
        operation=execute,
    )


@tenant_context_worker
def restore_validate_worker(*, tenant_id: UUID, job_id: UUID) -> dict[str, object]:
    def execute(job: AsyncJob) -> object:
        from .services import RestoreService

        return RestoreService().validate_restore(tenant_id, _payload_uuid(job, "restore_run_id"), job.id)

    return _run(tenant_id=tenant_id, job_id=job_id, command=RESTORE_VALIDATE_COMMAND, operation=execute)


@tenant_context_worker
def restore_execute_worker(*, tenant_id: UUID, job_id: UUID) -> dict[str, object]:
    def execute(job: AsyncJob) -> object:
        from .services import RestoreService

        return RestoreService().execute_restore_job(tenant_id, _payload_uuid(job, "restore_run_id"), job.id)

    return _run(tenant_id=tenant_id, job_id=job_id, command=RESTORE_EXECUTE_COMMAND, operation=execute)


@tenant_context_worker
def exercise_execute_worker(*, tenant_id: UUID, job_id: UUID) -> dict[str, object]:
    def execute(job: AsyncJob) -> object:
        from .services import DRExerciseService

        return DRExerciseService().execute_exercise(tenant_id, _payload_uuid(job, "exercise_id"), job.id)

    return _run(tenant_id=tenant_id, job_id=job_id, command=EXERCISE_EXECUTE_COMMAND, operation=execute)


def _job_handler(worker: Callable[..., dict[str, object]]) -> Callable[[AsyncJob], dict[str, object]]:
    def handler(job: AsyncJob) -> dict[str, object]:
        return worker(tenant_id=job.tenant_id, job_id=job.id)

    handler.__name__ = f"registered_{worker.__name__}"
    return handler


def register_async_handlers() -> None:
    """Register all commands without replacement; duplicates stop startup."""
    for command, worker in (
        (BACKUP_REQUEST_COMMAND, backup_request_worker),
        (RECOVERY_POINT_VERIFY_COMMAND, recovery_point_verify_worker),
        (RESTORE_VALIDATE_COMMAND, restore_validate_worker),
        (RESTORE_EXECUTE_COMMAND, restore_execute_worker),
        (EXERCISE_EXECUTE_COMMAND, exercise_execute_worker),
    ):
        register_handler(command, _job_handler(worker), replace=False)


__all__ = [
    "ASYNC_COMMANDS",
    "BACKUP_REQUEST_COMMAND",
    "EXERCISE_EXECUTE_COMMAND",
    "InvalidWorkerPayload",
    "RECOVERY_POINT_VERIFY_COMMAND",
    "RESTORE_EXECUTE_COMMAND",
    "RESTORE_VALIDATE_COMMAND",
    "backup_request_worker",
    "exercise_execute_worker",
    "recovery_point_verify_worker",
    "register_async_handlers",
    "restore_execute_worker",
    "restore_validate_worker",
]
