"""Bounded, governed, and non-leaking readiness for Human Resources."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.access import RequiresAccess
from src.core.api import GovernedAPIViewMixin
from src.core.api.results import OperationFailed
from src.core.health import HealthCheckResult, health_registry
from src.core.middleware.correlation import get_correlation_id
from src.core.state_machine import registry as state_machine_registry

from .permissions import GovernedSessionAuthentication, requirement_for

logger = logging.getLogger("saraise.human_resources.health")

DOMAIN_TABLES: Final = (
    "hr_departments",
    "hr_employees",
    "hr_attendances",
    "hr_attendance_revisions",
    "hr_leave_balances",
    "hr_leave_requests",
    "hr_configurations",
    "hr_configuration_versions",
    "hr_configuration_audits",
    "hr_mutation_commands",
)
OUTBOX_TABLES: Final = ("async_job_outbox_events",)
STATE_MACHINES: Final = (
    "human_resources.employee_lifecycle",
    "human_resources.leave_request",
)


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    """Sanitized result of one bounded dependency probe."""

    name: str
    healthy: bool
    code: str
    latency_ms: float
    critical: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": "healthy" if self.healthy else "unhealthy",
            "code": self.code,
            "latency_ms": self.latency_ms,
            "critical": self.critical,
        }


@dataclass(frozen=True, slots=True)
class HumanResourcesHealthReport:
    """Complete public readiness report; it contains no business data."""

    checks: tuple[ReadinessCheck, ...]

    @property
    def ready(self) -> bool:
        return all(check.healthy for check in self.checks if check.critical)

    @property
    def status_code(self) -> int:
        return 200 if self.ready else 503

    def as_dict(self) -> dict[str, object]:
        return {
            "module": "human_resources",
            "status": "healthy" if self.ready else "unhealthy",
            "live": True,
            "ready": self.ready,
            "checked_at": timezone.now().isoformat(),
            "checks": {check.name: check.as_dict() for check in self.checks},
        }


Probe = Callable[[], tuple[bool, str]]


def _run(name: str, probe: Probe, *, critical: bool = True) -> ReadinessCheck:
    """Run a probe and replace internal failures with a stable public code."""

    started = time.monotonic()
    try:
        healthy, code = probe()
    except Exception:
        healthy, code = False, "DEPENDENCY_CHECK_FAILED"
        logger.exception(
            "HR readiness probe failed",
            extra={
                "correlation_id": get_correlation_id(),
                "tenant_id": "",
                "actor_id": "",
                "action": "readiness_probe",
                "aggregate_type": "health",
                "aggregate_id": name,
                "result_code": code,
            },
        )
    return ReadinessCheck(
        name=name,
        healthy=healthy,
        code=code,
        latency_ms=round((time.monotonic() - started) * 1000, 3),
        critical=critical,
    )


def _database() -> tuple[bool, str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        available = cursor.fetchone() == (1,)
    return available, "READY" if available else "DATABASE_UNAVAILABLE"


def _schema() -> tuple[bool, str]:
    available = set(DOMAIN_TABLES).issubset(connection.introspection.table_names())
    return available, "READY" if available else "HR_SCHEMA_MISSING"


def _migrations() -> tuple[bool, str]:
    executor = MigrationExecutor(connection)
    leaves = tuple(executor.loader.graph.leaf_nodes("human_resources"))
    available = bool(leaves) and all(node in executor.loader.applied_migrations for node in leaves)
    return available, "READY" if available else "HR_MIGRATIONS_PENDING"


def _row_level_security() -> tuple[bool, str]:
    if connection.vendor != "postgresql":
        # PostgreSQL row-level security is a required security dependency.
        # A test/development adapter may exercise application behavior, but it
        # cannot prove that the production isolation control is enforced.
        return False, "HR_RLS_UNAVAILABLE"
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
            """SELECT tablename, policyname, cmd, roles, qual, with_check
               FROM pg_policies
               WHERE schemaname = current_schema() AND tablename = ANY(%s)""",
            [list(DOMAIN_TABLES)],
        )
        canonical_expression = "(tenant_id = saraise_current_tenant_id())"
        policy_tables = {
            row[0]
            for row in cursor.fetchall()
            if row[1] == f"tenant_isolation_{row[0]}"
            and row[2] == "ALL"
            and set(row[3]) == {"public"}
            and row[4] == canonical_expression
            and row[5] == canonical_expression
        }
    available = (
        set(flags) == set(DOMAIN_TABLES)
        and all(enabled and forced for enabled, forced in flags.values())
        and policy_tables == set(DOMAIN_TABLES)
    )
    return available, "READY" if available else "HR_RLS_NOT_ENFORCED"


def _state_machines() -> tuple[bool, str]:
    available = set(STATE_MACHINES).issubset(state_machine_registry.names())
    return available, "READY" if available else "HR_STATE_MACHINES_MISSING"


def _outbox() -> tuple[bool, str]:
    model_available = (
        apps.is_installed("src.core.async_jobs")
        and apps.get_model("async_jobs", "OutboxEvent", require_ready=True) is not None
    )
    schema_available = set(OUTBOX_TABLES).issubset(connection.introspection.table_names())
    available = model_available and schema_available
    return available, "READY" if available else "OUTBOX_UNAVAILABLE"


def get_module_health() -> HumanResourcesHealthReport:
    """Execute all critical checks without selecting HR rows."""

    return HumanResourcesHealthReport(
        checks=(
            _run("database", _database),
            _run("domain_schema", _schema),
            _run("required_migrations", _migrations),
            _run("row_level_security", _row_level_security),
            _run("state_machines", _state_machines),
            _run("transactional_outbox", _outbox),
        )
    )


def readiness_probe() -> HealthCheckResult:
    """Adapter for the process-wide health registry."""

    report = get_module_health()
    return HealthCheckResult(
        healthy=report.ready,
        message="READY" if report.ready else "HR_NOT_READY",
        checked_at=timezone.now(),
        details={"checks": {check.name: check.code for check in report.checks}},
    )


def register_health_probes() -> None:
    """Register the complete HR readiness contract with the application."""

    from .services import HumanResourcesConfigurationService

    raw_staleness_limit = HumanResourcesConfigurationService.default_document()["operations"][
        "health_staleness_seconds"
    ]
    if isinstance(raw_staleness_limit, bool) or not isinstance(raw_staleness_limit, (int, float)):
        raise ValueError("HR health staleness configuration must be numeric")
    staleness_limit = float(raw_staleness_limit)
    if staleness_limit <= 0:
        raise ValueError("HR health staleness configuration must be greater than zero")
    health_registry.register(
        "human_resources.readiness",
        readiness_probe,
        critical=True,
        staleness_limit=staleness_limit,
        replace=True,
    )


class HumanResourcesHealthView(GovernedAPIViewMixin, APIView):  # type: ignore[misc]
    """Authenticated and quota-governed module readiness endpoint."""

    authentication_classes = (GovernedSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    http_method_names = ("get", "head", "options")

    def perform_authentication(self, request: Request) -> None:
        super().perform_authentication(request)
        user = getattr(request, "user", None)
        if user is None or not bool(getattr(user, "is_authenticated", False)):
            return
        try:
            raw_tenant_id = getattr(getattr(user, "profile", None), "tenant_id", None)
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
            # RequiresAccess observes no valid tenant and denies by default.
            return

    def get_permissions(self) -> Sequence[Any]:
        requirement = requirement_for("health", "get")
        self.required_permission = requirement.permission if requirement else None
        self.required_entitlement = requirement.entitlement if requirement else None
        self.quota_resource = requirement.quota_resource if requirement else None
        self.quota_cost = requirement.quota_cost if requirement else 0
        return super().get_permissions()

    def get(self, request: Request) -> Response:
        del request
        report = get_module_health()
        if not report.ready:
            raise OperationFailed(
                error_code="HR_NOT_READY",
                message="Human Resources is not ready.",
                detail=report.as_dict(),
                http_status=report.status_code,
            )
        return Response(report.as_dict(), status=report.status_code)


health_check = HumanResourcesHealthView.as_view()


__all__ = [
    "DOMAIN_TABLES",
    "HumanResourcesHealthReport",
    "HumanResourcesHealthView",
    "OUTBOX_TABLES",
    "ReadinessCheck",
    "STATE_MACHINES",
    "get_module_health",
    "health_check",
    "readiness_probe",
    "register_health_probes",
]
