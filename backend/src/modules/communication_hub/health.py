"""
Health check functions for Communication Hub module.
"""

from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for communication_hub module."""
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return JsonResponse(
            {
                "status": "healthy",
                "module": "communication_hub",
                "database": "connected",
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse(
            {
                "status": "unhealthy",
                "module": "communication_hub",
                "error": str(e),
            },
            status=503,
        )
