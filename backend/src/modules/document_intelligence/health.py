"""Sanitized module liveness/readiness probes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Mapping

from django.db import connection
from django.utils import timezone

from src.core.health import HealthCheckResult, health_registry

from .adapters import DependencyHealth, RegisteredProviderResolver, get_dms_gateway, get_provider_resolver

DOMAIN_TABLES = (
    "document_intelligence_extractions",
    "document_intelligence_extraction_pages",
    "document_intelligence_classifications",
    "document_intelligence_classification_scores",
    "document_intelligence_classifier_training_jobs",
    "document_intelligence_classifier_model_versions",
    "document_intelligence_extraction_templates",
    "document_intelligence_extraction_template_zones",
)
ASYNC_TABLES = ("async_jobs", "async_job_outbox_events", "async_job_transitions")


@dataclass(frozen=True, slots=True)
class ModuleHealthReport:
    status: str
    payload: Mapping[str, object]

    @property
    def status_code(self) -> int:
        return 503 if self.status == "unavailable" else 200


def database_readiness_probe() -> HealthCheckResult:
    """Check all domain tables and PostgreSQL RLS policy presence without row data."""
    now = timezone.now()
    try:
        tables = set(connection.introspection.table_names())
        missing = [table for table in DOMAIN_TABLES if table not in tables]
        if missing:
            return HealthCheckResult(False, "domain_schema_unavailable", now, {"code": "schema_missing"})
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT tablename FROM pg_policies WHERE schemaname = current_schema() AND tablename = ANY(%s)",
                    [list(DOMAIN_TABLES)],
                )
                policy_tables = {row[0] for row in cursor.fetchall()}
            if policy_tables != set(DOMAIN_TABLES):
                return HealthCheckResult(False, "rls_policy_unavailable", now, {"code": "rls_missing"})
        return HealthCheckResult(True, "ready", now, {"code": "ready"})
    except Exception:
        return HealthCheckResult(False, "database_unavailable", now, {"code": "dependency_unavailable"})


def async_readiness_probe() -> HealthCheckResult:
    now = timezone.now()
    try:
        tables = set(connection.introspection.table_names())
        ready = set(ASYNC_TABLES).issubset(tables)
        return HealthCheckResult(
            ready,
            "ready" if ready else "async_schema_unavailable",
            now,
            {"code": "ready" if ready else "schema_missing"},
        )
    except Exception:
        return HealthCheckResult(False, "async_dependency_unavailable", now, {"code": "dependency_unavailable"})


def dms_readiness_probe(stale_after_seconds: int | None = None) -> HealthCheckResult:
    try:
        return _dependency_result(get_dms_gateway().health(), required=True, stale_after_seconds=stale_after_seconds)
    except Exception:
        return HealthCheckResult(
            False,
            "dependency_unavailable",
            timezone.now(),
            {"code": "dependency_unavailable", "required": True, "circuit_state": "unknown"},
        )


def _stale_window(seconds: int | None) -> timedelta:
    if seconds is None:
        from .services import default_configuration_document

        seconds = int(default_configuration_document()["health"]["stale_after_seconds"])
    if isinstance(seconds, bool) or seconds <= 0:
        raise ValueError("health stale window must be a positive integer")
    return timedelta(seconds=seconds)


def provider_readiness_probe(stale_after_seconds: int | None = None) -> HealthCheckResult:
    """Require one usable OCR adapter; report partial provider failure as degraded."""
    now = timezone.now()
    resolver = get_provider_resolver()
    if not isinstance(resolver, RegisteredProviderResolver):
        probe = getattr(resolver, "health", None)
        if not callable(probe):
            return HealthCheckResult(
                False,
                "provider_probe_unavailable",
                now,
                {"code": "probe_missing", "status": "unavailable"},
            )
        try:
            return _dependency_result(probe(), required=True)
        except Exception:
            return HealthCheckResult(
                False,
                "provider_unavailable",
                now,
                {"code": "dependency_unavailable", "status": "unavailable"},
            )
    adapters = {**resolver.configured_ocr(), **resolver.configured_classifiers()}
    if not adapters:
        return HealthCheckResult(
            False, "provider_unavailable", now, {"code": "not_configured", "status": "unavailable"}
        )
    results: list[DependencyHealth] = []
    for adapter in adapters.values():
        try:
            results.append(adapter.health())
        except Exception:
            continue
    available = sum(1 for result in results if result.available and not _stale(result, stale_after_seconds))
    if available == 0:
        circuit_open = any(result.circuit_state == "open" for result in results)
        return HealthCheckResult(
            False,
            "provider_unavailable",
            now,
            {"code": "circuit_open" if circuit_open else "runtime_unavailable", "status": "unavailable"},
        )
    degraded = available < len(adapters)
    return HealthCheckResult(
        True,
        "degraded" if degraded else "ready",
        now,
        {"code": "partial_provider_failure" if degraded else "ready", "status": "degraded" if degraded else "healthy"},
    )


def _stale(result: DependencyHealth, stale_after_seconds: int | None = None) -> bool:
    checked_at = result.checked_at
    if not hasattr(checked_at, "tzinfo"):
        return True
    try:
        return timezone.now() - checked_at > _stale_window(stale_after_seconds)
    except (TypeError, ValueError):
        return True


def _dependency_result(
    result: DependencyHealth, *, required: bool, stale_after_seconds: int | None = None
) -> HealthCheckResult:
    now = timezone.now()
    stale = _stale(result, stale_after_seconds)
    healthy = bool(result.available) and not stale
    code = "stale" if stale else result.code
    return HealthCheckResult(
        healthy,
        "ready" if healthy else "dependency_unavailable",
        now,
        {"code": code, "required": required, "circuit_state": result.circuit_state},
    )


def get_module_health(stale_after_seconds: int | None = None) -> ModuleHealthReport:
    """Return a non-sensitive readiness report for the authenticated endpoint."""
    dms_result = dms_readiness_probe() if stale_after_seconds is None else dms_readiness_probe(stale_after_seconds)
    provider_result = (
        provider_readiness_probe() if stale_after_seconds is None else provider_readiness_probe(stale_after_seconds)
    )
    probes = {
        "database": database_readiness_probe(),
        "async_execution": async_readiness_probe(),
        "dms": dms_result,
        "providers": provider_result,
    }
    critical = ("database", "async_execution", "dms", "providers")
    unavailable = any(not probes[name].healthy for name in critical)
    degraded = not unavailable and probes["providers"].details.get("status") == "degraded"
    status = "unavailable" if unavailable else "degraded" if degraded else "healthy"
    dependencies = [
        {
            "name": name,
            "status": "healthy" if result.healthy else "unavailable",
            "code": str(result.details.get("code", "unknown")),
            "checked_at": result.checked_at.isoformat(),
            **({"circuit_state": result.details["circuit_state"]} if "circuit_state" in result.details else {}),
        }
        for name, result in probes.items()
    ]
    if degraded:
        dependencies = [
            {**item, "status": "degraded"} if item["name"] == "providers" else item for item in dependencies
        ]
    return ModuleHealthReport(
        status,
        {
            "status": status,
            "live": True,
            "ready": not unavailable,
            "checked_at": timezone.now().isoformat(),
            "dependencies": dependencies,
        },
    )


def register_health_probes() -> None:
    """Register composite critical probes with global application readiness."""
    health_registry.register(
        "document_intelligence.database_rls", database_readiness_probe, critical=True, replace=True
    )
    health_registry.register(
        "document_intelligence.async_execution", async_readiness_probe, critical=True, replace=True
    )
    health_registry.register("document_intelligence.dms", dms_readiness_probe, critical=True, replace=True)
    health_registry.register("document_intelligence.providers", provider_readiness_probe, critical=True, replace=True)


__all__ = [
    "ModuleHealthReport",
    "async_readiness_probe",
    "database_readiness_probe",
    "dms_readiness_probe",
    "get_module_health",
    "provider_readiness_probe",
    "register_health_probes",
]
