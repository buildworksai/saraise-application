"""Sanitized readiness for the durable orchestration runtime."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent, OutboxStatus
from src.core.async_jobs.services import HandlerNotRegistered, get_handler
from src.core.health import HealthCheckResult, health_registry

from .workflow_adapter import workflow_adapter_available

MODULE_HEALTH_NAME = "automation_orchestration.readiness"
SCHEDULE_SCANNER_HEARTBEAT_KEY = "automation_orchestration:schedule-scanner:last-seen"
REQUIRED_COMMANDS = (
    "automation_orchestration.execute_run",
    "automation_orchestration.execute_task",
    "automation_orchestration.scan_schedules",
)


def mark_schedule_scanner_healthy() -> None:
    """Record a short-lived scanner heartbeat without storing tenant data."""

    cache.set(SCHEDULE_SCANNER_HEARTBEAT_KEY, timezone.now().isoformat(), timeout=180)


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


def _outbox_fresh() -> bool:
    """Fail when undelivered work has exceeded the operational SLO."""

    threshold = timezone.now() - timedelta(minutes=5)
    try:
        return not OutboxEvent.objects.filter(status=OutboxStatus.PENDING, created_at__lt=threshold).exists()
    except Exception:
        return False


def _scanner_fresh() -> bool:
    raw = cache.get(SCHEDULE_SCANNER_HEARTBEAT_KEY)
    if not isinstance(raw, str):
        return False
    try:
        seen = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if timezone.is_naive(seen):
        seen = timezone.make_aware(seen)
    return timezone.now() - seen <= timedelta(minutes=2)


def module_readiness(*, require_scanner_heartbeat: bool = True) -> HealthCheckResult:
    """Check dependencies and return only non-sensitive component states."""

    checks = {
        "database": _database_ready(),
        "outbox": _outbox_fresh(),
        "async_handlers": _handlers_ready(),
        "schedule_scanner": _scanner_fresh() if require_scanner_heartbeat else _handlers_ready(),
        "workflow_adapter": workflow_adapter_available(),
    }
    healthy = all(checks.values())
    return HealthCheckResult(
        healthy=healthy,
        message="orchestration runtime ready" if healthy else "one or more required dependencies are unavailable",
        details={name: "ok" if state else "unavailable" for name, state in checks.items()},
    )


def sanitized_health_payload(*, require_scanner_heartbeat: bool = True) -> tuple[dict[str, object], int]:
    result = module_readiness(require_scanner_heartbeat=require_scanner_heartbeat)
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
        staleness_limit=30,
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
