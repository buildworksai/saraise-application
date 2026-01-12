"""
Security & Access Control Health Check.

Health check endpoint for Security & Access Control module.
"""

from django.core.cache import cache
from django.db import connection
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Permission, Role


@api_view(["GET"])
def check_security_module_health(request):
    """
    Health check endpoint for Security & Access Control module.

    Returns:
        - Database connectivity status
        - Redis connectivity status
        - Role and permission statistics
    """
    health_status = {"status": "healthy", "checks": {}}

    # Check database connectivity
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_status["checks"]["database"] = "ok"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = f"error: {str(e)}"

    # Check Redis connectivity
    try:
        cache.set("security_access_control_health_check", "ok", timeout=10)
        result = cache.get("security_access_control_health_check")
        if result == "ok":
            health_status["checks"]["redis"] = "ok"
        else:
            health_status["status"] = "unhealthy"
            health_status["checks"]["redis"] = "error: cache read failed"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["redis"] = f"error: {str(e)}"

    # Check role and permission statistics
    try:
        total_roles = Role.objects.count()
        active_roles = Role.objects.filter(is_active=True).count()
        total_permissions = Permission.objects.count()

        health_status["checks"]["security"] = {
            "status": "ok",
            "total_roles": total_roles,
            "active_roles": active_roles,
            "total_permissions": total_permissions,
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["security"] = f"error: {str(e)}"

    status_code = 200 if health_status["status"] == "healthy" else 503
    return Response(health_status, status=status_code)
