"""Sanitized liveness/readiness endpoint for AI-provider configuration."""

from __future__ import annotations

from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.encryption import EncryptionService

from .api import TenantContextMixin
from .models import AIProviderCredential
from .permissions import AIProviderActionPermission, SessionAuthentication401, TenantProviderThrottle

DOMAIN_TABLES = frozenset(
    {
        "ai_provider_configuration_providers",
        "ai_provider_configuration_credentials",
        "ai_provider_configuration_models",
        "ai_provider_configuration_deployments",
        "ai_provider_configuration_usage_logs",
    }
)


class HealthView(TenantContextMixin, APIView):
    """Return no row counts, identifiers, URLs, credentials, or exception text."""

    authentication_classes = (SessionAuthentication401,)
    permission_classes = (AIProviderActionPermission,)
    throttle_classes = (TenantProviderThrottle,)
    action = "health"
    action_permissions = {"health": "ai_provider_configuration.health:read"}

    def get(self, request: object) -> Response:
        del request
        tenant_id = self.tenant_id()
        checks: dict[str, dict[str, str]] = {}
        ready = True

        try:
            tables = set(connection.introspection.table_names())
            schema_ready = DOMAIN_TABLES.issubset(tables)
            checks["database"] = {"status": "healthy" if schema_ready else "unavailable"}
            ready = ready and schema_ready
        except Exception:
            checks["database"] = {"status": "unavailable"}
            ready = False

        try:
            probe = EncryptionService.encrypt("health-probe")
            encryption_ready = EncryptionService.decrypt(probe) == "health-probe"
            checks["encryption"] = {"status": "healthy" if encryption_ready else "unavailable"}
            ready = ready and encryption_ready
        except Exception:
            checks["encryption"] = {"status": "unavailable"}
            ready = False

        try:
            # Execute a tenant-scoped query while deliberately suppressing the
            # count so health cannot become a tenant metadata oracle.
            AIProviderCredential.objects.for_tenant(tenant_id).filter(is_deleted=False).exists()
            checks["tenant_store"] = {"status": "healthy"}
        except Exception:
            checks["tenant_store"] = {"status": "unavailable"}
            ready = False

        payload = {
            "module": "ai-provider-configuration",
            "status": "healthy" if ready else "unhealthy",
            "live": True,
            "ready": ready,
            "checked_at": timezone.now().isoformat(),
            "checks": checks,
        }
        return Response(payload, status=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE)


health_check = HealthView.as_view()


__all__ = ["HealthView", "health_check"]
