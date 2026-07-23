"""Sanitized, fail-closed readiness for the governed runtime."""

from __future__ import annotations

from datetime import timedelta
from time import monotonic
from uuid import UUID

from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.access.permissions import RequiresAccess
from src.core.api import GovernedAPIViewMixin
from src.core.async_jobs.models import OutboxEvent
from src.core.async_jobs.services import get_handler
from src.core.auth_utils import get_user_tenant_id

from .authentication import GovernedSessionAuthentication
from .providers.factory import get_provider_factory
from .providers.registry import get_registry as get_provider_registry
from .registries import runner_registry
from .services import ConfigurationService, EXECUTE_COMMAND


def _probe(operation) -> dict[str, object]:
    started = monotonic()
    try:
        operation()
        state = "healthy"
    except Exception:
        state = "unavailable"
    return {"status": state, "latency_ms": round((monotonic() - started) * 1000, 2)}


class ModuleHealthView(GovernedAPIViewMixin, APIView):
    authentication_classes = (GovernedSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    required_permission = "ai.health:view"
    required_entitlement = "ai.health:view"
    quota_resource = "ai.health:view"
    quota_cost = 1

    def check_permissions(self, request) -> None:
        tenant = get_user_tenant_id(request.user)
        if tenant:
            request.tenant_id = UUID(str(tenant))
        super().check_permissions(request)

    def get(self, request):
        tenant = UUID(str(get_user_tenant_id(request.user)))
        configuration = ConfigurationService.resolve(tenant)["health"]

        def database() -> None:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    raise RuntimeError

        def cache_probe() -> None:
            key = f"ai-agent-management:health:{tenant}"
            cache.set(key, "ok", timeout=int(configuration["cache_probe_timeout_seconds"]))
            if cache.get(key) != "ok":
                raise RuntimeError

        def rls() -> None:
            if connection.vendor != "postgresql":
                raise RuntimeError
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE c.relname LIKE 'ai_%%' AND c.relrowsecurity AND c.relforcerowsecurity"
                )
                if int(cursor.fetchone()[0]) < int(configuration["minimum_rls_table_count"]):
                    raise RuntimeError

        def handler() -> None:
            get_handler(EXECUTE_COMMAND)

        def outbox() -> None:
            cutoff = timezone.now() - timedelta(minutes=int(configuration["outbox_stale_minutes"]))
            if OutboxEvent.objects.filter(
                tenant_id=tenant, status="pending", available_at__lte=cutoff
            ).exists():
                raise RuntimeError

        def extensions() -> None:
            if not runner_registry.keys():
                raise RuntimeError

        def provider() -> None:
            if not get_provider_factory().is_configured or not get_provider_registry().list_providers():
                raise RuntimeError

        # Provider adapters own canonical resilient-client breakers; an
        # unavailable provider projection therefore also denies circuit
        # readiness without exposing a dependency name or state.
        components = {
            "database": _probe(database),
            "cache": _probe(cache_probe),
            "rls": _probe(rls),
            "execution_handler": _probe(handler),
            "outbox": _probe(outbox),
            "extension_registry": _probe(extensions),
            "provider": _probe(provider),
            "circuit": _probe(provider),
        }
        healthy = all(item["status"] == "healthy" for item in components.values())
        payload = {
            "status": "healthy" if healthy else "unavailable",
            "module": "ai_agent_management",
            "components": components,
        }
        return Response(payload, status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE)


health_check = ModuleHealthView.as_view()
