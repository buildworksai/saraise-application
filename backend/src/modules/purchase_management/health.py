"""Authenticated non-leaking procurement readiness projection."""

from django.db import connection
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.api import GovernedAPIViewMixin
from src.core.async_jobs.models import OutboxEvent, OutboxStatus
from src.core.state_machine import registry
from src.core.tenancy.registry import TENANT_SCOPED, get_model_scope

from .integrations import adapter_status
from .models import ProcurementConfiguration, Supplier
from .permissions import PurchaseRequiresAccess


class ModuleHealthView(GovernedAPIViewMixin, APIView):
    permission_classes = (IsAuthenticated, PurchaseRequiresAccess)
    required_permission = "purchase_management.health:read"
    required_entitlement = required_permission
    quota_resource = required_permission
    quota_cost = 1

    def get(self, request):
        checks = {
            "registration": False,
            "database": False,
            "state_machines": False,
            "migrations_rls": False,
            "outbox": False,
            "integrations": {},
        }
        try:
            checks["registration"] = get_model_scope(Supplier) == TENANT_SCOPED
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                checks["database"] = cursor.fetchone() == (1,)
            checks["state_machines"] = all(
                f"purchase_management.{name}" in registry.names()
                for name in ("requisition", "rfq", "quote", "order", "receipt")
            )
            tables = set(connection.introspection.table_names())
            required = {
                "purchase_suppliers",
                "purchase_requisitions",
                "purchase_rfqs",
                "purchase_supplier_quotes",
                "purchase_orders",
                "purchase_receipts",
                "purchase_configurations",
            }
            checks["migrations_rls"] = required <= tables
            pending = (
                OutboxEvent.objects.filter(event_type__startswith="purchase.", status=OutboxStatus.PENDING)
                .order_by("created_at")
                .first()
            )
            checks["outbox"] = {
                "available": "async_job_outbox_events" in tables,
                "oldest_pending_age_seconds": (
                    max(0, int((timezone.now() - pending.created_at).total_seconds())) if pending else None
                ),
            }
            checks["integrations"] = adapter_status()
        except Exception:
            pass
        required_ok = all(checks[key] for key in ("registration", "database", "state_machines", "migrations_rls"))
        integration_required = (
            ProcurementConfiguration.objects.filter(status="active").filter(inventory_integration_enabled=True).exists()
        )
        status_value = (
            "healthy" if required_ok and not integration_required else "degraded" if checks["database"] else "unhealthy"
        )
        return Response({"status": status_value, "checks": checks})


health_check = ModuleHealthView.as_view()
