"""Sanitized liveness and readiness probes for Business Intelligence."""

from __future__ import annotations

import uuid
from typing import Any

from django.core.cache import cache
from django.db import connection

from .datasets import dataset_registry


def _probe_database() -> tuple[bool, dict[str, Any]]:
    required = {
        "bi_query_definitions",
        "bi_reports",
        "bi_dashboards",
        "bi_dashboard_widgets",
        "bi_dashboard_shares",
        "bi_query_executions",
        "async_jobs",
        "async_job_outbox_events",
    }
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            tables = set(connection.introspection.table_names(cursor))
        missing = sorted(required - tables)
        return not missing, {"status": "healthy" if not missing else "unavailable", "missing_tables": missing}
    except Exception:
        return False, {"status": "unavailable"}


def _probe_rls() -> tuple[bool, dict[str, Any]]:
    if connection.vendor != "postgresql":
        return True, {"status": "healthy", "applicable": False}
    try:
        names = (
            "bi_query_definitions",
            "bi_reports",
            "bi_dashboards",
            "bi_dashboard_widgets",
            "bi_dashboard_shares",
            "bi_query_executions",
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(%s)",
                [list(names)],
            )
            records = cursor.fetchall()
        healthy = len(records) == len(names) and all(enabled and forced for _, enabled, forced in records)
        return healthy, {"status": "healthy" if healthy else "unavailable", "tables_checked": len(records)}
    except Exception:
        return False, {"status": "unavailable"}


def _probe_cache() -> tuple[bool, dict[str, Any]]:
    key = f"bi:health:{uuid.uuid4()}"
    try:
        cache.set(key, "ok", 10)
        healthy = cache.get(key) == "ok"
        cache.delete(key)
        return healthy, {"status": "healthy" if healthy else "unavailable"}
    except Exception:
        return False, {"status": "unavailable"}


def _probe_datasets() -> tuple[bool, bool, dict[str, Any]]:
    try:
        validator = getattr(dataset_registry, "validate_integrity", None)
        if callable(validator):
            validator()
        lister = getattr(dataset_registry, "providers", None)
        registered = lister() if callable(lister) else {}
        providers = registered.values() if isinstance(registered, dict) or hasattr(registered, "values") else registered
        summaries: dict[str, str] = {}
        degraded = False
        for entry in providers:
            provider = entry[1] if isinstance(entry, tuple) and len(entry) == 2 else entry
            descriptor = provider.describe()
            key = getattr(descriptor, "key", None) or (
                descriptor.get("key") if isinstance(descriptor, dict) else "unknown"
            )
            health = provider.health()
            value = getattr(health, "status", None) or (
                health.get("status") if isinstance(health, dict) else str(health)
            )
            status = str(getattr(value, "value", value)).lower()
            summaries[str(key)] = status if status in {"healthy", "degraded", "unavailable"} else "unavailable"
            degraded = degraded or summaries[str(key)] != "healthy"
        return True, degraded, {"status": "degraded" if degraded else "healthy", "providers": summaries}
    except Exception:
        return False, False, {"status": "unavailable"}


def module_health() -> dict[str, Any]:
    """Return only bounded operational state; raw exceptions never escape."""
    database_ok, database = _probe_database()
    rls_ok, rls = _probe_rls()
    cache_ok, cache_result = _probe_cache()
    registry_ok, provider_degraded, datasets = _probe_datasets()
    ready = database_ok and rls_ok and cache_ok and registry_ok
    status = "unavailable" if not ready else ("degraded" if provider_degraded else "healthy")
    return {
        "status": status,
        "ready": ready,
        "dependencies": {"database": database, "rls": rls, "cache": cache_result, "datasets": datasets},
    }


health_check = module_health
check_health = module_health

__all__ = ["check_health", "health_check", "module_health"]
