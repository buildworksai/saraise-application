"""
Health check functions for Bank Reconciliation module.
"""

from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for bank_reconciliation module."""
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return JsonResponse(
            {
                "status": "healthy",
                "module": "bank_reconciliation",
                "database": "connected",
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse(
            {
                "status": "unhealthy",
                "module": "bank_reconciliation",
                "error": str(e),
            },
            status=503,
        )
