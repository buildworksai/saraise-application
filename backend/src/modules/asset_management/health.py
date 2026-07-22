"""
Health check functions for Asset Management module.
"""

import logging

from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger("saraise.asset_management")


def health_check(request):
    """Health check endpoint for asset_management module."""
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return JsonResponse(
            {
                "status": "healthy",
                "module": "asset_management",
                "database": "connected",
            },
            status=200,
        )
    except Exception:
        logger.exception(
            "asset_management.health.database_unavailable",
            extra={
                "event": "asset_management.health.database_unavailable",
                "correlation_id": request.headers.get("X-Correlation-ID", "unavailable"),
            },
        )
        return JsonResponse(
            {
                "status": "unhealthy",
                "module": "asset_management",
                "error_code": "DATABASE_UNAVAILABLE",
                "message": "Asset Management database connectivity is unavailable.",
            },
            status=503,
        )
