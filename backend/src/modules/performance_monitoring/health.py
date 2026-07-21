"""Non-sensitive readiness probes for monitoring dependencies."""

from __future__ import annotations

from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes, renderer_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.access import RequiresAccess
from src.core.api import SuccessEnvelopeRenderer
from src.core.async_jobs.services import get_handler
from src.core.health import HealthCheckResult, health_registry

from .api import CsrfSessionAuthentication


def database_probe() -> HealthCheckResult:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return HealthCheckResult(True, "ready", timezone.now(), {"code": "ready"})
    except Exception:
        return HealthCheckResult(False, "database_unavailable", timezone.now(), {"code": "database_unavailable"})


def cache_probe() -> HealthCheckResult:
    key = "performance-monitoring:readiness"
    try:
        cache.set(key, "ready", timeout=10)
        healthy = cache.get(key) == "ready"
        return HealthCheckResult(
            healthy,
            "ready" if healthy else "cache_unavailable",
            timezone.now(),
            {"code": "ready" if healthy else "cache_unavailable"},
        )
    except Exception:
        return HealthCheckResult(False, "cache_unavailable", timezone.now(), {"code": "cache_unavailable"})


def async_probe() -> HealthCheckResult:
    try:
        for command in (
            "performance_monitoring.evaluate_alerts",
            "performance_monitoring.snapshot_sla",
            "performance_monitoring.enforce_retention",
        ):
            get_handler(command)
        return HealthCheckResult(True, "ready", timezone.now(), {"code": "ready"})
    except Exception:
        return HealthCheckResult(False, "async_unavailable", timezone.now(), {"code": "handlers_unavailable"})


def notifications_probe() -> HealthCheckResult:
    try:
        from src.core.notifications.services import NotificationService

        healthy = callable(NotificationService.create_notification)
        return HealthCheckResult(
            healthy,
            "ready" if healthy else "notification_unavailable",
            timezone.now(),
            {"code": "ready" if healthy else "contract_unavailable"},
        )
    except Exception:
        return HealthCheckResult(False, "notification_unavailable", timezone.now(), {"code": "contract_unavailable"})


def register_health_probes() -> None:
    health_registry.register("performance_monitoring.database", database_probe, critical=True, replace=True)
    health_registry.register("performance_monitoring.cache", cache_probe, critical=False, replace=True)
    health_registry.register("performance_monitoring.async", async_probe, critical=True, replace=True)
    health_registry.register("performance_monitoring.notifications", notifications_probe, critical=True, replace=True)


def _health_response() -> Response:
    checks = {
        "database": database_probe(),
        "cache": cache_probe(),
        "async": async_probe(),
        "notifications": notifications_probe(),
    }
    ready = checks["database"].healthy and checks["async"].healthy and checks["notifications"].healthy
    degraded = ready and not checks["cache"].healthy
    payload = {
        "module": "performance-monitoring",
        "status": "degraded" if degraded else "healthy" if ready else "unavailable",
        "ready": ready,
        "checks": {
            name: {"status": "healthy" if result.healthy else "unavailable", "code": result.details["code"]}
            for name, result in checks.items()
        },
    }
    return Response(payload, status=200 if ready else 503)


@api_view(("GET",))
@authentication_classes((CsrfSessionAuthentication,))
@permission_classes((IsAuthenticated, RequiresAccess("performance_monitoring.health:read")))
def health_check(request) -> Response:
    del request
    return _health_response()


@api_view(("GET",))
@authentication_classes((CsrfSessionAuthentication,))
@permission_classes((IsAuthenticated, RequiresAccess("performance_monitoring.health:read")))
@renderer_classes((SuccessEnvelopeRenderer,))
def governed_health_check(request) -> Response:
    del request
    return _health_response()


__all__ = [
    "async_probe",
    "cache_probe",
    "database_probe",
    "governed_health_check",
    "health_check",
    "notifications_probe",
    "register_health_probes",
]
