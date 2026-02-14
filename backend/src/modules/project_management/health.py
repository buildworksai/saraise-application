"""
Health check functions for Project Management module.
"""

from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for project_management module."""
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return JsonResponse(
            {
                "status": "healthy",
                "module": "project_management",
                "database": "connected",
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse(
            {
                "status": "unhealthy",
                "module": "project_management",
                "error": str(e),
            },
            status=503,
        )
