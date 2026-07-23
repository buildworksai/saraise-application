"""Sanitized liveness and readiness for the sales-management module.

Readiness verifies only infrastructure invariants.  It never returns tenant
data, table row counts, credentials, dependency URLs, or exception text.
Optional paid adapters can degrade the report but cannot make the useful OSS
quote-to-delivery funnel unhealthy.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from django.db import connection, transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone

from src.core.health import HealthCheckResult, health_registry
from src.core.tenancy import get_current_tenant_id

from .integrations import Capability, CapabilityStatus, get_integration_registry

PROBE_TIMEOUT_MILLISECONDS = 2_000
PROBE_STALENESS_LIMIT = timedelta(seconds=30)
OUTBOX_TABLE = "async_job_outbox_events"


def _domain_tables() -> tuple[str, ...]:
    """Resolve authoritative model metadata lazily to keep imports safe."""

    from .models import (
        Customer,
        DeliveryNote,
        DeliveryNoteLine,
        Quotation,
        QuotationLine,
        SalesConfiguration,
        SalesConfigurationVersion,
        SalesDocumentSequence,
        SalesOrder,
        SalesOrderLine,
    )

    return tuple(
        model._meta.db_table
        for model in (
            Customer,
            Quotation,
            QuotationLine,
            SalesOrder,
            SalesOrderLine,
            DeliveryNote,
            DeliveryNoteLine,
            SalesConfiguration,
            SalesConfigurationVersion,
            SalesDocumentSequence,
        )
    )


@dataclass(frozen=True, slots=True)
class SalesHealthReport:
    status: str
    components: Mapping[str, Mapping[str, object]]

    @property
    def ready(self) -> bool:
        return self.status != "unavailable"

    @property
    def status_code(self) -> int:
        return 200 if self.ready else 503

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "module": "sales_management",
            "live": True,
            "ready": self.ready,
            "checked_at": timezone.now().isoformat(),
            "components": dict(self.components),
        }


def liveness_probe() -> HealthCheckResult:
    """Process-only liveness with no database or provider dependency."""

    return HealthCheckResult(True, "live", timezone.now(), {"code": "LIVE"})


def database_rls_probe(tenant_id: UUID | str | None = None) -> HealthCheckResult:
    """Check schema/queryability and PostgreSQL tenant-policy enforcement."""

    checked_at = timezone.now()
    try:
        expected_tables = set(_domain_tables())
        if not expected_tables.issubset(set(connection.introspection.table_names())):
            return HealthCheckResult(False, "schema unavailable", checked_at, {"code": "SCHEMA_MISSING"})

        with transaction.atomic():
            with connection.cursor() as cursor:
                if connection.vendor == "postgresql":
                    cursor.execute("SET LOCAL statement_timeout = %s", [PROBE_TIMEOUT_MILLISECONDS])
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    return HealthCheckResult(False, "database unavailable", checked_at, {"code": "QUERY_FAILED"})

                if connection.vendor == "postgresql":
                    cursor.execute(
                        """
                        SELECT c.relname, c.relrowsecurity,
                               bool_or(p.qual IS NOT NULL),
                               bool_or(p.with_check IS NOT NULL)
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        LEFT JOIN pg_policies p
                          ON p.schemaname = n.nspname AND p.tablename = c.relname
                        WHERE n.nspname = current_schema() AND c.relname = ANY(%s)
                        GROUP BY c.relname, c.relrowsecurity
                        """,
                        [list(expected_tables)],
                    )
                    secured = {
                        name
                        for name, enabled, has_using, has_with_check in cursor.fetchall()
                        if enabled and has_using and has_with_check
                    }
                    if secured != expected_tables:
                        return HealthCheckResult(
                            False, "tenant isolation unavailable", checked_at, {"code": "RLS_MISSING"}
                        )

        if connection.vendor == "postgresql" and tenant_id is not None:
            try:
                expected_tenant = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
            except (TypeError, ValueError, AttributeError):
                return HealthCheckResult(False, "tenant context unavailable", checked_at, {"code": "TENANT_INVALID"})
            try:
                active_tenant = get_current_tenant_id()
            except Exception:
                active_tenant = None
            if active_tenant != expected_tenant:
                return HealthCheckResult(
                    False, "tenant context unavailable", checked_at, {"code": "TENANT_CONTEXT_MISSING"}
                )

        return HealthCheckResult(True, "ready", checked_at, {"code": "READY"})
    except Exception:
        return HealthCheckResult(False, "database unavailable", checked_at, {"code": "DEPENDENCY_UNAVAILABLE"})


def outbox_probe() -> HealthCheckResult:
    """Verify durable outbox schema/queryability without inspecting payloads."""

    checked_at = timezone.now()
    try:
        if OUTBOX_TABLE not in set(connection.introspection.table_names()):
            return HealthCheckResult(False, "outbox unavailable", checked_at, {"code": "SCHEMA_MISSING"})
        with transaction.atomic():
            with connection.cursor() as cursor:
                if connection.vendor == "postgresql":
                    cursor.execute("SET LOCAL statement_timeout = %s", [PROBE_TIMEOUT_MILLISECONDS])
                cursor.execute(f'SELECT 1 FROM "{OUTBOX_TABLE}" LIMIT 1')
                cursor.fetchone()
        return HealthCheckResult(True, "ready", checked_at, {"code": "READY"})
    except Exception:
        return HealthCheckResult(False, "outbox unavailable", checked_at, {"code": "DEPENDENCY_UNAVAILABLE"})


def _required_component(result: HealthCheckResult) -> dict[str, object]:
    age = timezone.now() - result.checked_at
    stale = age > PROBE_STALENESS_LIMIT or age < timedelta(seconds=-1)
    healthy = result.healthy and not stale
    return {
        "status": "available" if healthy else "unavailable",
        "reason_code": "STALE_PROBE" if stale else str(result.details.get("code", "UNKNOWN")),
        "required": True,
    }


def integration_components(tenant_id: UUID | None) -> dict[str, Mapping[str, object]]:
    """Return sanitized optional capability states without invoking business calls."""

    if tenant_id is None:
        return {
            capability.value: {
                "status": "not_configured",
                "reason_code": "TENANT_CONTEXT_NOT_APPLICABLE",
                "required": False,
            }
            for capability in Capability
        }
    try:
        states = get_integration_registry().capabilities(tenant_id)
    except Exception:
        return {
            capability.value: {
                "status": "degraded",
                "reason_code": "REGISTRY_UNAVAILABLE",
                "required": False,
            }
            for capability in Capability
        }
    components: dict[str, Mapping[str, object]] = {}
    for state in states:
        if state.status is CapabilityStatus.AVAILABLE:
            status = "available"
        elif state.status is CapabilityStatus.TEMPORARILY_UNAVAILABLE:
            status = "degraded"
        else:
            status = "not_configured"
        components[state.capability.value] = {
            "status": status,
            "reason_code": state.reason_code,
            "required": False,
            "provider_id": state.provider_id,
        }
    return components


def get_module_health(tenant_id: UUID | str | None = None) -> SalesHealthReport:
    """Aggregate critical readiness and optional provider degradation."""

    database = _required_component(database_rls_probe(tenant_id))
    outbox = _required_component(outbox_probe())
    parsed_tenant: UUID | None
    try:
        parsed_tenant = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id)) if tenant_id else None
    except (TypeError, ValueError, AttributeError):
        parsed_tenant = None
    optional = integration_components(parsed_tenant)
    required_ready = database["status"] == "available" and outbox["status"] == "available"
    optional_ready = all(component["status"] == "available" for component in optional.values())
    status = "available" if required_ready and optional_ready else "degraded" if required_ready else "unavailable"
    return SalesHealthReport(
        status,
        {"database_rls": database, "durable_outbox": outbox, **optional},
    )


def register_health_probes() -> None:
    """Register module-critical probes with the application health registry."""

    health_registry.register(
        "sales_management.database_rls",
        database_rls_probe,
        critical=True,
        staleness_limit=PROBE_STALENESS_LIMIT,
        replace=True,
    )
    health_registry.register(
        "sales_management.durable_outbox",
        outbox_probe,
        critical=True,
        staleness_limit=PROBE_STALENESS_LIMIT,
        replace=True,
    )


def live_health(request: HttpRequest) -> JsonResponse:
    """Public diagnostic exception declared explicitly in the module manifest."""

    del request
    return JsonResponse(
        {
            "status": "healthy",
            "module": "sales_management",
            "live": True,
            "checked_at": timezone.now().isoformat(),
        },
        status=200,
    )


def ready_health(request: HttpRequest) -> JsonResponse:
    """Return minimal readiness; raw failure details are deliberately suppressed."""

    report = get_module_health(getattr(request, "tenant_id", None))
    return JsonResponse(report.as_dict(), status=report.status_code)


# Compatibility for the existing URL import while routes migrate to live/ready.
health_check = ready_health

# URL loading imports this module during application startup. Registration is
# idempotent (``replace=True``) and executes no probe or database query.
register_health_probes()


__all__ = [
    "SalesHealthReport",
    "database_rls_probe",
    "get_module_health",
    "health_check",
    "integration_components",
    "live_health",
    "liveness_probe",
    "outbox_probe",
    "ready_health",
    "register_health_probes",
]
