"""Fail-closed, non-sensitive readiness for security access control."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Callable, Mapping
from urllib.parse import urljoin
from uuid import UUID, uuid4

from django.conf import settings
from django.db import connection
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from src.core.middleware.correlation import get_correlation_id
from src.core.resilience import CircuitBreakerError, CircuitState, ResilientHttpError

POLICY_DEPENDENCY = "policy-engine"
POLICY_HEALTH_PATH = "/health/ready"
LOCAL_CANARY_PERMISSION = "security.readiness-canary:deny"

GLOBAL_TABLES = ("security_permissions",)
TENANT_TABLES = (
    "security_roles",
    "security_role_permissions",
    "security_user_roles",
    "security_permission_sets",
    "security_permission_set_permissions",
    "security_user_permission_sets",
    "security_field_security",
    "security_row_security_rules",
    "security_security_profiles",
    "security_profile_assignments",
    "security_audit_logs",
)
EXPECTED_TABLES = GLOBAL_TABLES + TENANT_TABLES


@dataclass(frozen=True, slots=True)
class ComponentResult:
    ready: bool
    code: str
    circuit_state: str | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": "ready" if self.ready else "unavailable",
            "code": self.code,
        }
        if self.circuit_state is not None:
            payload["circuit_state"] = self.circuit_state
        return payload


def _database_check() -> ComponentResult:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            ready = cursor.fetchone() == (1,)
        return ComponentResult(ready, "ready" if ready else "query_failed")
    except Exception:
        return ComponentResult(False, "dependency_unavailable")


def _schema_check() -> ComponentResult:
    try:
        tables = set(connection.introspection.table_names())
        ready = set(EXPECTED_TABLES).issubset(tables)
        return ComponentResult(ready, "ready" if ready else "schema_missing")
    except Exception:
        return ComponentResult(False, "dependency_unavailable")


def _rls_check() -> ComponentResult:
    if connection.vendor != "postgresql":
        # RLS is a mandatory security dependency, not an optional capability.
        # Test suites may substitute this probe at their composition boundary;
        # the security primitive itself always fails closed.
        return ComponentResult(False, "rls_unsupported")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                   FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = current_schema()
                     AND c.relname = ANY(%s)""",
                [list(TENANT_TABLES)],
            )
            flags = {row[0]: (bool(row[1]), bool(row[2])) for row in cursor.fetchall()}
            cursor.execute(
                """SELECT tablename, qual, with_check
                   FROM pg_policies
                   WHERE schemaname = current_schema()
                     AND tablename = ANY(%s)""",
                [list(TENANT_TABLES)],
            )
            policies: dict[str, bool] = {table: False for table in TENANT_TABLES}
            for table, using_expression, check_expression in cursor.fetchall():
                policies[table] = policies[table] or bool(using_expression and check_expression)
        ready = (
            set(flags) == set(TENANT_TABLES)
            and all(enabled and forced for enabled, forced in flags.values())
            and all(policies.values())
        )
        return ComponentResult(ready, "ready" if ready else "rls_missing")
    except Exception:
        return ComponentResult(False, "dependency_unavailable")


