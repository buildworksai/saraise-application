"""Bounded, sanitized CRM liveness and dependency readiness."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.access import RequiresAccess
from src.core.api import GovernedAPIViewMixin
from src.core.async_jobs.services import get_handler
from src.core.health import HealthCheckResult, health_registry
from src.core.state_machine import registry as state_machine_registry

from .integrations import IntegrationUnavailable, extension_registry, get_revenue_prediction_client, get_scoring_client
from .jobs import EXTERNAL_ACTIVITY_COMMAND, FULFILLMENT_ACK_COMMAND, LEAD_SCORING_COMMAND, STALE_DEAL_COMMAND

DOMAIN_TABLES: Final = (
    "crm_leads",
    "crm_accounts",
    "crm_contacts",
    "crm_opportunities",
    "crm_activities",
)
ASYNC_TABLES: Final = ("async_jobs", "async_job_outbox_events", "async_job_transitions")
STATE_MACHINES: Final = ("crm.lead", "crm.opportunity")


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: str
    code: str
    latency_ms: float
    critical: bool
    circuit_state: str | None = None

    @property
    def healthy(self) -> bool:
        return self.status == "healthy"

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "status": self.status,
            "code": self.code,
            "latency_ms": self.latency_ms,
            "critical": self.critical,
        }
        if self.circuit_state is not None:
            payload["circuit_state"] = self.circuit_state
        return payload


@dataclass(frozen=True, slots=True)
class ModuleHealthReport:
    status: str
    checks: tuple[Check, ...]

    @property
    def ready(self) -> bool:
        return self.status != "unhealthy"

    @property
    def status_code(self) -> int:
        return 503 if self.status == "unhealthy" else 200

    def as_dict(self) -> dict[str, object]:
        return {
            "module": "crm",
            "status": self.status,
            "live": True,
            "ready": self.ready,
            "checked_at": timezone.now().isoformat(),
            "checks": {check.name: check.as_dict() for check in self.checks},
        }


Probe = Callable[[], tuple[bool, str] | tuple[bool, str, str]]


def _run(name: str, probe: Probe, *, critical: bool) -> Check:
    started = time.monotonic()
    try:
        result = probe()
        available, code = result[0], result[1]
        circuit_state = result[2] if len(result) == 3 else None
        if available:
            status = "healthy"
        else:
            status = "unhealthy" if critical else "degraded"
    except Exception:
        code = "dependency_unavailable"
        circuit_state = None
        status = "unhealthy" if critical else "degraded"
    return Check(
        name=name,
        status=status,
        code=code,
        latency_ms=round((time.monotonic() - started) * 1000, 3),
        critical=critical,
        circuit_state=circuit_state,
    )


def _database() -> tuple[bool, str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        ready = cursor.fetchone() == (1,)
    return ready, "ready" if ready else "query_failed"


def _schema() -> tuple[bool, str]:
    tables = set(connection.introspection.table_names())
    ready = set(DOMAIN_TABLES).issubset(tables)
    return ready, "ready" if ready else "schema_missing"


def _migrations() -> tuple[bool, str]:
    executor = MigrationExecutor(connection)
    leaves = tuple(executor.loader.graph.leaf_nodes("crm"))
    if not leaves:
        return False, "migration_graph_missing"
    applied = executor.loader.applied_migrations
    ready = all(node in applied for node in leaves)
    return ready, "ready" if ready else "migration_pending"


def _rls() -> tuple[bool, str]:
    if connection.vendor != "postgresql":
        # SQLite is restricted to development/test and has no RLS catalog.
        return True, "not_applicable"
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
               FROM pg_class c
               JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = current_schema() AND c.relname = ANY(%s)""",
            [list(DOMAIN_TABLES)],
        )
        flags = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
        cursor.execute(
            """SELECT tablename, qual, with_check
               FROM pg_policies
               WHERE schemaname = current_schema() AND tablename = ANY(%s)""",
            [list(DOMAIN_TABLES)],
        )
        policies = {row[0] for row in cursor.fetchall() if row[1] and row[2]}
    ready = (
        set(flags) == set(DOMAIN_TABLES)
        and all(enabled and forced for enabled, forced in flags.values())
        and policies == set(DOMAIN_TABLES)
    )
    return ready, "ready" if ready else "rls_missing"


def _cache() -> tuple[bool, str]:
    configuration = getattr(settings, "CACHES", {}).get("default", {})
    backend = str(configuration.get("BACKEND", "")) if isinstance(configuration, Mapping) else ""
    if not backend or backend.endswith("DummyCache"):
        return True, "disabled"
    key = "crm:readiness:cache"
    marker = timezone.now().isoformat()
    cache.set(key, marker, timeout=10)
    ready = cache.get(key) == marker
    return ready, "ready" if ready else "roundtrip_failed"


def _async_outbox() -> tuple[bool, str]:
    tables = set(connection.introspection.table_names())
    if not set(ASYNC_TABLES).issubset(tables):
        return False, "schema_missing"
    for command in (
        STALE_DEAL_COMMAND,
        LEAD_SCORING_COMMAND,
        EXTERNAL_ACTIVITY_COMMAND,
        FULFILLMENT_ACK_COMMAND,
    ):
        get_handler(command)
    return True, "ready"


