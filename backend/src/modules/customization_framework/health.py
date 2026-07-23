"""Sanitized readiness checks for the customization domain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from django.conf import settings
from django.db import connection
from django.utils import timezone

from src.core.state_machine import registry as state_machine_registry

DOMAIN_TABLES = (
    "customization_field_definitions",
    "customization_field_values",
    "customization_form_definitions",
    "customization_form_layout_versions",
    "customization_business_rules",
    "customization_business_rule_versions",
    "customization_rule_executions",
)
STATE_MACHINES = (
    "customization_framework.field_definition",
    "customization_framework.form",
    "customization_framework.rule",
)
ASYNC_TABLES = ("async_jobs", "async_job_outbox_events", "async_job_transitions")


@dataclass(frozen=True, slots=True)
class ModuleHealthReport:
    status: str
    payload: Mapping[str, object]

    @property
    def status_code(self) -> int:
        return 503 if self.status == "unavailable" else 200


def _database_check() -> tuple[bool, str]:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True, "ready"
    except Exception:
        return False, "dependency_unavailable"


def _schema_check() -> tuple[bool, str]:
    try:
        tables = set(connection.introspection.table_names())
        return (True, "ready") if set(DOMAIN_TABLES).issubset(tables) else (False, "schema_missing")
    except Exception:
        return False, "dependency_unavailable"


def _rls_check() -> tuple[bool, str]:
    if connection.vendor != "postgresql":
        return False, "rls_unverifiable"
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                   WHERE n.nspname=current_schema() AND c.relname = ANY(%s)""",
                [list(DOMAIN_TABLES)],
            )
            flags = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
            cursor.execute(
                """SELECT tablename, qual, with_check FROM pg_policies
                   WHERE schemaname=current_schema() AND tablename = ANY(%s)""",
                [list(DOMAIN_TABLES)],
            )
            policies = {row[0] for row in cursor.fetchall() if row[1] and row[2]}
        ready = (
            set(flags) == set(DOMAIN_TABLES)
            and all(enabled and forced for enabled, forced in flags.values())
            and policies == set(DOMAIN_TABLES)
        )
        return (True, "ready") if ready else (False, "rls_missing")
    except Exception:
        return False, "dependency_unavailable"


def _state_machine_check() -> tuple[bool, str]:
    ready = set(STATE_MACHINES).issubset(state_machine_registry.names())
    return (True, "ready") if ready else (False, "registration_missing")


def _async_check() -> tuple[bool, str]:
    if not getattr(settings, "CUSTOMIZATION_ASYNC_IMPACT_ENABLED", False):
        return True, "disabled"
    try:
        ready = set(ASYNC_TABLES).issubset(set(connection.introspection.table_names()))
        return (True, "ready") if ready else (False, "schema_missing")
    except Exception:
        return False, "dependency_unavailable"


def get_module_health() -> ModuleHealthReport:
    """Return readiness without counts, SQL, hostnames, or exception text."""
    checks = {
        "database": _database_check(),
        "domain_schema": _schema_check(),
        "row_level_security": _rls_check(),
        "state_machines": _state_machine_check(),
        "async_outbox": _async_check(),
    }
    ready = all(value[0] for value in checks.values())
    status = "healthy" if ready else "unavailable"
    payload = {
        "status": status,
        "live": True,
        "ready": ready,
        "checked_at": timezone.now(),
        "checks": {
            name: {"status": "healthy" if value[0] else "unavailable", "code": value[1]}
            for name, value in checks.items()
        },
    }
    return ModuleHealthReport(status, payload)


__all__ = ["DOMAIN_TABLES", "ModuleHealthReport", "get_module_health"]
