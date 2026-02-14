"""
Health check functions for Human Resources module.
"""

from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for human_resources module."""
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return JsonResponse(
            {
                "status": "healthy",
                "module": "human_resources",
                "database": "connected",
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse(
            {
                "status": "unhealthy",
                "module": "human_resources",
                "error": str(e),
            },
            status=503,
        )
