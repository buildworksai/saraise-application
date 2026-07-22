"""Sanitized liveness and tenant-aware readiness for compliance risk."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID

from django.db import connection, transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone

from src.core.health import HealthCheckResult, health_registry
from src.core.tenancy import get_current_tenant_id

from .integrations import DEPENDENCIES, DependencyHealth, get_integration_registry

T = TypeVar("T")
PROBE_TIMEOUT_SECONDS = 2.0
ASYNC_TABLES = frozenset({"async_jobs", "async_job_outbox_events", "async_job_transitions"})


@dataclass(frozen=True, slots=True)
class ModuleHealthReport:
    status: str
    components: Mapping[str, Mapping[str, object]]

    @property
    def status_code(self) -> int:
        return 503 if self.status == "unavailable" else 200

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "module": "compliance_risk_management",
            "live": True,
            "ready": self.status != "unavailable",
            "checked_at": timezone.now().isoformat(),
            "components": dict(self.components),
        }


def _domain_tables() -> tuple[str, ...]:
    from .models import (
        ComplianceCalendarEntry,
        ComplianceRequirement,
        Control,
        ControlTest,
        RemediationAction,
        RiskAssessment,
        RiskConfiguration,
        RiskConfigurationVersion,
    )

    return tuple(
        model._meta.db_table
        for model in (
            RiskAssessment,
            Control,
            ControlTest,
            ComplianceRequirement,
            ComplianceCalendarEntry,
            RemediationAction,
            RiskConfiguration,
            RiskConfigurationVersion,
        )
    )


def _bounded_call(operation: Callable[[], T], timeout_seconds: float = PROBE_TIMEOUT_SECONDS) -> tuple[bool, T | None]:
    """Run a dependency probe without allowing it to wedge readiness."""

    results: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            results.put_nowait((True, operation()))
        except Exception:
            results.put_nowait((False, None))

    worker = threading.Thread(target=invoke, name="compliance-risk-health", daemon=True)
    worker.start()
    try:
        success, result = results.get(timeout=timeout_seconds)
    except queue.Empty:
        return False, None
    return success, result if success else None  # type: ignore[return-value]


def liveness_probe() -> HealthCheckResult:
    """Liveness intentionally checks process responsiveness only."""

    return HealthCheckResult(True, "live", timezone.now(), {"code": "live"})


def database_rls_probe(tenant_id: UUID | str | None = None) -> HealthCheckResult:
    """Validate schema, a bounded query, and forced PostgreSQL RLS metadata."""

    now = timezone.now()
    try:
        expected_tables = set(_domain_tables())
        actual_tables = set(connection.introspection.table_names())
        if not expected_tables.issubset(actual_tables):
            return HealthCheckResult(False, "schema_unavailable", now, {"code": "schema_missing"})
        with transaction.atomic():
            with connection.cursor() as cursor:
                if connection.vendor == "postgresql":
                    cursor.execute("SET LOCAL statement_timeout = %s", [int(PROBE_TIMEOUT_SECONDS * 1000)])
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    return HealthCheckResult(False, "database_unavailable", now, {"code": "query_failed"})
                if connection.vendor == "postgresql":
                    cursor.execute(
                        """
                        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                               EXISTS (
                                   SELECT 1 FROM pg_policies p
                                   WHERE p.schemaname = current_schema() AND p.tablename = c.relname
                               )
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = current_schema() AND c.relname = ANY(%s)
                        """,
                        [list(expected_tables)],
                    )
                    rows = cursor.fetchall()
                    secured = {name for name, enabled, forced, policy in rows if enabled and forced and policy}
                    if secured != expected_tables:
                        return HealthCheckResult(False, "rls_unavailable", now, {"code": "rls_missing"})
        if connection.vendor == "postgresql" and tenant_id is not None:
            try:
                expected_tenant = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
            except (TypeError, ValueError, AttributeError):
                return HealthCheckResult(False, "tenant_context_unavailable", now, {"code": "tenant_invalid"})
            if get_current_tenant_id() != expected_tenant:
                return HealthCheckResult(False, "tenant_context_unavailable", now, {"code": "tenant_context_missing"})
        return HealthCheckResult(True, "ready", now, {"code": "ready"})
    except Exception:
        return HealthCheckResult(False, "database_unavailable", now, {"code": "dependency_unavailable"})


def outbox_probe() -> HealthCheckResult:
    """Verify durable job/outbox schema and queryability without exposing rows."""

    now = timezone.now()
    try:
        tables = set(connection.introspection.table_names())
        if not ASYNC_TABLES.issubset(tables):
            return HealthCheckResult(False, "outbox_unavailable", now, {"code": "schema_missing"})
        with transaction.atomic():
            with connection.cursor() as cursor:
                if connection.vendor == "postgresql":
                    cursor.execute("SET LOCAL statement_timeout = %s", [int(PROBE_TIMEOUT_SECONDS * 1000)])
                cursor.execute("SELECT 1 FROM async_job_outbox_events LIMIT 1")
                cursor.fetchone()
        return HealthCheckResult(True, "ready", now, {"code": "ready"})
    except Exception:
        return HealthCheckResult(False, "outbox_unavailable", now, {"code": "dependency_unavailable"})


def integration_probes() -> dict[str, DependencyHealth]:
    """Probe optional adapters concurrently under one bounded readiness window."""

    registry = get_integration_registry()
    results: dict[str, DependencyHealth] = {}
    lock = threading.Lock()
    threads: list[threading.Thread] = []

    def probe(name: str) -> None:
        success, result = _bounded_call(lambda: registry.get(name).health())
        health = (
            result
            if success and isinstance(result, DependencyHealth)
            else DependencyHealth(name, False, "probe_timed_out", "unknown", timezone.now(), True)
        )
        with lock:
            results[name] = health

    deadline = time.monotonic() + PROBE_TIMEOUT_SECONDS
    for dependency in DEPENDENCIES:
        thread = threading.Thread(target=probe, args=(dependency,), name=f"compliance-risk-{dependency}", daemon=True)
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))
    for dependency in DEPENDENCIES:
        results.setdefault(
            dependency,
            DependencyHealth(dependency, False, "probe_timed_out", "unknown", timezone.now(), True),
        )
    return results


def get_module_health(tenant_id: UUID | str | None = None) -> ModuleHealthReport:
    """Return required failures as unavailable and optional failures as degraded."""

    database = database_rls_probe(tenant_id)
    outbox = outbox_probe()
    integrations = integration_probes()
    required_ready = database.healthy and outbox.healthy
    optional_ready = all(result.available for result in integrations.values())
    status = "healthy" if required_ready and optional_ready else "degraded" if required_ready else "unavailable"
    components: dict[str, Mapping[str, object]] = {
        "database_rls": {
            "status": "healthy" if database.healthy else "unavailable",
            "code": str(database.details.get("code", "unknown")),
            "required": True,
        },
        "async_outbox": {
            "status": "healthy" if outbox.healthy else "unavailable",
            "code": str(outbox.details.get("code", "unknown")),
            "required": True,
        },
    }
    components.update(
        {
            name: {
                "status": "healthy" if result.available else "degraded",
                "code": result.code,
                "required": False,
                "configured": result.configured,
                "circuit_state": result.circuit_state,
            }
            for name, result in integrations.items()
        }
    )
    return ModuleHealthReport(status, components)


def register_health_probes() -> None:
    """Expose module-owned required probes to application readiness."""

    health_registry.register(
        "compliance_risk_management.database_rls",
        database_rls_probe,
        critical=True,
        replace=True,
    )
    health_registry.register(
        "compliance_risk_management.async_outbox",
        outbox_probe,
        critical=True,
        replace=True,
    )


def live_health(request: HttpRequest) -> JsonResponse:
    """Process-only view helper; API routing must apply authentication/access."""

    del request
    return JsonResponse(
        {
            "status": "healthy",
            "module": "compliance_risk_management",
            "live": True,
            "checked_at": timezone.now().isoformat(),
        }
    )


def ready_health(request: HttpRequest) -> JsonResponse:
    """Tenant-aware view helper with a sanitized readiness document."""

    report = get_module_health(getattr(request, "tenant_id", None))
    return JsonResponse(report.as_dict(), status=report.status_code)


# Compatibility name for code importing the former single endpoint.  New URL
# declarations must mount live_health and ready_health separately.
health_check = ready_health

__all__ = [
    "ModuleHealthReport",
    "database_rls_probe",
    "get_module_health",
    "health_check",
    "integration_probes",
    "live_health",
    "liveness_probe",
    "outbox_probe",
    "ready_health",
    "register_health_probes",
]
