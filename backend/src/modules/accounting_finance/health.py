"""
Health check functions for Accounting & Finance module.
"""

from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for accounting_finance module."""
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return JsonResponse(
            {
                "status": "healthy",
                "module": "accounting_finance",
                "database": "connected",
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse(
            {
                "status": "unhealthy",
                "module": "accounting_finance",
                "error": str(e),
            },
            status=503,
        )
