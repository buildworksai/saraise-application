"""Tenant-first durable async handlers for imports and candidate generation."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import register_handler
from src.core.tenancy import tenant_context_worker


def _uuid_payload(payload: Mapping[str, object], key: str) -> UUID:
    try:
        return UUID(str(payload[key]))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"durable job payload requires UUID field {key!r}") from exc


def _text_payload(payload: Mapping[str, object], key: str, *, maximum: int = 255) -> str:
    value = str(payload.get(key, "")).strip()
    if not value or len(value) > maximum:
        raise ValueError(f"durable job payload requires bounded text field {key!r}")
    return value


@tenant_context_worker
def import_statement_task(*, tenant_id: UUID, import_id: UUID, async_job_id: UUID) -> dict[str, str]:
    """Execute one persisted import; bytes are resolved by the import service."""
    from .services import StatementImportService

    statement = StatementImportService().execute_import(tenant_id, import_id)
    return {"import_id": str(import_id), "statement_id": str(statement.id), "status": str(statement.status)}


@tenant_context_worker
def generate_candidates_task(
    *,
    tenant_id: UUID,
    reconciliation_id: UUID,
    actor_id: UUID,
    idempotency_key: str,
    async_job_id: UUID,
) -> dict[str, object]:
    """Run bounded deterministic generation through the reconciliation service."""
    del async_job_id
    from .services import ReconciliationService

    result = ReconciliationService().generate_candidates(
        tenant_id,
        reconciliation_id,
        actor_id,
        idempotency_key,
    )
    count = getattr(result, "proposal_count", getattr(result, "count", None))
    if count is None and hasattr(result, "proposals"):
        count = len(result.proposals)
    if count is None:
        try:
            count = len(result)
        except TypeError as exc:
            raise ValueError("candidate service returned no measurable proposal count") from exc
    return {"reconciliation_id": str(reconciliation_id), "proposal_count": int(count)}


@register_handler("bank_reconciliation.import_statement")
def _import_handler(job: AsyncJob) -> dict[str, str]:
    return import_statement_task(
        tenant_id=job.tenant_id,
        import_id=_uuid_payload(job.payload, "import_id"),
        async_job_id=job.id,
    )


@register_handler("bank_reconciliation.generate_candidates")
def _candidate_handler(job: AsyncJob) -> dict[str, object]:
    actor_value = job.payload.get("actor_id", job.actor_id)
    try:
        actor_id = UUID(str(actor_value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("durable candidate job requires a UUID actor_id") from exc
    return generate_candidates_task(
        tenant_id=job.tenant_id,
        reconciliation_id=_uuid_payload(job.payload, "reconciliation_id"),
        actor_id=actor_id,
        idempotency_key=_text_payload(job.payload, "idempotency_key", maximum=128),
        async_job_id=job.id,
    )


__all__ = ["generate_candidates_task", "import_statement_task"]
