"""Bounded, tenant-aware, sanitized readiness for email marketing."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Final
from uuid import UUID

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
from src.core.async_jobs.models import OutboxEvent, OutboxStatus
from src.core.async_jobs.services import get_handler
from src.core.health import HealthCheckResult, health_registry
from src.core.state_machine import registry as state_machine_registry

from .adapters import (
    AdapterNotRegistered,
    get_audience_resolver,
    get_delivery_gateway,
    get_renderer,
)
from .jobs import COMMANDS

DOMAIN_TABLES: Final = (
    "email_campaigns",
    "email_templates",
    "email_campaign_recipients",
    "email_delivery_attempts",
    "email_delivery_attempt_revisions",
    "email_delivery_events",
    "email_suppression_entries",
    "email_consent_records",
    "email_marketing_configurations",
    "email_marketing_configuration_versions",
    "email_marketing_lifecycle_transitions",
    "email_marketing_mutation_idempotency",
)
ASYNC_TABLES: Final = (
    "async_jobs",
    "async_job_outbox_events",
    "async_job_transitions",
)
STATE_MACHINES: Final = (
    "email_marketing.campaign",
    "email_marketing.recipient",
)


def _health_policy(tenant_id: UUID | None = None) -> Mapping[str, object]:
    # Lazy import avoids the health/services/adapters dependency cycle.
    from .services import (
        get_platform_runtime_defaults,
        get_runtime_configuration,
    )

    document = (
        getattr(get_runtime_configuration(tenant_id), "document", None)
        if tenant_id is not None
        else get_platform_runtime_defaults()
    )
    if not isinstance(document, Mapping):
        raise ValueError("email marketing runtime configuration is unavailable")
    policy = document.get("health")
    if not isinstance(policy, Mapping):
        raise ValueError("email marketing health configuration is unavailable")
    return policy


def _positive_seconds(policy: Mapping[str, object], key: str) -> float:
    value = policy.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"configured {key} is invalid")
    return float(value)


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
        value: dict[str, object] = {
            "status": self.status,
            "code": self.code,
            "latency_ms": self.latency_ms,
            "critical": self.critical,
        }
        if self.circuit_state is not None:
            value["circuit_state"] = self.circuit_state
        return value


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
        checked_at = timezone.now().isoformat()
        return {
            "module": "email_marketing",
            "status": self.status,
            "live": True,
            "ready": self.ready,
            "migration": "0007_tenant_configured_model_defaults",
            "checked_at": checked_at,
            "checks": [
                {
                    "name": check.name,
                    "status": ("ready" if check.status == "healthy" else check.status),
                    "detail": check.code,
                    "checked_at": checked_at,
                    "latency_ms": check.latency_ms,
                    "critical": check.critical,
                    **({"circuit_state": check.circuit_state} if check.circuit_state is not None else {}),
                }
                for check in self.checks
            ],
        }


Probe = Callable[[], tuple[bool, str] | tuple[bool, str, str]]


def _run(name: str, probe: Probe, *, critical: bool) -> Check:
    started = time.monotonic()
    try:
        result = probe()
        available, code = result[0], result[1]
        circuit_state = result[2] if len(result) == 3 else None
        status = "healthy" if available else "unhealthy" if critical else "degraded"
    except Exception:
        code = "dependency_unavailable"
        circuit_state = "unknown" if name == "delivery_gateway" else None
        status = "unhealthy" if critical else "degraded"
    return Check(
        name,
        status,
        code,
        round((time.monotonic() - started) * 1000, 3),
        critical,
        circuit_state,
    )


def _database() -> tuple[bool, str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        ready = cursor.fetchone() == (1,)
    return ready, "ready" if ready else "query_failed"


def _schema() -> tuple[bool, str]:
    tables = set(connection.introspection.table_names())
    ready = set(DOMAIN_TABLES + ASYNC_TABLES).issubset(tables)
    return ready, "ready" if ready else "schema_missing"


def _migrations() -> tuple[bool, str]:
    executor = MigrationExecutor(connection)
    leaves = tuple(executor.loader.graph.leaf_nodes("email_marketing"))
    if not leaves:
        return False, "migration_graph_missing"
    ready = all(node in executor.loader.applied_migrations for node in leaves)
    return ready, "ready" if ready else "migration_pending"


def _rls() -> tuple[bool, str]:
    if connection.vendor != "postgresql":
        return True, "not_applicable"
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = current_schema() AND c.relname = ANY(%s)""",
            [list(DOMAIN_TABLES)],
        )
        flags = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
        cursor.execute(
            """SELECT tablename, qual, with_check FROM pg_policies
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


def _state_machines() -> tuple[bool, str]:
    ready = set(STATE_MACHINES).issubset(state_machine_registry.names())
    return ready, "ready" if ready else "registration_missing"


def _handlers() -> tuple[bool, str]:
    for command in COMMANDS:
        get_handler(command)
    return True, "ready"


def _outbox(tenant_id: UUID) -> tuple[bool, str]:
    freshness_seconds = _positive_seconds(_health_policy(tenant_id), "outbox_freshness_seconds")
    stale_before = timezone.now() - timedelta(seconds=freshness_seconds)
    stale = OutboxEvent.objects.filter(
        tenant_id=tenant_id,
        status=OutboxStatus.PENDING,
        created_at__lt=stale_before,
    ).exists()
    return not stale, "stale_pending_evidence" if stale else "fresh"


def _gateway(tenant_id: UUID | None = None) -> tuple[bool, str, str]:
    gateway = get_delivery_gateway()
    tenant_health = getattr(gateway, "health_for_tenant", None)
    result = tenant_health(tenant_id) if callable(tenant_health) else gateway.health()
    return result.available, result.code, result.circuit_state


def _renderer() -> tuple[bool, str]:
    get_renderer()
    return True, "ready"


def _audience_resolver() -> tuple[bool, str]:
    try:
        get_audience_resolver()
    except AdapterNotRegistered:
        return False, "resolver_not_registered"
    return True, "ready"


def get_module_health(tenant_id: UUID) -> ModuleHealthReport:
    """Run real probes without exposing addresses, rows, settings, or errors."""
    checks = (
        _run("database", _database, critical=True),
        _run("domain_schema", _schema, critical=True),
        _run("required_migrations", _migrations, critical=True),
        _run("row_level_security", _rls, critical=True),
        _run("state_machines", _state_machines, critical=True),
        _run("async_handlers", _handlers, critical=True),
        _run("outbox_freshness", lambda: _outbox(tenant_id), critical=True),
        _run("renderer", _renderer, critical=True),
        _run("delivery_gateway", lambda: _gateway(tenant_id), critical=True),
        _run("audience_resolver", _audience_resolver, critical=False),
    )
    unhealthy = any(check.critical and check.status == "unhealthy" for check in checks)
    degraded = any(not check.critical and check.status == "degraded" for check in checks)
    status = "unhealthy" if unhealthy else "degraded" if degraded else "ready"
    return ModuleHealthReport(status, checks)


def process_readiness_probe() -> HealthCheckResult:
    """Process-level registry probe; tenant outbox freshness stays request-bound."""
    checks = (
        _run("database", _database, critical=True),
        _run("schema", _schema, critical=True),
        _run("state_machines", _state_machines, critical=True),
        _run("handlers", _handlers, critical=True),
        _run("gateway", lambda: _gateway(None), critical=True),
    )
    healthy = all(check.healthy for check in checks)
    return HealthCheckResult(
        healthy,
        "ready" if healthy else "dependency_unavailable",
        timezone.now(),
        {check.name: check.code for check in checks},
    )


def register_health_probes() -> None:
    staleness_limit = _positive_seconds(_health_policy(), "probe_staleness_seconds")
    health_registry.register(
        "email_marketing.process",
        process_readiness_probe,
        critical=True,
        staleness_limit=staleness_limit,
        replace=True,
    )


class EmailMarketingHealthView(GovernedAPIViewMixin, APIView):  # type: ignore[misc]
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    required_permission = "email_marketing.health:read"
    required_entitlement = "email_marketing"
    quota_resource = "email_marketing.api_reads"
    quota_cost = 1

    def get(self, request: Request) -> Response:
        tenant_id = getattr(request, "tenant_id", None)
        if tenant_id is None:
            try:
                profile = getattr(request.user, "profile", None)
                tenant_id = getattr(profile, "tenant_id", None)
            except (AttributeError, ObjectDoesNotExist):
                tenant_id = None
        try:
            canonical_tenant_id = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
        except (TypeError, ValueError, AttributeError):
            return Response(
                {"status": "unhealthy", "code": "tenant_context_missing"},
                status=503,
            )
        report = get_module_health(canonical_tenant_id)
        return Response(report.as_dict(), status=report.status_code)


health_check = EmailMarketingHealthView.as_view()


__all__ = [
    "ASYNC_TABLES",
    "Check",
    "DOMAIN_TABLES",
    "EmailMarketingHealthView",
    "ModuleHealthReport",
    "get_module_health",
    "health_check",
    "process_readiness_probe",
    "register_health_probes",
]
