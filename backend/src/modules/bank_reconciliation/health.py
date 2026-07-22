"""Sanitized module liveness and dependency readiness probes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from django.db import connection
from django.http import JsonResponse
from django.utils import timezone

from src.core.async_jobs.services import get_handler
from src.core.health import HealthCheckResult, health_registry
from src.core.state_machine import MachineNotRegisteredError
from src.core.state_machine import get as get_state_machine

from .adapters import ledger_gateway_status, parser_registry_status
from .matching import candidate_provider_registry_status

DOMAIN_TABLES = (
    "bank_accounts",
    "bank_statement_imports",
    "bank_statements",
    "bank_transactions",
    "bank_matching_rules",
    "bank_reconciliation_sessions",
    "bank_reconciliation_matches",
    "bank_reconciliation_match_lines",
)
ASYNC_TABLES = ("async_jobs", "async_job_outbox_events", "async_job_transitions")
REQUIRED_HANDLERS = ("bank_reconciliation.import_statement",)
REQUIRED_MACHINES = ("bank_reconciliation.statement_import", "bank_reconciliation.reconciliation")


@dataclass(frozen=True, slots=True)
class ModuleHealthReport:
    status: str
    payload: Mapping[str, object]

    @property
    def status_code(self) -> int:
        return 503 if self.status == "unavailable" else 200


def database_readiness_probe() -> HealthCheckResult:
    now = timezone.now()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        tables = set(connection.introspection.table_names())
        missing = set(DOMAIN_TABLES) - tables
        if missing:
            return HealthCheckResult(False, "domain_schema_unavailable", now, {"code": "schema_missing"})
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT tablename FROM pg_policies WHERE schemaname = current_schema() AND tablename = ANY(%s)",
                    [list(DOMAIN_TABLES)],
                )
                protected = {row[0] for row in cursor.fetchall()}
            if protected != set(DOMAIN_TABLES):
                return HealthCheckResult(False, "rls_policy_unavailable", now, {"code": "rls_missing"})
        return HealthCheckResult(True, "ready", now, {"code": "ready"})
    except Exception:
        return HealthCheckResult(False, "database_unavailable", now, {"code": "dependency_unavailable"})


def parser_readiness_probe() -> HealthCheckResult:
    now = timezone.now()
    status = parser_registry_status()
    ready = status["ready"] is True
    return HealthCheckResult(
        ready,
        "ready" if ready else "parser_registry_unavailable",
        now,
        {"code": "ready" if ready else "required_parser_missing", "registered_count": len(status["registered"])},
    )


def state_machine_readiness_probe() -> HealthCheckResult:
    now = timezone.now()
    try:
        for name in REQUIRED_MACHINES:
            get_state_machine(name)
    except (MachineNotRegisteredError, LookupError):
        return HealthCheckResult(False, "state_machine_unavailable", now, {"code": "registration_missing"})
    return HealthCheckResult(True, "ready", now, {"code": "ready"})


def async_readiness_probe() -> HealthCheckResult:
    now = timezone.now()
    try:
        # Import establishes registration when app startup has not imported the
        # task module yet; no work is executed by this probe.
        from . import tasks as _tasks

        del _tasks
        for command in REQUIRED_HANDLERS:
            get_handler(command)
        tables = set(connection.introspection.table_names())
        if not set(ASYNC_TABLES).issubset(tables):
            return HealthCheckResult(False, "async_schema_unavailable", now, {"code": "schema_missing"})
    except Exception as exc:
        # The broad branch intentionally emits only a stable code.
        del exc
        return HealthCheckResult(False, "async_dependency_unavailable", now, {"code": "dependency_unavailable"})
    return HealthCheckResult(True, "ready", now, {"code": "ready"})


def outbox_readiness_probe() -> HealthCheckResult:
    now = timezone.now()
    try:
        tables = set(connection.introspection.table_names())
        ready = "async_job_outbox_events" in tables
    except Exception:
        ready = False
    return HealthCheckResult(
        ready,
        "ready" if ready else "outbox_unavailable",
        now,
        {"code": "ready" if ready else "schema_missing"},
    )


def candidate_provider_readiness_probe() -> HealthCheckResult:
    now = timezone.now()
    status = candidate_provider_registry_status()
    ready = status["ready"] is True
    return HealthCheckResult(
        ready,
        "ready" if ready else "candidate_provider_unavailable",
        now,
        {"code": "ready" if ready else "core_missing"},
    )


def ledger_readiness_probe() -> HealthCheckResult:
    now = timezone.now()
    status = ledger_gateway_status()
    # Ledger integration is optional. Not configured is truthful and healthy;
    # a configured-but-failing gateway degrades the module without blocking the
    # core file workflow.
    healthy = status.status in {"available", "not_configured"}
    return HealthCheckResult(healthy, status.status, now, {"code": status.code, "status": status.status})


def get_module_health() -> ModuleHealthReport:
    probes = {
        "database": database_readiness_probe(),
        "parsers": parser_readiness_probe(),
        "state_machines": state_machine_readiness_probe(),
        "async_execution": async_readiness_probe(),
        "outbox": outbox_readiness_probe(),
        "candidate_provider": candidate_provider_readiness_probe(),
        "ledger_gateway": ledger_readiness_probe(),
    }
    required = ("database", "parsers", "state_machines", "async_execution", "outbox", "candidate_provider")
    unavailable = any(not probes[name].healthy for name in required)
    degraded = not unavailable and probes["ledger_gateway"].details.get("status") == "degraded"
    status = "unavailable" if unavailable else "degraded" if degraded else "healthy"
    components = [
        {
            "name": name,
            "status": (
                "degraded" if name == "ledger_gateway" and degraded else "healthy" if result.healthy else "unavailable"
            ),
            "code": str(result.details.get("code", "unknown")),
            "checked_at": result.checked_at.isoformat(),
        }
        for name, result in probes.items()
    ]
    return ModuleHealthReport(
        status,
        {
            "status": status,
            "live": True,
            "ready": not unavailable,
            "checked_at": timezone.now().isoformat(),
            "components": components,
        },
    )


def health_check(request: object) -> JsonResponse:
    """Compatibility function for the module URL; API v2 protects the route."""
    correlation_id = getattr(request, "correlation_id", None) or getattr(request, "request_id", None) or ""
    report = get_module_health()
    payload = {
        "data": dict(report.payload),
        "meta": {"correlation_id": str(correlation_id), "timestamp": timezone.now().isoformat()},
    }
    return JsonResponse(payload, status=report.status_code)


def register_health_probes() -> None:
    health_registry.register("bank_reconciliation.database_rls", database_readiness_probe, critical=True, replace=True)
    health_registry.register("bank_reconciliation.parsers", parser_readiness_probe, critical=True, replace=True)
    health_registry.register(
        "bank_reconciliation.state_machines", state_machine_readiness_probe, critical=True, replace=True
    )
    health_registry.register("bank_reconciliation.async_execution", async_readiness_probe, critical=True, replace=True)
    health_registry.register("bank_reconciliation.outbox", outbox_readiness_probe, critical=True, replace=True)
    health_registry.register(
        "bank_reconciliation.candidate_provider",
        candidate_provider_readiness_probe,
        critical=True,
        replace=True,
    )
    health_registry.register("bank_reconciliation.ledger", ledger_readiness_probe, critical=False, replace=True)


__all__ = [
    "ModuleHealthReport",
    "async_readiness_probe",
    "candidate_provider_readiness_probe",
    "database_readiness_probe",
    "get_module_health",
    "health_check",
    "ledger_readiness_probe",
    "outbox_readiness_probe",
    "parser_readiness_probe",
    "register_health_probes",
    "state_machine_readiness_probe",
]
