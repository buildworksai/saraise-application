"""
Health check functions for Asset Management module.
"""

import logging

from django.db import connection

logger = logging.getLogger("saraise.asset_management")


class AssetHealthUnavailable(Exception):
    """Stable sanitized health failure."""


def get_module_health(correlation_id: str | None = None) -> dict[str, str]:
    """Return sanitized module health evidence or raise for the API layer."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return {
            "status": "healthy",
            "module": "asset_management",
            "database": "connected",
        }
    except Exception:
        logger.exception(
            "asset_management.health.database_unavailable",
            extra={
                "event": "asset_management.health.database_unavailable",
                "correlation_id": correlation_id or "missing-context",
            },
        )
        raise AssetHealthUnavailable("Asset Management database connectivity is unavailable.")


__all__ = ["AssetHealthUnavailable", "get_module_health"]
