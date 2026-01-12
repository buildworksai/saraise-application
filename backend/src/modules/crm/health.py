"""
Health check endpoint for CRM module.
"""

from django.core.cache import cache
from django.db import connection
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Lead, Opportunity


@api_view(["GET"])
def health_check(request):
    """
    Health check endpoint.

    Checks:
    - Database connectivity
    - Redis connectivity
    - Module-specific health

    Returns:
    - 200 OK if healthy
    - 503 Service Unavailable if unhealthy
    """
    health_status = {"status": "healthy", "module": "crm", "checks": {}}

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
        cache.set("crm_health_check", "ok", timeout=10)
        result = cache.get("crm_health_check")
        if result == "ok":
            health_status["checks"]["redis"] = "ok"
        else:
            health_status["status"] = "unhealthy"
            health_status["checks"]["redis"] = "error: cache read failed"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["redis"] = f"error: {str(e)}"

    # Check module data access
    try:
        leads_count = Lead.objects.filter(is_deleted=False).count()
        opportunities_count = Opportunity.objects.filter(is_deleted=False).count()
        health_status["checks"]["module_data"] = {
            "status": "ok",
            "leads_count": leads_count,
            "opportunities_count": opportunities_count,
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["module_data"] = f"error: {str(e)}"

    status_code = 200 if health_status["status"] == "healthy" else 503
    return Response(health_status, status=status_code)
