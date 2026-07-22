"""Non-invasive health checks for budget management and its dependencies."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from django.db import connection, transaction
from django.http import JsonResponse
from django.utils import timezone

from src.core.async_jobs.services import enqueue
from src.core.tenancy import get_current_tenant_id

from .integrations import get_integrations


@dataclass(frozen=True, slots=True)
class HealthResult:
    status: str
    module: str
    checked_at: str
    dependencies: dict[str, str]


def _adapter_state(adapter: Any | None) -> str:
    if adapter is None:
        return "not_configured"
    state = getattr(adapter, "health_state", None)
    if not callable(state):
        return "configured"
    try:
        value = str(state()).lower()
    except Exception:
        return "unknown"
    return value if value in {"closed", "open", "half_open", "configured"} else "unknown"


def check_health(tenant_id: UUID) -> HealthResult:
    """Check critical persistence and optional adapter state without I/O calls."""

    dependencies: dict[str, str] = {}
    critical_failure = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                raise RuntimeError("unexpected database probe result")
        dependencies["database"] = "healthy"
    except Exception:
        dependencies["database"] = "unhealthy"
        critical_failure = True

    active_tenant = get_current_tenant_id()
    if active_tenant != tenant_id:
        dependencies["tenant_context"] = "unhealthy"
        critical_failure = True
    else:
        dependencies["tenant_context"] = "healthy"

    if connection.vendor == "postgresql":
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regprocedure('saraise_enable_rls(regclass)') IS NOT NULL")
                available = bool(cursor.fetchone()[0])
            dependencies["rls"] = "healthy" if available else "unhealthy"
            critical_failure = critical_failure or not available
        except Exception:
            dependencies["rls"] = "unhealthy"
            critical_failure = True
    else:
        # Development databases cannot prove RLS, but this is visible rather
        # than mislabeled healthy. PostgreSQL production deployments must pass.
        dependencies["rls"] = "not_applicable"

    try:
        with transaction.atomic():
            enqueue(
                tenant_id,
                uuid.UUID(int=0),
                "budget_management.health_probe",
                {},
                f"health:{uuid.uuid4()}",
            )
            transaction.set_rollback(True)
        dependencies["durable_jobs"] = "healthy"
    except Exception:
        dependencies["durable_jobs"] = "unhealthy"
        critical_failure = True

    adapters = get_integrations()
    dependencies["accounting"] = _adapter_state(adapters.accounting)
    dependencies["workflow"] = _adapter_state(adapters.workflow)
    dependencies["notification"] = _adapter_state(adapters.notification)
    optional_degraded = any(
        dependencies[name] not in {"closed", "configured"}
        for name in ("accounting", "workflow", "notification")
    )
    status = "unhealthy" if critical_failure else "degraded" if optional_degraded else "healthy"
    return HealthResult(status, "budget_management", timezone.now().isoformat(), dependencies)


def get_module_health(tenant_id: UUID) -> dict[str, Any]:
    """Return the serializer-ready governed health projection."""

    result = check_health(tenant_id)
    return {
        "status": result.status,
        "checked_at": result.checked_at,
        "dependencies": dict(result.dependencies),
    }


def health_check(request: Any) -> JsonResponse:
    """Compatibility view; governed API views may call :func:`check_health`."""

    raw_tenant = getattr(request, "tenant_id", None) or get_current_tenant_id()
    try:
        tenant_id = raw_tenant if isinstance(raw_tenant, UUID) else UUID(str(raw_tenant))
    except (TypeError, ValueError, AttributeError):
        result = HealthResult(
            "unhealthy",
            "budget_management",
            timezone.now().isoformat(),
            {"tenant_context": "unhealthy"},
        )
    else:
        result = check_health(tenant_id)
    payload = asdict(result)
    return JsonResponse(payload, status=503 if result.status == "unhealthy" else 200)


__all__ = ["HealthResult", "check_health", "get_module_health", "health_check"]
