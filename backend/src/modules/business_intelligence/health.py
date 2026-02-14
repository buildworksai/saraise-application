"""
Health check functions for Business Intelligence module.
"""

from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for business_intelligence module."""
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return JsonResponse(
            {
                "status": "healthy",
                "module": "business_intelligence",
                "database": "connected",
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse(
            {
                "status": "unhealthy",
                "module": "business_intelligence",
                "error": str(e),
            },
            status=503,
        )
