"""Sanitized liveness and fail-closed accounting readiness checks."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Final, Mapping

from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from src.core.api import SuccessEnvelopeRenderer
from src.core.health import HealthCheckResult, health_registry

from .integrations import InvalidProviderResult, extension_registry
from .jobs import REGISTERED_COMMANDS, handlers_ready

logger = logging.getLogger("saraise.accounting_finance")

MODULE_VERSION: Final = "2.0.0"
DOMAIN_TABLES: Final = frozenset(
    {
        "accounting_accounts",
        "accounting_posting_periods",
        "accounting_journal_entries",
        "accounting_journal_lines",
        "accounting_ap_invoices",
        "accounting_ap_invoice_lines",
        "accounting_ar_invoices",
        "accounting_ar_invoice_lines",
        "accounting_payments",
    }
)
REQUIRED_MIGRATIONS: Final = frozenset(
    {"0001_initial", "0002_v2_additive_schema", "0003_v2_constraints_and_indexes", "0004_enable_rls"}
)


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    name: str
    ready: bool
    code: str
    latency_ms: float

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "ready": self.ready,
            "code": self.code,
            "latency_ms": self.latency_ms,
        }


@dataclass(frozen=True, slots=True)
class AccountingHealthReport:
    status: str
    version: str
    checks: tuple[ReadinessCheck, ...]
    latency_ms: float

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    @property
    def status_code(self) -> int:
        return status.HTTP_200_OK if self.ready else status.HTTP_503_SERVICE_UNAVAILABLE

    def as_dict(self) -> dict[str, object]:
        return {
            "module": "accounting_finance",
            "version": self.version,
            "status": self.status,
            "checks": [check.as_dict() for check in self.checks],
            "latency_ms": self.latency_ms,
        }


def _timed(name: str, success_code: str, failure_code: str, probe: object) -> ReadinessCheck:
    started = time.monotonic()
    try:
        ready = bool(probe()) if callable(probe) else False
    except Exception:
        ready = False
    return ReadinessCheck(
        name=name,
        ready=ready,
        code=success_code if ready else failure_code,
        latency_ms=round((time.monotonic() - started) * 1000, 3),
    )


def _database_access() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        return cursor.fetchone() == (1,)


def _schema_and_migrations() -> bool:
    tables = set(connection.introspection.table_names())
    if not DOMAIN_TABLES.issubset(tables):
        return False
    applied = {
        name
        for app, name in MigrationRecorder(connection).applied_migrations()
        if app == "accounting_finance"
    }
    return REQUIRED_MIGRATIONS.issubset(applied)


def _rls_enforced() -> bool:
    # SQLite is used only by the unit suite and has no RLS feature.  The check
    # is explicitly "not applicable", never represented as PostgreSQL RLS.
    if connection.vendor != "postgresql":
        return True
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
        flags = {name: (bool(enabled), bool(forced)) for name, enabled, forced in cursor.fetchall()}
        cursor.execute(
            """
            SELECT tablename, qual, with_check
            FROM pg_policies
            WHERE schemaname = current_schema() AND tablename = ANY(%s)
            """,
            [sorted(DOMAIN_TABLES)],
        )
        policies = {
            name
            for name, using, check in cursor.fetchall()
            if "app.tenant_id" in str(using or "") and "app.tenant_id" in str(check or "")
        }
        cursor.execute(
            """
            SELECT r.rolsuper, r.rolbypassrls, c.relowner = r.oid
            FROM pg_roles r
            JOIN pg_class c ON c.relname = %s
            WHERE r.rolname = current_user
            """,
            [sorted(DOMAIN_TABLES)[0]],
        )
        role = cursor.fetchone()
    protected = {name for name, values in flags.items() if values == (True, True)}
    safe_role = bool(role) and not bool(role[0]) and not bool(role[1]) and not bool(role[2])
    return protected == DOMAIN_TABLES and policies == DOMAIN_TABLES and safe_role


def _mdm_capability() -> bool:
    return extension_registry.has_party_directory()


def _circuits_closed() -> bool:
    try:
        return all(state == "closed" for state in extension_registry.circuit_states().values())
    except InvalidProviderResult:
        return False


def get_module_health() -> AccountingHealthReport:
    """Evaluate every readiness dependency without exposing exception text."""

    started = time.monotonic()
    checks = (
        _timed("database", "DATABASE_READY", "DATABASE_UNAVAILABLE", _database_access),
        _timed("migrations", "MIGRATIONS_READY", "MIGRATIONS_MISSING", _schema_and_migrations),
        _timed(
            "row_level_security",
            "RLS_ENFORCED" if connection.vendor == "postgresql" else "RLS_NOT_APPLICABLE",
            "RLS_NOT_ENFORCED",
            _rls_enforced,
        ),
        _timed("async_handlers", "HANDLERS_READY", "HANDLERS_MISSING", handlers_ready),
        _timed("party_directory", "MDM_CAPABILITY_READY", "MDM_CAPABILITY_UNAVAILABLE", _mdm_capability),
        _timed("configured_circuits", "CIRCUITS_CLOSED", "CIRCUIT_OPEN", _circuits_closed),
    )
    ready = all(check.ready for check in checks)
    return AccountingHealthReport(
        status="ready" if ready else "not_ready",
        version=MODULE_VERSION,
        checks=checks,
        latency_ms=round((time.monotonic() - started) * 1000, 3),
    )


def accounting_readiness_probe() -> HealthCheckResult:
    """Adapter registered with the process-wide readiness registry."""

    report = get_module_health()
    return HealthCheckResult(
        healthy=report.ready,
        message="" if report.ready else "accounting readiness checks failed",
        details={
            "module": "accounting_finance",
            "version": MODULE_VERSION,
            "checks": {check.name: check.code for check in report.checks},
            "commands": REGISTERED_COMMANDS,
            "latency_ms": report.latency_ms,
        },
    )


_registration_lock = threading.RLock()
_registered = False


def register_health_probe() -> None:
    """Install the accounting probe once without silently replacing another."""

    global _registered
    with _registration_lock:
        if _registered:
            return
        health_registry.register(
            "accounting_finance",
            accounting_readiness_probe,
            critical=True,
            staleness_limit=30.0,
        )
        _registered = True


@api_view(["GET"])
@permission_classes([AllowAny])
@renderer_classes([SuccessEnvelopeRenderer])
def live(request: object) -> Response:
    """Process-only liveness; dependencies do not affect it."""

    del request
    return Response({"module": "accounting_finance", "version": MODULE_VERSION, "status": "live"})


@api_view(["GET"])
@permission_classes([AllowAny])
@renderer_classes([SuccessEnvelopeRenderer])
def ready(request: object) -> Response:
    """Return the sanitized, named module readiness checks."""

    del request
    try:
        report = get_module_health()
    except Exception:
        logger.exception(
            "Accounting readiness probe failed",
            extra={
                "event": "accounting.health.ready",
                "resource_type": "health",
                "operation": "ready",
                "outcome": "failed",
                "error_code": "READINESS_PROBE_FAILED",
            },
        )
        return Response(
            {
                "module": "accounting_finance",
                "version": MODULE_VERSION,
                "status": "not_ready",
                "checks": [
                    {
                        "name": "probe",
                        "ready": False,
                        "code": "READINESS_PROBE_FAILED",
                        "latency_ms": 0.0,
                    }
                ],
                "latency_ms": 0.0,
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response(report.as_dict(), status=report.status_code)


# Retained import name for the existing URL module; canonical v2 points here.
health_check = ready


__all__ = [
    "AccountingHealthReport",
    "DOMAIN_TABLES",
    "MODULE_VERSION",
    "REQUIRED_MIGRATIONS",
    "ReadinessCheck",
    "accounting_readiness_probe",
    "get_module_health",
    "health_check",
    "live",
    "ready",
    "register_health_probe",
]
