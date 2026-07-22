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


def cache_probe(*, timeout_seconds: int | None = None) -> HealthCheckResult:
    if timeout_seconds is None or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
        return HealthCheckResult(False, "cache_policy_unavailable", timezone.now(), {"code": "policy_unavailable"})
    key = "performance-monitoring:readiness"
    try:
        cache.set(key, "ready", timeout=timeout_seconds)
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
            "performance_monitoring.deliver_alert_notification",
            "performance_monitoring.consume.request_completed",
            "performance_monitoring.consume.error_occurred",
            "performance_monitoring.consume.job_completed",
        ):
            get_handler(command)
        return HealthCheckResult(True, "ready", timezone.now(), {"code": "ready"})
    except Exception:
        return HealthCheckResult(False, "async_unavailable", timezone.now(), {"code": "handlers_unavailable"})


def notifications_probe() -> HealthCheckResult:
    """Use the dependency's explicit non-mutating readiness contract.

    Importing a service or finding a callable proves nothing about its backing
    persistence and delivery dependencies. An absent, malformed, or
    inconclusive contract therefore fails closed.
    """

    try:
        from src.core.notifications.services import NotificationService

        readiness_probe = getattr(NotificationService, "readiness_probe", None)
        if not callable(readiness_probe):
            return HealthCheckResult(
                False,
                "notification_unavailable",
                timezone.now(),
                {"code": "readiness_contract_unavailable"},
            )
        result = readiness_probe()
        healthy = getattr(result, "healthy", None)
        if healthy is not True:
            code = "dependency_unavailable" if healthy is False else "readiness_inconclusive"
            return HealthCheckResult(False, "notification_unavailable", timezone.now(), {"code": code})
        return HealthCheckResult(
            True,
            "ready",
            timezone.now(),
            {"code": "ready"},
        )
    except Exception:
        return HealthCheckResult(False, "notification_unavailable", timezone.now(), {"code": "dependency_unavailable"})


def register_health_probes() -> None:
    health_registry.register("performance_monitoring.database", database_probe, critical=True, replace=True)
    health_registry.register("performance_monitoring.async", async_probe, critical=True, replace=True)
    health_registry.register("performance_monitoring.notifications", notifications_probe, critical=True, replace=True)


def _health_response(tenant_id: object) -> Response:
    from .services import ConfigurationService

    try:
        document = ConfigurationService().effective_document(tenant_id, environment="default")
        health_policy = document["health"]
        timeout_seconds = health_policy["cache_probe_timeout_seconds"]
        critical_dependencies = frozenset(health_policy["critical_dependencies"])
    except Exception:
        return Response(
            {
                "module": "performance-monitoring",
                "status": "unavailable",
                "ready": False,
                "checks": {"configuration": {"status": "unavailable", "code": "policy_unavailable"}},
            },
            status=503,
        )
    checks = {
        "database": database_probe(),
        "cache": cache_probe(timeout_seconds=timeout_seconds),
        "async": async_probe(),
        "notifications": notifications_probe(),
    }
    ready = all(checks[name].healthy for name in critical_dependencies)
    degraded = ready and any(not result.healthy for name, result in checks.items() if name not in critical_dependencies)
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
    profile = getattr(request.user, "profile", None)
    tenant_id = getattr(request, "tenant_id", None) or getattr(profile, "tenant_id", None)
    return _health_response(tenant_id)


@api_view(("GET",))
@authentication_classes((CsrfSessionAuthentication,))
@permission_classes((IsAuthenticated, RequiresAccess("performance_monitoring.health:read")))
@renderer_classes((SuccessEnvelopeRenderer,))
def governed_health_check(request) -> Response:
    profile = getattr(request.user, "profile", None)
    tenant_id = getattr(request, "tenant_id", None) or getattr(profile, "tenant_id", None)
    return _health_response(tenant_id)


__all__ = [
    "async_probe",
    "cache_probe",
    "database_probe",
    "governed_health_check",
    "health_check",
    "notifications_probe",
    "register_health_probes",
]