def _state_machines() -> tuple[bool, str]:
    ready = set(STATE_MACHINES).issubset(state_machine_registry.names())
    return ready, "ready" if ready else "registration_missing"


def _provider(getter: Callable[[], object], setting_name: str) -> tuple[bool, str, str]:
    if not isinstance(getattr(settings, setting_name, None), Mapping):
        return True, "disabled", "not_applicable"
    try:
        provider = getter()
        health = provider.health()  # type: ignore[attr-defined]
        return health.available, health.code, health.circuit_state
    except IntegrationUnavailable:
        return False, "configuration_unavailable", "unknown"


def _optional_extensions() -> tuple[bool, str]:
    configured = getattr(settings, "CRM_OPTIONAL_DEPENDENCIES", {})
    if not configured:
        return True, "disabled"
    if not isinstance(configured, Mapping):
        return False, "configuration_invalid"
    capability_map = {
        "master_data_management": "account_enrichment",
        "sales_management": "fulfillment",
    }
    for dependency, raw_enabled in configured.items():
        enabled = raw_enabled.get("enabled", True) if isinstance(raw_enabled, Mapping) else bool(raw_enabled)
        if not enabled:
            continue
        capability = capability_map.get(str(dependency))
        if capability and not extension_registry.resolve(capability):
            return False, "adapter_not_registered"
        module_name = str(dependency).replace("-", "_")
        if capability is None and not apps.is_installed(f"src.modules.{module_name}"):
            return False, "module_not_installed"
    return True, "ready"


def database_readiness_probe() -> HealthCheckResult:
    check = _run("database", _database, critical=True)
    return HealthCheckResult(check.healthy, check.code, timezone.now(), check.as_dict())


def async_readiness_probe() -> HealthCheckResult:
    check = _run("async_outbox", _async_outbox, critical=True)
    return HealthCheckResult(check.healthy, check.code, timezone.now(), check.as_dict())


def rls_readiness_probe() -> HealthCheckResult:
    check = _run("row_level_security", _rls, critical=True)
    return HealthCheckResult(check.healthy, check.code, timezone.now(), check.as_dict())


def get_module_health() -> ModuleHealthReport:
    """Run real readiness checks without querying or exposing business rows."""

    checks = (
        _run("database", _database, critical=True),
        _run("domain_schema", _schema, critical=True),
        _run("required_migrations", _migrations, critical=True),
        _run("row_level_security", _rls, critical=True),
        _run("cache", _cache, critical=False),
        _run("async_outbox", _async_outbox, critical=True),
        _run("state_machines", _state_machines, critical=True),
        _run(
            "lead_scoring_provider",
            lambda: _provider(get_scoring_client, "CRM_LEAD_SCORING_PROVIDER"),
            critical=False,
        ),
        _run(
            "revenue_prediction_provider",
            lambda: _provider(get_revenue_prediction_client, "CRM_REVENUE_PREDICTION_PROVIDER"),
            critical=False,
        ),
        _run("optional_extensions", _optional_extensions, critical=False),
    )
    unhealthy = any(check.critical and check.status == "unhealthy" for check in checks)
    degraded = any(not check.critical and check.status == "degraded" for check in checks)
    status = "unhealthy" if unhealthy else "degraded" if degraded else "healthy"
    return ModuleHealthReport(status=status, checks=checks)


def register_health_probes() -> None:
    """Expose CRM's critical readiness to the process-wide registry."""

    health_registry.register("crm.database", database_readiness_probe, critical=True, replace=True)
    health_registry.register("crm.rls", rls_readiness_probe, critical=True, replace=True)
    health_registry.register("crm.async_outbox", async_readiness_probe, critical=True, replace=True)


class CRMHealthView(GovernedAPIViewMixin, APIView):  # type: ignore[misc]
    """Authenticated v2 health endpoint with explicit entitlement and quota."""

    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    required_permission = "crm.health:read"
    required_entitlement = "crm"
    quota_resource = "crm.health"

    def perform_authentication(self, request: Request) -> None:
        """Bind only the authenticated profile tenant before access checks."""

        super().perform_authentication(request)
        user = getattr(request, "user", None)
        if user is None or not bool(getattr(user, "is_authenticated", False)):
            return
        try:
            raw_tenant_id = getattr(user.profile, "tenant_id", None)
        except (AttributeError, ObjectDoesNotExist):
            return
        try:
            if raw_tenant_id:
                setattr(
                    request,
                    "tenant_id",
                    raw_tenant_id if isinstance(raw_tenant_id, UUID) else UUID(str(raw_tenant_id)),
                )
        except (AttributeError, TypeError, ValueError):
            # RequiresAccess observes no tenant_id and denies by default.
            return

    def get(self, request: Request) -> Response:
        del request
        report = get_module_health()
        return Response(report.as_dict(), status=report.status_code)


health_check = CRMHealthView.as_view()


__all__ = [
    "ASYNC_TABLES",
    "CRMHealthView",
    "Check",
    "DOMAIN_TABLES",
    "ModuleHealthReport",
    "async_readiness_probe",
    "database_readiness_probe",
    "get_module_health",
    "health_check",
    "register_health_probes",
    "rls_readiness_probe",
]
