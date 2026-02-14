"""
Health check functions for Fixed Assets module.
"""

from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for fixed_assets module."""
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return JsonResponse(
            {
                "status": "healthy",
                "module": "fixed_assets",
                "database": "connected",
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse(
            {
                "status": "unhealthy",
                "module": "fixed_assets",
                "error": str(e),
            },
            status=503,
        )
