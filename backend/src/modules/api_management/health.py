"""Sanitized tenant-scoped dependency probes."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.core.cache import cache
from django.db import connection

from .models import ApiManagementResource

logger = logging.getLogger(__name__)


def module_health(*, tenant_id: uuid.UUID, cache_ttl_seconds: int, correlation_id: str) -> tuple[dict[str, Any], int]:
    """Return operational status without counts or exception disclosure."""

    if not isinstance(correlation_id, str) or not correlation_id.strip():
        raise ValueError("correlation_id is required for health diagnostics.")
    correlation_id = correlation_id.strip()
    checks: dict[str, str] = {}
    overall = "healthy"
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception:
        logger.exception(
            "api_management database health probe failed",
            extra={"tenant_id": str(tenant_id), "correlation_id": correlation_id},
        )
        checks["database"] = "dependency_unavailable"
        overall = "unhealthy"

    try:
        key = f"health_check_api_management:{tenant_id}"
        cache.set(key, "ok", cache_ttl_seconds)
        if cache.get(key) == "ok":
            checks["cache"] = "ok"
        else:
            checks["cache"] = "invalid_response"
            overall = "degraded" if overall == "healthy" else overall
    except Exception:
        logger.exception(
            "api_management cache health probe failed",
            extra={"tenant_id": str(tenant_id), "correlation_id": correlation_id},
        )
        checks["cache"] = "dependency_unavailable"
        overall = "unhealthy"

    try:
        ApiManagementResource.objects.filter(tenant_id=tenant_id).exists()
        checks["module_model"] = "ok"
    except Exception:
        logger.exception(
            "api_management model health probe failed",
            extra={"tenant_id": str(tenant_id), "correlation_id": correlation_id},
        )
        checks["module_model"] = "dependency_unavailable"
        overall = "unhealthy"

    return (
        {"status": overall, "module": "api-management", "checks": checks},
        200 if overall == "healthy" else 503,
    )


__all__ = ["module_health"]
