"""
Health check functions for Master Data Management module.
"""

from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for master_data_management module."""
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return JsonResponse(
            {
                "status": "healthy",
                "module": "master_data_management",
                "database": "connected",
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse(
            {
                "status": "unhealthy",
                "module": "master_data_management",
                "error": str(e),
            },
            status=503,
        )
