"""Tenant-bound durable handlers for accounting background commands."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import HandlerAlreadyRegistered, get_handler, register_handler
from src.core.observability import TaskContext, bind_task_context
from src.core.tenancy import tenant_context

logger = logging.getLogger("saraise.accounting_finance")

JOURNAL_IMPORT_COMMAND: Final = "accounting.journal_entries.import"
REPORT_GENERATE_COMMAND: Final = "accounting.reports.generate"
AR_MARK_OVERDUE_COMMAND: Final = "accounting.ar.mark_overdue"
REGISTERED_COMMANDS: Final = (
    JOURNAL_IMPORT_COMMAND,
    REPORT_GENERATE_COMMAND,
    AR_MARK_OVERDUE_COMMAND,
)

_REPORT_TYPES: Final = frozenset(
    {"trial_balance", "general_ledger", "balance_sheet", "income_statement", "cash_flow"}
)
_REPORT_PARAMETER_KEYS: Final = {
    "trial_balance": frozenset({"as_of_date"}),
    "general_ledger": frozenset({"account_id", "start_date", "end_date"}),
    "balance_sheet": frozenset({"as_of_date"}),
    "income_statement": frozenset({"start_date", "end_date"}),
    "cash_flow": frozenset({"start_date", "end_date"}),
}
_OPAQUE_REFERENCE: Final = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class AccountingJobError(RuntimeError):
    """Stable, redacted worker boundary error."""

    code = "ACCOUNTING_JOB_FAILED"


class AccountingJobPayloadError(AccountingJobError, ValueError):
    code = "JOB_PAYLOAD_INVALID"


class AccountingJobCapabilityUnavailable(AccountingJobError):
    code = "CAPABILITY_UNAVAILABLE"


def _uuid(value: object, field_name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise AccountingJobPayloadError(f"{field_name} must be a valid UUID.") from exc


def _date(value: object, field_name: str) -> date:
    if isinstance(value, datetime):
        raise AccountingJobPayloadError(f"{field_name} must be a date, not a datetime.")
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise AccountingJobPayloadError(f"{field_name} must be an ISO date.") from exc


def _opaque_reference(value: object) -> str:
    reference = str(value or "").strip()
    if not _OPAQUE_REFERENCE.fullmatch(reference) or reference.startswith("."):
        raise AccountingJobPayloadError("file_reference must be an opaque managed reference.")
    return reference


def _payload(job: AsyncJob, *, allowed: frozenset[str], required: frozenset[str]) -> dict[str, object]:
    if not isinstance(job.payload, Mapping):
        raise AccountingJobPayloadError("Job payload must be an object.")
    keys = {str(key) for key in job.payload}
    if keys - allowed or required - keys:
        raise AccountingJobPayloadError("Job payload fields do not match the command schema.")
    return {str(key): value for key, value in job.payload.items()}


def _json(value: object) -> object:
    """Convert allowlisted domain results to durable JSON without floats."""

    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, (UUID, date, datetime, Decimal)):
        return value.isoformat() if isinstance(value, (date, datetime)) else str(value)
    if isinstance(value, float):
        raise AccountingJobError("Accounting job returned an unsupported numeric result.")
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _json(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json(item) for item in value]
    raise AccountingJobError("Accounting job returned an unsupported result.")


def _context(job: AsyncJob) -> TaskContext:
    return TaskContext(
        correlation_id=_uuid(job.correlation_id, "correlation_id"),
        tenant_id=_uuid(job.tenant_id, "tenant_id"),
        actor_id=str(job.actor_id),
        causation_id=str(job.id),
        job_id=str(job.id),
    )


def _log(job: AsyncJob, *, outcome: str, started: float, error_code: str = "") -> None:
    logger.info(
        "Accounting durable command completed",
        extra={
            "event": "accounting.job.execute",
            "correlation_id": str(job.correlation_id),
            "tenant_id": str(job.tenant_id),
            "actor_id": str(job.actor_id),
            "resource_type": "async_job",
            "resource_id": str(job.id),
            "operation": str(job.command),
            "outcome": outcome,
            "error_code": error_code,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "job_id": str(job.id),
            "causation_id": str(job.id),
        },
    )


def journal_import_handler(job: AsyncJob) -> dict[str, object]:
    """Execute a file import through a real storage-aware service capability.

    ``file_reference`` is deliberately an opaque safe token.  Paths, URLs, and
    credentials are never persisted in the shared job table.  Deployments that
    have not configured a storage/import service fail explicitly.
    """

    started = time.monotonic()
    values = _payload(job, allowed=frozenset({"file_reference"}), required=frozenset({"file_reference"}))
    file_reference = _opaque_reference(values["file_reference"])
    tenant = _uuid(job.tenant_id, "tenant_id")
    from .services import JournalEntryService

    executor = getattr(JournalEntryService, "execute_batch_import", None)
    if not callable(executor):
        _log(job, outcome="failed", started=started, error_code=AccountingJobCapabilityUnavailable.code)
        raise AccountingJobCapabilityUnavailable("Journal import storage capability is unavailable.")

    with tenant_context(tenant), bind_task_context(_context(job)):
        result = executor(
            tenant,
            actor_id=str(job.actor_id),
            file_reference=file_reference,
            job_id=job.id,
            idempotency_key=str(job.id),
        )
    serialized = _json(result)
    if not isinstance(serialized, Mapping):
        raise AccountingJobError("Journal import returned an invalid result.")
    _log(job, outcome="succeeded", started=started)
    return dict(serialized)


def report_generate_handler(job: AsyncJob) -> dict[str, object]:
    """Generate one declared financial projection in the job's tenant."""

    started = time.monotonic()
    values = _payload(
        job,
        allowed=frozenset({"report_type", "parameters"}),
        required=frozenset({"report_type", "parameters"}),
    )
    report_type = str(values["report_type"])
    if report_type not in _REPORT_TYPES:
        raise AccountingJobPayloadError("report_type is unsupported.")
    raw_parameters = values["parameters"]
    if not isinstance(raw_parameters, Mapping):
        raise AccountingJobPayloadError("parameters must be an object.")
    parameters = {str(key): value for key, value in raw_parameters.items()}
    if set(parameters) != set(_REPORT_PARAMETER_KEYS[report_type]):
        raise AccountingJobPayloadError("Report parameters do not match the selected report.")
    parsed: dict[str, object] = {}
    for key, value in parameters.items():
        parsed[key] = _uuid(value, key) if key == "account_id" else _date(value, key)

    from .services import FinancialReportingService

    reporter = getattr(FinancialReportingService, report_type, None)
    if not callable(reporter):
        raise AccountingJobCapabilityUnavailable("Financial report capability is unavailable.")
    tenant = _uuid(job.tenant_id, "tenant_id")
    with tenant_context(tenant), bind_task_context(_context(job)):
        report = reporter(tenant, **parsed)
    result = {
        "schema_version": "1.0",
        "report_type": report_type,
        "report": _json(report),
        "correlation_id": str(job.correlation_id),
    }
    _log(job, outcome="succeeded", started=started)
    return result


