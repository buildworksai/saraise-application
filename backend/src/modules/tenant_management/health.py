"""
Tenant Management Health Check.

Health check endpoint for Tenant Management module.
"""

from django.core.cache import cache
from django.db import connection
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Tenant


@api_view(["GET"])
def health_check(request):
    """
    Health check endpoint for Tenant Management module.

    Returns:
        - Database connectivity status
        - Redis connectivity status
        - Tenant count statistics
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
        cache.set("tenant_management_health_check", "ok", timeout=10)
        result = cache.get("tenant_management_health_check")
        if result == "ok":
            health_status["checks"]["redis"] = "ok"
        else:
            health_status["status"] = "unhealthy"
            health_status["checks"]["redis"] = "error: cache read failed"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["redis"] = f"error: {str(e)}"

    # Check tenant statistics
    try:
        total_tenants = Tenant.objects.count()
        active_tenants = Tenant.objects.filter(status=Tenant.TenantStatus.ACTIVE).count()
        trial_tenants = Tenant.objects.filter(status=Tenant.TenantStatus.TRIAL).count()

        health_status["checks"]["tenants"] = {
            "status": "ok",
            "total": total_tenants,
            "active": active_tenants,
            "trial": trial_tenants,
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["tenants"] = f"error: {str(e)}"

    status_code = 200 if health_status["status"] == "healthy" else 503
    return Response(health_status, status=status_code)
