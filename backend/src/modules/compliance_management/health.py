"""Sanitized, fail-closed storage readiness for compliance management."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from django.conf import settings
from django.db import connection, transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone

from src.core.health import HealthCheckResult, health_registry

logger = logging.getLogger("saraise.compliance_management.health")

HEALTH_PROBE_NAME = "compliance_management.storage"
HEALTH_STALENESS_SECONDS = 30
DEFAULT_STATEMENT_TIMEOUT_MS = 1_000
MAX_STATEMENT_TIMEOUT_MS = 10_000
REQUIRED_MODEL_NAMES: tuple[str, ...] = (
    "ComplianceFramework",
    "ComplianceRequirement",
    "CompliancePolicy",
    "CompliancePolicyVersion",
    "RequirementPolicyMapping",
    "ComplianceAssessment",
    "ComplianceEvidence",
    "EvidenceRequirementLink",
    "ComplianceConfigurationRevision",
    "ComplianceActivity",
)


def _statement_timeout_ms() -> int:
    value = getattr(settings, "COMPLIANCE_HEALTH_DB_TIMEOUT_MS", DEFAULT_STATEMENT_TIMEOUT_MS)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_STATEMENT_TIMEOUT_MS:
        return DEFAULT_STATEMENT_TIMEOUT_MS
    return value


def _required_tables() -> tuple[str, ...]:
    """Resolve table names from model metadata so schema renames cannot drift."""

    from . import models

    tables: list[str] = []
    for model_name in REQUIRED_MODEL_NAMES:
        model = getattr(models, model_name, None)
        metadata = getattr(model, "_meta", None)
        table_name = getattr(metadata, "db_table", None)
        if not isinstance(table_name, str) or not table_name:
            raise LookupError(f"required compliance model {model_name} is unavailable")
        tables.append(table_name)
    return tuple(tables)


def _postgres_tables_exist(cursor: object, tables: Sequence[str]) -> bool:
    execute = getattr(cursor, "execute")
    fetchone = getattr(cursor, "fetchone")
    for table in tables:
        execute("SELECT to_regclass(%s)", [table])
        row = fetchone()
        if not row or row[0] is None:
            return False
    return True


def _sqlite_tables_exist(cursor: object, tables: Sequence[str]) -> bool:
    execute = getattr(cursor, "execute")
    fetchall = getattr(cursor, "fetchall")
    placeholders = ", ".join(["%s"] * len(tables))
    execute(
        f"SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ({placeholders})",  # nosec B608
        list(tables),
    )
    present = {row[0] for row in fetchall()}
    return present == set(tables)


def storage_probe() -> HealthCheckResult:
    """Verify bounded database access and the complete module schema.

    The public result deliberately carries only categorical state.  Exception
    text, schema names, row counts, credentials, and tenant data stay out of
    health responses and logs.
    """

    checked_at = timezone.now()
    try:
        tables = _required_tables()
        with transaction.atomic():
            with connection.cursor() as cursor:
                if connection.vendor == "postgresql":
                    cursor.execute("SET LOCAL statement_timeout = %s", [_statement_timeout_ms()])
                    schema_ready = _postgres_tables_exist(cursor, tables)
                elif connection.vendor == "sqlite":
                    schema_ready = _sqlite_tables_exist(cursor, tables)
                else:
                    # Unsupported engines cannot prove the PostgreSQL contract.
                    schema_ready = False
        if not schema_ready:
            return HealthCheckResult(
                healthy=False,
                message="required compliance storage schema is unavailable",
                checked_at=checked_at,
                details={"database": "available", "schema": "unavailable"},
            )
        return HealthCheckResult(
            healthy=True,
            message="compliance storage ready",
            checked_at=checked_at,
            details={"database": "available", "schema": "available"},
        )
    except Exception:
        # Database exceptions can embed credentials or private schema details;
        # the stable reason code is sufficient for operations and metrics.
        logger.error(
            "Compliance storage readiness failed",
            extra={"event": "compliance_management.storage_probe.failed", "failure_reason": "storage_unavailable"},
        )
        return HealthCheckResult(
            healthy=False,
            message="compliance storage is unavailable",
            checked_at=checked_at,
            details={"database": "unavailable", "schema": "unavailable"},
        )


def register_health_probe() -> None:
    """Register the critical process-level readiness probe idempotently."""

    health_registry.register(
        HEALTH_PROBE_NAME,
        storage_probe,
        critical=True,
        staleness_limit=HEALTH_STALENESS_SECONDS,
        replace=True,
    )


def health_check(request: HttpRequest) -> JsonResponse:
    """Compatibility route backed by the real storage probe, never a constant."""

    del request
    result = storage_probe()
    payload = {
        "status": "healthy" if result.healthy else "unhealthy",
        "module": "compliance_management",
        "checked_at": result.checked_at.isoformat(),
        "checks": dict(result.details),
    }
    return JsonResponse(payload, status=200 if result.healthy else 503)


# The legacy module URL imports this module during Django startup.  AppConfig
# wiring may safely call the same registration function because replacement is
# explicit and idempotent.
register_health_probe()

__all__ = [
    "HEALTH_PROBE_NAME",
    "REQUIRED_MODEL_NAMES",
    "health_check",
    "register_health_probe",
    "storage_probe",
]