def ar_mark_overdue_handler(job: AsyncJob) -> dict[str, object]:
    """Apply overdue transitions using the authoritative AR service."""

    started = time.monotonic()
    values = _payload(job, allowed=frozenset({"as_of_date"}), required=frozenset({"as_of_date"}))
    as_of_date = _date(values["as_of_date"], "as_of_date")
    tenant = _uuid(job.tenant_id, "tenant_id")
    from .services import ARInvoiceService

    with tenant_context(tenant), bind_task_context(_context(job)):
        transitioned = ARInvoiceService.mark_overdue(
            tenant,
            as_of_date=as_of_date,
            actor_id=str(job.actor_id),
        )
    if isinstance(transitioned, bool) or not isinstance(transitioned, int) or transitioned < 0:
        raise AccountingJobError("Overdue transition returned an invalid result.")
    _log(job, outcome="succeeded", started=started)
    return {"schema_version": "1.0", "transitioned": transitioned, "as_of_date": as_of_date.isoformat()}


def register_handlers() -> None:
    """Register each accounting command without replacing another module."""

    for command, handler in (
        (JOURNAL_IMPORT_COMMAND, journal_import_handler),
        (REPORT_GENERATE_COMMAND, report_generate_handler),
        (AR_MARK_OVERDUE_COMMAND, ar_mark_overdue_handler),
    ):
        try:
            register_handler(command, handler)
        except HandlerAlreadyRegistered:
            if get_handler(command) is not handler:
                raise


def handlers_ready() -> bool:
    """Return true only when all exact accounting handlers are installed."""

    expected = {
        JOURNAL_IMPORT_COMMAND: journal_import_handler,
        REPORT_GENERATE_COMMAND: report_generate_handler,
        AR_MARK_OVERDUE_COMMAND: ar_mark_overdue_handler,
    }
    try:
        return all(get_handler(command) is handler for command, handler in expected.items())
    except Exception:
        return False


register_handlers()


__all__ = [
    "AR_MARK_OVERDUE_COMMAND",
    "AccountingJobCapabilityUnavailable",
    "AccountingJobError",
    "AccountingJobPayloadError",
    "JOURNAL_IMPORT_COMMAND",
    "REGISTERED_COMMANDS",
    "REPORT_GENERATE_COMMAND",
    "ar_mark_overdue_handler",
    "handlers_ready",
    "journal_import_handler",
    "register_handlers",
    "report_generate_handler",
]