def _permission_catalog_check() -> ComponentResult:
    """Prove the global catalog can be read without exposing its contents."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM security_permissions LIMIT 1")
            cursor.fetchone()
        return ComponentResult(True, "ready")
    except Exception:
        return ComponentResult(False, "catalog_unavailable")


def _local_evaluator_check() -> ComponentResult:
    try:
        from .models import SecurityConfiguration, UserRole
        from .services import AccessEvaluationService

        evaluator = getattr(AccessEvaluationService, "evaluate_local", None)
        if not callable(evaluator):
            return ComponentResult(False, "evaluator_unavailable")

        # A readiness result must prove the evaluator and its tenant-owned
        # configuration work together.  The canary principal is explicitly
        # configured so this public probe never scans across tenant data.
        raw_tenant_id = getattr(settings, "SARAISE_SECURITY_CANARY_TENANT_ID", None)
        raw_user_id = getattr(settings, "SARAISE_SECURITY_CANARY_USER_ID", None)
        try:
            tenant_id = UUID(str(raw_tenant_id))
        except (TypeError, ValueError, AttributeError):
            return ComponentResult(False, "canary_fixture_missing")
        user_id = str(raw_user_id).strip()
        if not user_id:
            return ComponentResult(False, "canary_fixture_missing")
        principal_exists = (
            UserRole.objects.for_tenant(tenant_id)
            .filter(
                user_id=user_id,
                revoked_at__isnull=True,
            )
            .exists()
        )
        if not principal_exists:
            return ComponentResult(False, "canary_fixture_missing")
        configuration = SecurityConfiguration.objects.for_tenant(tenant_id).values("document", "version").first()
        if (
            configuration is None
            or not isinstance(configuration.get("document"), Mapping)
            or not configuration["document"]
            or not isinstance(configuration.get("version"), int)
            or configuration["version"] < 1
        ):
            return ComponentResult(False, "configuration_missing")
        result = evaluator(
            tenant_id,
            SimpleNamespace(id=user_id),
            LOCAL_CANARY_PERMISSION,
            resource_context={"readiness_canary": True},
            request=SimpleNamespace(correlation_id="readiness-canary"),
        )
        ready = result.allowed is False and tuple(result.reason_codes) == ("DENY_DEFAULT",)
        return ComponentResult(ready, "ready" if ready else "canary_did_not_deny")
    except (ImportError, AttributeError, TypeError, ValueError):
        return ComponentResult(False, "evaluator_unavailable")
    except Exception:
        # Database, configuration, or evaluator failures are deliberately
        # indistinguishable on the public readiness surface.
        return ComponentResult(False, "evaluator_unavailable")


def _remote_policy_check(correlation_id: str) -> ComponentResult:
    configured_url = getattr(settings, "SARAISE_POLICY_ENGINE_URL", None)
    if not isinstance(configured_url, str) or not configured_url.strip() or configured_url != configured_url.strip():
        return ComponentResult(False, "configuration_missing", "unknown")

    try:
        from .services import get_policy_http_client

        client = get_policy_http_client()
        breaker = client.get_breaker(POLICY_DEPENDENCY)
        state = getattr(breaker.state, "value", breaker.state)
        state_value = str(state) if state in tuple(CircuitState) else "unknown"
        if breaker.state == CircuitState.OPEN:
            return ComponentResult(False, "circuit_open", state_value)
        health_url = urljoin(f"{configured_url.rstrip('/')}/", POLICY_HEALTH_PATH.lstrip("/"))
        response = client.get(
            health_url,
            dependency=POLICY_DEPENDENCY,
            correlation_id=correlation_id,
            headers={"Accept": "application/json"},
        )
        ready = 200 <= response.status_code < 300
        updated_state = getattr(client.get_breaker(POLICY_DEPENDENCY).state, "value", "unknown")
        return ComponentResult(
            ready,
            "ready" if ready else "dependency_unavailable",
            str(updated_state),
        )
    except CircuitBreakerError:
        return ComponentResult(False, "circuit_open", "open")
    except (ResilientHttpError, ImportError, AttributeError, TypeError, ValueError):
        return ComponentResult(False, "dependency_unavailable", "unknown")
    except Exception:
        # A readiness endpoint must never leak an unexpected adapter or SDK
        # exception. The dependency remains unavailable until the cause is
        # repaired and a bounded probe succeeds.
        return ComponentResult(False, "dependency_unavailable", "unknown")


def _correlation_id() -> str:
    return get_correlation_id() or f"req_{uuid4().hex[:24]}"


def module_readiness(
    *,
    correlation_id: str | None = None,
    checks: Mapping[str, Callable[[], ComponentResult]] | None = None,
) -> tuple[dict[str, object], int]:
    """Return current readiness without counts, hosts, SQL, or exception text."""
    current_correlation_id = correlation_id or _correlation_id()
    selected_checks = checks or {
        "database": _database_check,
        "schema": _schema_check,
        "row_level_security": _rls_check,
        "permission_catalog": _permission_catalog_check,
    }
    results = {name: probe() for name, probe in selected_checks.items()}
    mode = getattr(settings, "SARAISE_MODE", None)
    if mode in {"development", "self-hosted"}:
        results["policy_evaluator"] = _local_evaluator_check()
    elif mode == "saas":
        results["policy_dependency"] = _remote_policy_check(current_correlation_id)
    else:
        results["policy_evaluator"] = ComponentResult(False, "mode_invalid")

    ready = all(result.ready for result in results.values())
    payload: dict[str, object] = {
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "correlation_id": current_correlation_id,
        "checked_at": timezone.now().isoformat(),
        "components": {name: result.as_dict() for name, result in results.items()},
    }
    return payload, 200 if ready else 503


@api_view(["GET"])
@permission_classes([AllowAny])
def check_security_module_health(request: Request) -> Response:
    """Public readiness endpoint containing operational state only."""
    del request
    payload, status_code = module_readiness()
    return Response(payload, status=status_code)


__all__ = [
    "EXPECTED_TABLES",
    "GLOBAL_TABLES",
    "LOCAL_CANARY_PERMISSION",
    "POLICY_DEPENDENCY",
    "POLICY_HEALTH_PATH",
    "TENANT_TABLES",
    "ComponentResult",
    "check_security_module_health",
    "module_readiness",
]
