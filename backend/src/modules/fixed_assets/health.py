"""Sanitized readiness checks for fixed-assets persistence and dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from django.db import connection
from django.http import JsonResponse

DOMAIN_TABLES = frozenset(
    {
        "fixed_asset_categories",
        "fixed_assets",
        "fixed_asset_depreciation_schedules",
        "fixed_asset_depreciation_lines",
        "fixed_asset_transactions",
    }
)
ASYNC_TABLES = frozenset({"async_jobs", "async_job_outbox_events", "async_job_transitions"})


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    name: str
    status: str
    code: str


@dataclass(frozen=True, slots=True)
class ModuleHealthReport:
    status: str
    payload: Mapping[str, object]

    @property
    def status_code(self) -> int:
        return 503 if self.status == "unhealthy" else 200


def database_rls_readiness() -> ReadinessCheck:
    """Verify schema access plus enabled and forced PostgreSQL RLS."""

    try:
        tables = set(connection.introspection.table_names())
        if not DOMAIN_TABLES.issubset(tables):
            return ReadinessCheck("database_rls", "unhealthy", "SCHEMA_MISSING")
        if connection.vendor != "postgresql":
            return ReadinessCheck("database_rls", "unhealthy", "RLS_UNSUPPORTED")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema() AND c.relname = ANY(%s)
                """,
                [sorted(DOMAIN_TABLES)],
            )
            protected = {row[0] for row in cursor.fetchall() if bool(row[1]) and bool(row[2])}
            cursor.execute(
                """
                SELECT tablename, qual, with_check
                FROM pg_policies
                WHERE schemaname = current_schema() AND tablename = ANY(%s)
                """,
                [sorted(DOMAIN_TABLES)],
            )
            policy_tables = {
                row[0]
                for row in cursor.fetchall()
                if "app.tenant_id" in str(row[1] or "") and "app.tenant_id" in str(row[2] or "")
            }
        if protected != DOMAIN_TABLES or policy_tables != DOMAIN_TABLES:
            return ReadinessCheck("database_rls", "unhealthy", "RLS_MISSING")
        return ReadinessCheck("database_rls", "healthy", "READY")
    except Exception:
        return ReadinessCheck("database_rls", "unhealthy", "DATABASE_UNAVAILABLE")


def async_job_readiness() -> ReadinessCheck:
    """Verify that durable job and outbox persistence is queryable."""

    try:
        tables = set(connection.introspection.table_names())
        if not ASYNC_TABLES.issubset(tables):
            return ReadinessCheck("async_jobs", "unhealthy", "ASYNC_SCHEMA_MISSING")
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM async_jobs LIMIT 1")
            cursor.fetchone()
        return ReadinessCheck("async_jobs", "healthy", "READY")
    except Exception:
        return ReadinessCheck("async_jobs", "unhealthy", "ASYNC_PERSISTENCE_UNAVAILABLE")


def accounting_adapter_readiness() -> ReadinessCheck:
    """Report optional accounting absence as degraded, never fabricated ready."""

    try:
        from . import integrations

        registry = getattr(integrations, "extension_registry", None)
        adapter = registry.accounting_port() if registry is not None else None
        if adapter is None:
            return ReadinessCheck("accounting_adapter", "degraded", "CAPABILITY_UNAVAILABLE")
        checker = getattr(adapter, "is_configured", None)
        if callable(checker) and not bool(checker()):
            return ReadinessCheck("accounting_adapter", "degraded", "CAPABILITY_UNAVAILABLE")
        # The bundled adapter is configured only when the accounting module
        # publishes the versioned fixed-asset facade it delegates to.
        if isinstance(adapter, integrations.DefaultAccountingAdapter):
            adapter._facade()
        return ReadinessCheck("accounting_adapter", "healthy", "READY")
    except Exception:
        return ReadinessCheck("accounting_adapter", "degraded", "CAPABILITY_UNAVAILABLE")


def get_module_health() -> ModuleHealthReport:
    checks = (database_rls_readiness(), async_job_readiness(), accounting_adapter_readiness())
    critical_unhealthy = any(
        check.status == "unhealthy" for check in checks if check.name in {"database_rls", "async_jobs"}
    )
    degraded = any(check.status == "degraded" for check in checks)
    status = "unhealthy" if critical_unhealthy else "degraded" if degraded else "healthy"
    return ModuleHealthReport(
        status=status,
        payload={
            "status": status,
            "checks": [{"name": check.name, "status": check.status, "code": check.code} for check in checks],
        },
    )


def health_check(request: object) -> JsonResponse:
    """Preserve the API v1 health shape without leaking exception details."""

    del request
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            ready = cursor.fetchone() == (1,)
    except Exception:
        ready = False
    return JsonResponse(
        {
            "status": "healthy" if ready else "unhealthy",
            "module": "fixed_assets",
            "database": "connected" if ready else "unavailable",
        },
        status=200 if ready else 503,
    )


__all__ = [
    "ModuleHealthReport",
    "ReadinessCheck",
    "accounting_adapter_readiness",
    "async_job_readiness",
    "database_rls_readiness",
    "get_module_health",
    "health_check",
]
