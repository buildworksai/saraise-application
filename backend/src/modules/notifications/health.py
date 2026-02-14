"""
Health check functions for Notifications module.
"""

from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for notifications module."""
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return JsonResponse(
            {
                "status": "healthy",
                "module": "notifications",
                "database": "connected",
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse(
            {
                "status": "unhealthy",
                "module": "notifications",
                "error": str(e),
            },
            status=503,
        )
