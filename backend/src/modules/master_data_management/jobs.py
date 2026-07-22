"""Durable worker handlers for MDM quality and duplicate scans."""

from __future__ import annotations

import logging
import time
from typing import Final
from uuid import UUID

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import HandlerAlreadyRegistered, register_handler
from src.core.observability import TaskContext, bind_task_context
from src.core.tenancy import tenant_context

from .services import (
    DEDUPLICATION_SCAN_COMMAND,
    QUALITY_SCAN_COMMAND,
    DataQualityService,
    MatchingService,
)

logger = logging.getLogger("saraise.master_data_management")
REGISTERED_COMMANDS: Final = (QUALITY_SCAN_COMMAND, DEDUPLICATION_SCAN_COMMAND)


def _uuid(value: object, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field} must be a valid UUID") from exc


def quality_scan_handler(job: AsyncJob) -> dict[str, object]:
    """Execute one persisted quality scan within its tenant boundary."""

    started = time.monotonic()
    tenant = _uuid(job.tenant_id, "tenant_id")
    actor = _uuid(job.actor_id, "actor_id")
    entity_type = _uuid(job.payload.get("entity_type_id"), "entity_type_id")
    context = TaskContext(
        correlation_id=_uuid(job.correlation_id, "correlation_id"),
        tenant_id=tenant,
        actor_id=str(actor),
        causation_id=str(job.id),
        job_id=str(job.id),
    )
    with tenant_context(tenant), bind_task_context(context):
        result = DataQualityService.execute_quality_scan(
            tenant,
            actor,
            entity_type_id=entity_type,
            job_id=job.id,
        )
    logger.info(
        "MDM quality scan completed",
        extra={
            "event": "mdm.job.quality_scan",
            "correlation_id": job.correlation_id,
            "tenant_id": str(tenant),
            "actor_id": str(actor),
            "resource_type": "async_job",
            "resource_id": str(job.id),
            "operation": QUALITY_SCAN_COMMAND,
            "outcome": "succeeded",
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "job_id": str(job.id),
        },
    )
    return result


def deduplication_scan_handler(job: AsyncJob) -> dict[str, object]:
    """Execute one persisted blocking-and-comparison scan."""

    started = time.monotonic()
    tenant = _uuid(job.tenant_id, "tenant_id")
    actor = _uuid(job.actor_id, "actor_id")
    entity_type = _uuid(job.payload.get("entity_type_id"), "entity_type_id")
    raw_rule_ids = job.payload.get("rule_ids")
    if not isinstance(raw_rule_ids, list) or not raw_rule_ids:
        raise ValueError("rule_ids must be a non-empty array")
    rule_ids = [_uuid(item, "rule_ids") for item in raw_rule_ids]
    context = TaskContext(
        correlation_id=_uuid(job.correlation_id, "correlation_id"),
        tenant_id=tenant,
        actor_id=str(actor),
        causation_id=str(job.id),
        job_id=str(job.id),
    )
    with tenant_context(tenant), bind_task_context(context):
        result = MatchingService.execute_deduplication_scan(
            tenant,
            actor,
            entity_type_id=entity_type,
            rule_ids=rule_ids,
            job_id=job.id,
        )
    logger.info(
        "MDM deduplication scan completed",
        extra={
            "event": "mdm.job.deduplication_scan",
            "correlation_id": job.correlation_id,
            "tenant_id": str(tenant),
            "actor_id": str(actor),
            "resource_type": "async_job",
            "resource_id": str(job.id),
            "operation": DEDUPLICATION_SCAN_COMMAND,
            "outcome": "succeeded",
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "job_id": str(job.id),
        },
    )
    return result


def register_handlers() -> None:
    """Register handlers explicitly; never silently replace paid handlers."""

    for command, handler in (
        (QUALITY_SCAN_COMMAND, quality_scan_handler),
        (DEDUPLICATION_SCAN_COMMAND, deduplication_scan_handler),
    ):
        try:
            register_handler(command, handler)
        except HandlerAlreadyRegistered:
            # Django's development autoreloader can import a module twice.  A
            # different registration still remains protected by the registry.
            from src.core.async_jobs.services import get_handler

            if get_handler(command) is not handler:
                raise


register_handlers()

__all__ = [
    "REGISTERED_COMMANDS",
    "deduplication_scan_handler",
    "quality_scan_handler",
    "register_handlers",
]
