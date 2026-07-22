"""Durable async command handlers for bounded metadata operations."""

from __future__ import annotations

import uuid

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import register_handler
from src.core.tenancy import tenant_context_worker

from .services import EntityDefinitionService, SchemaVersionService


@tenant_context_worker
def validate_schema(
    tenant_id: uuid.UUID,
    definition_id: uuid.UUID,
    version_id: uuid.UUID,
    *,
    sample_limit: int,
) -> dict[str, object]:
    return SchemaVersionService.validate_candidate(
        tenant_id, definition_id, version_id, sample_limit=sample_limit
    )


@tenant_context_worker
def export_schema(tenant_id: uuid.UUID, definition_id: uuid.UUID) -> dict[str, object]:
    return EntityDefinitionService.export_definition(tenant_id, definition_id)


@tenant_context_worker
def revalidate_resources(
    tenant_id: uuid.UUID,
    definition_id: uuid.UUID,
    version_id: uuid.UUID,
    *,
    sample_limit: int,
) -> dict[str, object]:
    # Candidate impact validation is the authoritative bulk revalidation path.
    return SchemaVersionService.validate_candidate(
        tenant_id, definition_id, version_id, sample_limit=sample_limit
    )


def _validate_job(job: AsyncJob) -> dict[str, object]:
    return validate_schema(
        tenant_id=job.tenant_id,
        definition_id=uuid.UUID(str(job.payload["definition_id"])),
        version_id=uuid.UUID(str(job.payload["version_id"])),
        sample_limit=int(job.payload["sample_limit"]),
    )


def _export_job(job: AsyncJob) -> dict[str, object]:
    return export_schema(
        tenant_id=job.tenant_id,
        definition_id=uuid.UUID(str(job.payload["definition_id"])),
    )


def _revalidate_job(job: AsyncJob) -> dict[str, object]:
    return revalidate_resources(
        tenant_id=job.tenant_id,
        definition_id=uuid.UUID(str(job.payload["definition_id"])),
        version_id=uuid.UUID(str(job.payload["version_id"])),
        sample_limit=int(job.payload["sample_limit"]),
    )


def register_handlers() -> None:
    """Idempotently install handlers at Django startup."""
    from src.core.async_jobs.services import HandlerAlreadyRegistered

    for command, handler in (
        ("metadata_modeling.validate_schema", _validate_job),
        ("metadata_modeling.export_schema", _export_job),
        ("metadata_modeling.revalidate_resources", _revalidate_job),
    ):
        try:
            register_handler(command, handler)
        except HandlerAlreadyRegistered:
            continue


__all__ = ["export_schema", "register_handlers", "revalidate_resources", "validate_schema"]
