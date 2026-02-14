"""
Health check functions for Multi-Company module.
"""

from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for multi_company module."""
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return JsonResponse(
            {
                "status": "healthy",
                "module": "multi_company",
                "database": "connected",
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse(
            {
                "status": "unhealthy",
                "module": "multi_company",
                "error": str(e),
            },
            status=503,
        )
