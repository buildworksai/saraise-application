"""Non-leaking dependency health for the project-management capability."""
from django.apps import apps
from django.db import connection
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from src.core.access import RequiresAccess
from src.core.api import GovernedAPIViewMixin
from src.core.auth_utils import get_user_tenant_id
from .services import ConfigurationService


def get_module_health(tenant_id):
    checks = {"database": "unhealthy", "tenant_context": "unhealthy", "configuration": "unhealthy", "human_resources": "not_enabled"}
    try:
        with connection.cursor() as cursor: cursor.execute("SELECT 1"); cursor.fetchone()
        checks["database"] = "healthy"
        if tenant_id:
            checks["tenant_context"] = "healthy"
            ConfigurationService.get_active(tenant_id, ConfigurationService.runtime_environment())
            checks["configuration"] = "healthy"
        if apps.is_installed("src.modules.human_resources"):
            checks["human_resources"] = "ready"
    except Exception:
        outcome = "unhealthy" if checks["database"] == "unhealthy" else "degraded"
        return {"status": outcome, "module": "project_management", "checks": checks}
    return {"status": "healthy" if all(v in {"healthy", "ready", "not_enabled"} for v in checks.values()) else "degraded", "module": "project_management", "checks": checks}


class ProjectManagementHealthView(GovernedAPIViewMixin, APIView):
    permission_classes = (IsAuthenticated, RequiresAccess("project_management.health:read"))
    required_entitlement = "project_management.core"
    def get(self, request):
        result = get_module_health(get_user_tenant_id(request.user))
        return Response(result, status=status.HTTP_200_OK if result["status"] != "unhealthy" else status.HTTP_503_SERVICE_UNAVAILABLE)


health_check = ProjectManagementHealthView.as_view()
