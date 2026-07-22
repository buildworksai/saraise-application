"""Sanitized readiness probes for the workflow automation runtime."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from django.db import connection
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent, OutboxStatus
from src.core.async_jobs.services import HandlerNotRegistered, get_handler
from src.core.health import HealthCheckResult, health_registry
from src.core.tenancy import get_current_tenant_id

from .extensions import action_registry
from .models import Workflow, WorkflowStep
from .services import EXECUTE_INSTANCE_COMMAND, EXPIRE_TASKS_COMMAND, _handler_key_for_step

MODULE_HEALTH_NAME = "workflow_automation.readiness"
REQUIRED_COMMANDS = (EXECUTE_INSTANCE_COMMAND, EXPIRE_TASKS_COMMAND)


def _database_ready(tenant_id: uuid.UUID | None) -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                return False
            if connection.vendor == "postgresql" and tenant_id is not None:
                cursor.execute("SELECT current_setting('app.tenant_id', true)")
                row = cursor.fetchone()
                return bool(row and row[0] and str(row[0]) == str(tenant_id))
        return connection.vendor != "postgresql" or tenant_id is None
    except Exception:
        return False


def _handlers_registered() -> bool:
    try:
        for command in REQUIRED_COMMANDS:
            get_handler(command)
        return True
    except HandlerNotRegistered:
        return False


def _outbox_fresh(tenant_id: uuid.UUID | None) -> bool:
    if tenant_id is None:
        # Global core readiness has no lawful tenant scope. Per-request module
        # readiness performs the operational outbox check under RLS context.
        return True
    threshold = timezone.now() - timedelta(minutes=5)
    try:
        return not OutboxEvent.objects.for_tenant(tenant_id).filter(
            status=OutboxStatus.PENDING,
            created_at__lt=threshold,
        ).exists()
    except Exception:
        return False


def _required_extensions_ready(tenant_id: uuid.UUID | None) -> bool:
    try:
        baseline = action_registry.get("core.in_app_notification.v1")
        if not baseline.health().healthy:
            return False
        if tenant_id is None:
            return True
        workflow_ids = Workflow.objects.for_tenant(tenant_id).filter(
            status="published",
            deleted_at__isnull=True,
        ).values_list("id", flat=True)
        for step in WorkflowStep.objects.for_tenant(tenant_id).filter(
            workflow_id__in=workflow_ids,
            step_type__in=("action", "notification"),
        ):
            handler_key, _ = _handler_key_for_step(step)
            handler = action_registry.get(handler_key)
            descriptor = handler.descriptor
            if step.handler_contract_version != descriptor.contract_version:
                return False
            if step.handler_contract_fingerprint != descriptor.contract_fingerprint:
                return False
            if not handler.health().healthy:
                return False
        return True
    except Exception:
        return False


def module_readiness(tenant_id: uuid.UUID | str | None = None) -> HealthCheckResult:
    """Evaluate readiness without row counts, tenant identifiers, or errors."""

    if tenant_id is None:
        tenant_uuid = get_current_tenant_id()
    else:
        try:
            tenant_uuid = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
        except (TypeError, ValueError):
            tenant_uuid = None
    checks = {
        "database_rls": _database_ready(tenant_uuid),
        "async_handlers": _handlers_registered(),
        "outbox_worker": _outbox_fresh(tenant_uuid),
        "notifications": _required_extensions_ready(tenant_uuid),
        "required_extensions": _required_extensions_ready(tenant_uuid),
    }
    healthy = all(checks.values())
    return HealthCheckResult(
        healthy=healthy,
        message="workflow runtime ready" if healthy else "one or more required capabilities are unavailable",
        details={name: "ok" if ready else "unavailable" for name, ready in checks.items()},
    )


def sanitized_health_payload(tenant_id: uuid.UUID | str | None = None) -> tuple[dict[str, Any], int]:
    result = module_readiness(tenant_id)
    return (
        {
            "status": "ready" if result.healthy else "not_ready",
            "checks": dict(result.details),
        },
        200 if result.healthy else 503,
    )


def register_module_health() -> None:
    """Register the critical module probe idempotently for Django reload."""

    health_registry.register(
        MODULE_HEALTH_NAME,
        module_readiness,
        critical=True,
        staleness_limit=30,
        replace=True,
    )


__all__ = [
    "MODULE_HEALTH_NAME",
    "module_readiness",
    "register_module_health",
    "sanitized_health_payload",
]
