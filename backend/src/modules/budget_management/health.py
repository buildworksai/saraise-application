"""
Health check functions for Budget Management module.
"""

from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for budget_management module."""
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return JsonResponse(
            {
                "status": "healthy",
                "module": "budget_management",
                "database": "connected",
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse(
            {
                "status": "unhealthy",
                "module": "budget_management",
                "error": str(e),
            },
            status=503,
        )
