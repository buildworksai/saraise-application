"""Sanitized database, RLS, storage, and outbox readiness for DMS."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Mapping

from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from src.core.async_jobs.models import OutboxEvent, OutboxStatus
from src.core.health import HealthCheckResult, health_registry

from .storage import StorageHealth, get_document_storage

DOMAIN_TABLES = (
    "dms_folders",
    "dms_documents",
    "dms_document_versions",
    "dms_document_permissions",
    "dms_document_shares",
)
OUTBOX_FRESHNESS = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class ModuleHealthReport:
    status: str
    payload: Mapping[str, object]

    @property
    def status_code(self) -> int:
        return 503 if self.status == "unhealthy" else 200


def _result(healthy: bool, message: str, code: str, *, latency_ms: float | None = None) -> HealthCheckResult:
    details: dict[str, object] = {"code": code}
    if latency_ms is not None:
        details["latency_ms"] = latency_ms
    return HealthCheckResult(healthy, message, timezone.now(), details)


def database_readiness_probe() -> HealthCheckResult:
    """Verify canonical tables plus enabled, forced, read/write RLS policies."""

    started = time.monotonic()
    try:
        tables = set(connection.introspection.table_names())
        if not set(DOMAIN_TABLES).issubset(tables):
            return _result(
                False,
                "domain_schema_unavailable",
                "schema_missing",
                latency_ms=round((time.monotonic() - started) * 1000, 3),
            )
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = current_schema() AND c.relname = ANY(%s)
                    """,
                    [list(DOMAIN_TABLES)],
                )
                protected = {row[0] for row in cursor.fetchall() if bool(row[1]) and bool(row[2])}
                cursor.execute(
                    """
                    SELECT tablename, bool_or(qual IS NOT NULL), bool_or(with_check IS NOT NULL)
                    FROM pg_policies
                    WHERE schemaname = current_schema() AND tablename = ANY(%s)
                    GROUP BY tablename
                    """,
                    [list(DOMAIN_TABLES)],
                )
                policy_protected = {row[0] for row in cursor.fetchall() if bool(row[1]) and bool(row[2])}
            expected = set(DOMAIN_TABLES)
            if protected != expected or policy_protected != expected:
                return _result(
                    False,
                    "rls_policy_unavailable",
                    "rls_missing",
                    latency_ms=round((time.monotonic() - started) * 1000, 3),
                )
        return _result(True, "ready", "ready", latency_ms=round((time.monotonic() - started) * 1000, 3))
    except Exception:
        return _result(
            False,
            "database_unavailable",
            "dependency_unavailable",
            latency_ms=round((time.monotonic() - started) * 1000, 3),
        )


def storage_readiness_probe() -> HealthCheckResult:
    """Perform a randomized save/open/read/delete roundtrip."""

    started = time.monotonic()
    try:
        storage: StorageHealth = get_document_storage().health_probe()
        if not isinstance(storage, StorageHealth):
            raise TypeError("storage adapter returned invalid health evidence")
    except Exception:
        return _result(
            False,
            "storage_unavailable",
            "dependency_unavailable",
            latency_ms=round((time.monotonic() - started) * 1000, 3),
        )
    if not storage.healthy:
        return _result(False, "storage_unavailable", storage.detail, latency_ms=storage.latency_ms)
    if not storage.cleanup_ok or storage.status == "degraded":
        return _result(True, "storage_cleanup_degraded", "cleanup_failed", latency_ms=storage.latency_ms)
    return _result(True, "ready", "ready", latency_ms=storage.latency_ms)


def outbox_readiness_probe() -> HealthCheckResult:
    """Detect stale pending DMS events without counting or exposing tenant data."""

    started = time.monotonic()
    if not bool(getattr(settings, "DMS_OUTBOX_ENABLED", True)):
        return _result(True, "disabled", "disabled", latency_ms=round((time.monotonic() - started) * 1000, 3))
    try:
        tables = set(connection.introspection.table_names())
        if OutboxEvent._meta.db_table not in tables:
            return _result(
                False,
                "outbox_schema_unavailable",
                "schema_missing",
                latency_ms=round((time.monotonic() - started) * 1000, 3),
            )
        stale = OutboxEvent.objects.filter(
            event_type__startswith="dms.",
            status=OutboxStatus.PENDING,
            created_at__lt=timezone.now() - OUTBOX_FRESHNESS,
        ).exists()
        return _result(
            not stale,
            "outbox_stale" if stale else "ready",
            "outbox_stale" if stale else "ready",
            latency_ms=round((time.monotonic() - started) * 1000, 3),
        )
    except Exception:
        return _result(
            False,
            "outbox_unavailable",
            "dependency_unavailable",
            latency_ms=round((time.monotonic() - started) * 1000, 3),
        )


def get_module_health() -> ModuleHealthReport:
    """Return health evidence suitable for an authenticated governed endpoint."""

    probes = {
        "database_rls": database_readiness_probe(),
        "storage": storage_readiness_probe(),
        "outbox": outbox_readiness_probe(),
    }
    unavailable = any(not result.healthy for result in probes.values())
    degraded = not unavailable and any(result.details.get("code") == "cleanup_failed" for result in probes.values())
    status = "unhealthy" if unavailable else "degraded" if degraded else "healthy"
    checks: dict[str, dict[str, object]] = {}
    for name, result in probes.items():
        latency = result.details.get("latency_ms")
        checks[name] = {
            "status": (
                "unhealthy"
                if not result.healthy
                else "degraded" if result.details.get("code") == "cleanup_failed" else "healthy"
            ),
            "code": str(result.details.get("code", "unknown")),
            "latency_ms": float(latency) if isinstance(latency, (int, float)) else None,
        }
    return ModuleHealthReport(
        status,
        {
            "status": status,
            "checks": checks,
            "checked_at": timezone.now().isoformat(),
        },
    )


def register_health_probes() -> None:
    """Register critical DMS dependencies with global readiness."""

    health_registry.register("dms.database_rls", database_readiness_probe, critical=True, replace=True)
    health_registry.register("dms.storage", storage_readiness_probe, critical=True, replace=True)
    health_registry.register("dms.outbox", outbox_readiness_probe, critical=True, replace=True)


@require_GET
def health_check(request: HttpRequest) -> JsonResponse:
    """Compatibility view; v2 routes wrap this evidence with access governance."""

    del request
    report = get_module_health()
    return JsonResponse(dict(report.payload), status=report.status_code)


__all__ = [
    "DOMAIN_TABLES",
    "ModuleHealthReport",
    "database_readiness_probe",
    "get_module_health",
    "health_check",
    "outbox_readiness_probe",
    "register_health_probes",
    "storage_readiness_probe",
]
