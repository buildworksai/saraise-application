"""Truthful readiness checks for the inventory module."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.api import GovernedAPIViewMixin
from src.core.async_jobs.models import OutboxEvent
from src.core.tenancy import tenant_context

from .extensions import health_contributors
from .models import InventoryConfiguration
from .permissions import HEALTH_READ, InventoryAccessMixin

logger = logging.getLogger(__name__)

INVENTORY_TABLES = (
    "inventory_warehouses", "inventory_storage_locations", "inventory_items",
    "inventory_batches", "inventory_serial_numbers", "inventory_stock_entries",
    "inventory_stock_entry_lines", "inventory_stock_ledger_entries", "inventory_stock_cost_layers",
    "inventory_stock_balances", "inventory_stock_reservations", "inventory_cycle_counts",
    "inventory_cycle_count_lines", "inventory_configurations", "inventory_configuration_revisions",
)


def _environment() -> str:
    return "development" if getattr(settings, "SARAISE_MODE", "development") == "development" else "production"


def _rls_status() -> tuple[bool, dict[str, str]]:
    """Verify every inventory table has both RLS and FORCE RLS enabled."""

    if connection.vendor != "postgresql":
        return False, {"status": "unhealthy", "reason_code": "postgresql_rls_unavailable"}
    placeholders = ",".join(["%s"] * len(INVENTORY_TABLES))
    with connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                       COUNT(p.policyname)
                  FROM pg_class c
                  JOIN pg_namespace n ON n.oid = c.relnamespace
             LEFT JOIN pg_policies p
                    ON p.schemaname = n.nspname AND p.tablename = c.relname
                 WHERE c.relname IN ({placeholders})
              GROUP BY c.relname, c.relrowsecurity, c.relforcerowsecurity""",  # noqa: S608 - placeholders only
            list(INVENTORY_TABLES),
        )
        states = {name: (enabled, forced, policies) for name, enabled, forced, policies in cursor.fetchall()}
    ready = len(states) == len(INVENTORY_TABLES) and all(
        enabled and forced and policies > 0 for enabled, forced, policies in states.values()
    )
    return ready, {"status": "healthy" if ready else "unhealthy", "reason_code": "ready" if ready else "rls_policy_incomplete"}


def module_health(tenant_id: UUID, environment: str | None = None) -> tuple[dict[str, Any], int]:
    """Run fail-closed critical checks without exposing data or SQL errors."""

    components: dict[str, dict[str, Any]] = {}
    critical_failure = False
    degraded = False

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                raise RuntimeError("database probe returned an unexpected result")
        components["database"] = {"status": "healthy", "reason_code": "ready"}
    except Exception:
        logger.exception("inventory database health probe failed", extra={"event": "inventory.health.database_failed"})
        components["database"] = {"status": "unhealthy", "reason_code": "database_unavailable"}
        critical_failure = True

    if not critical_failure:
        try:
            with tenant_context(tenant_id):
                components["tenant_context"] = {"status": "healthy", "reason_code": "ready"}
                config = InventoryConfiguration.objects.for_tenant(tenant_id).filter(
                    environment=environment or _environment(), status="active"
                ).first()
                if config is None:
                    components["configuration"] = {"status": "unhealthy", "reason_code": "active_configuration_missing"}
                    critical_failure = True
                else:
                    try:
                        config.full_clean()
                    except ValidationError:
                        components["configuration"] = {"status": "unhealthy", "reason_code": "active_configuration_invalid"}
                        critical_failure = True
                    else:
                        components["configuration"] = {"status": "healthy", "reason_code": "ready"}
                        if any(bool(value) for value in config.enabled_capabilities.values()):
                            stale_before = timezone.now() - timedelta(minutes=5)
                            stale = OutboxEvent.objects.filter(
                                tenant_id=tenant_id, status="pending", available_at__lt=stale_before
                            ).exists()
                            components["async_outbox"] = {
                                "status": "degraded" if stale else "healthy",
                                "reason_code": "dispatch_delayed" if stale else "ready",
                            }
                            degraded = degraded or stale
                        else:
                            components["async_outbox"] = {"status": "healthy", "reason_code": "not_enabled"}
        except Exception:
            logger.exception("inventory tenancy/configuration health probe failed", extra={"event": "inventory.health.tenancy_failed"})
            components["tenant_context"] = {"status": "unhealthy", "reason_code": "tenant_context_unavailable"}
            components.setdefault("configuration", {"status": "unhealthy", "reason_code": "configuration_unavailable"})
            critical_failure = True

    if not critical_failure:
        try:
            rls_ready, rls_component = _rls_status()
            components["rls"] = rls_component
            critical_failure = not rls_ready
        except Exception:
            logger.exception("inventory RLS health probe failed", extra={"event": "inventory.health.rls_failed"})
            components["rls"] = {"status": "unhealthy", "reason_code": "rls_check_unavailable"}
            critical_failure = True

    extension_results: list[dict[str, str]] = []
    for contributor in health_contributors():
        try:
            result = contributor.check()
            extension_results.append({
                "name": result.name,
                "status": "healthy" if result.healthy else "degraded",
                "breaker_state": result.breaker_state,
                "reason_code": result.reason_code,
            })
            degraded = degraded or not result.healthy
        except Exception:
            logger.exception("inventory extension health contributor failed", extra={"event": "inventory.health.extension_failed"})
            extension_results.append({"name": "registered_extension", "status": "degraded", "breaker_state": "unknown", "reason_code": "probe_failed"})
            degraded = True
    components["extensions"] = {
        "status": "degraded" if any(item["status"] != "healthy" for item in extension_results) else "healthy",
        "reason_code": "dependency_degraded" if degraded and extension_results else "ready",
        "dependencies": extension_results,
    }

    overall = "unhealthy" if critical_failure else "degraded" if degraded else "healthy"
    payload = {"status": overall, "module": "inventory_management", "components": components, "checked_at": timezone.now().isoformat()}
    return payload, status.HTTP_503_SERVICE_UNAVAILABLE if critical_failure else status.HTTP_200_OK


class InventoryHealthView(GovernedAPIViewMixin, InventoryAccessMixin, APIView):  # type: ignore[misc]
    """Governed tenant-specific inventory readiness endpoint."""

    action_permissions = {"get": HEALTH_READ}

    def get_permissions(self) -> list[object]:
        self.action = self.request.method.lower()
        return super().get_permissions()

    def get(self, request: Request) -> Response:
        tenant = getattr(request, "tenant_id", None)
        if not isinstance(tenant, UUID):
            raise PermissionDenied("Authenticated tenant context is required.")
        payload, code = module_health(tenant)
        return Response(payload, status=code)


# Legacy callable name retained for URL reverse/import compatibility only.
health_check = InventoryHealthView.as_view()


__all__ = ["INVENTORY_TABLES", "InventoryHealthView", "health_check", "module_health"]
