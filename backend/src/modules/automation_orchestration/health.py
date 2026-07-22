"""Sanitized readiness for the durable orchestration runtime."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent, OutboxStatus
from src.core.async_jobs.services import HandlerNotRegistered, get_handler
from src.core.health import HealthCheckResult, health_registry
from src.core.tenancy.rls import get_current_tenant_id

from .services import DEFAULT_CONFIGURATION, ConfigurationService
from .workflow_adapter import workflow_adapter_available

MODULE_HEALTH_NAME = "automation_orchestration.readiness"
SCHEDULE_SCANNER_HEARTBEAT_KEY = "automation_orchestration:schedule-scanner:last-seen"
REQUIRED_COMMANDS = (
    "automation_orchestration.execute_run",
    "automation_orchestration.execute_task",
    "automation_orchestration.scan_schedules",
)


def _heartbeat_key(tenant_id: uuid.UUID | None) -> str:
    return f"{SCHEDULE_SCANNER_HEARTBEAT_KEY}:{tenant_id}" if tenant_id else SCHEDULE_SCANNER_HEARTBEAT_KEY


def _health_policy(tenant_id: uuid.UUID | None) -> dict[str, int]:
    if tenant_id is None:
        return dict(DEFAULT_CONFIGURATION["health"])
    return dict(ConfigurationService.effective_document(tenant_id)["health"])


def mark_schedule_scanner_healthy(tenant_id: uuid.UUID | None = None) -> None:
    """Record a short-lived scanner heartbeat without storing tenant data."""

    tenant_id = tenant_id or get_current_tenant_id()
    policy = _health_policy(tenant_id)
    cache.set(
        _heartbeat_key(tenant_id),
        timezone.now().isoformat(),
        timeout=policy["scanner_heartbeat_ttl_seconds"],
    )


def _database_ready() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)
    except Exception:
        return False


def _handlers_ready() -> bool:
    try:
        for command in REQUIRED_COMMANDS:
            get_handler(command)
        return True
    except HandlerNotRegistered:
        return False


def _outbox_fresh(policy: dict[str, int]) -> bool:
    """Fail when undelivered work has exceeded the operational SLO."""

    threshold = timezone.now() - timedelta(seconds=policy["pending_outbox_freshness_seconds"])
    try:
        return not OutboxEvent.objects.filter(status=OutboxStatus.PENDING, created_at__lt=threshold).exists()
    except Exception:
        return False


def _scanner_fresh(tenant_id: uuid.UUID | None, policy: dict[str, int]) -> bool:
    raw = cache.get(_heartbeat_key(tenant_id))
    if not isinstance(raw, str):
        return False
    try:
        seen = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if timezone.is_naive(seen):
        seen = timezone.make_aware(seen)
    return timezone.now() - seen <= timedelta(seconds=policy["scanner_freshness_seconds"])


def module_readiness(
    *, tenant_id: uuid.UUID | None = None, require_scanner_heartbeat: bool = True
) -> HealthCheckResult:
    """Check dependencies and return only non-sensitive component states."""

    policy = _health_policy(tenant_id)
    checks = {
        "database": _database_ready(),
        "outbox": _outbox_fresh(policy),
        "async_handlers": _handlers_ready(),
        "schedule_scanner": _scanner_fresh(tenant_id, policy) if require_scanner_heartbeat else _handlers_ready(),
        "workflow_adapter": workflow_adapter_available(),
    }
    healthy = all(checks.values())
    return HealthCheckResult(
        healthy=healthy,
        message="orchestration runtime ready" if healthy else "one or more required dependencies are unavailable",
        details={name: "ok" if state else "unavailable" for name, state in checks.items()},
    )


def sanitized_health_payload(
    *, tenant_id: uuid.UUID | None = None, require_scanner_heartbeat: bool = True
) -> tuple[dict[str, object], int]:
    result = module_readiness(tenant_id=tenant_id, require_scanner_heartbeat=require_scanner_heartbeat)
    return (
        {
            "status": "ready" if result.healthy else "not_ready",
            "checks": dict(result.details),
        },
        200 if result.healthy else 503,
    )


def register_module_health() -> None:
    health_registry.register(
        MODULE_HEALTH_NAME,
        module_readiness,
        critical=True,
        staleness_limit=DEFAULT_CONFIGURATION["health"]["registry_staleness_seconds"],
        replace=True,
    )


__all__ = [
    "MODULE_HEALTH_NAME",
    "REQUIRED_COMMANDS",
    "SCHEDULE_SCANNER_HEARTBEAT_KEY",
    "mark_schedule_scanner_healthy",
    "module_readiness",
    "register_module_health",
    "sanitized_health_payload",
]
