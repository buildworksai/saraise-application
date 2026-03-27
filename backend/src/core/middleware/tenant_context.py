"""
Tenant context middleware for PostgreSQL Row-Level Security.

SARAISE-33001: Sets PostgreSQL session variable for RLS enforcement.

This middleware runs on every request and sets:
- app.current_tenant_id: The authenticated user's tenant_id
- app.is_superuser: Whether the user is a system admin (bypasses RLS)

These variables are read by PostgreSQL RLS policies to enforce
tenant isolation at the database level.
"""

from __future__ import annotations

import logging
from typing import Callable

from django.conf import settings
from django.db import connection
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("saraise.middleware.tenant")


class TenantContextMiddleware:
    """
    Sets PostgreSQL session variables for Row-Level Security.

    Must be placed AFTER authentication middleware in the MIDDLEWARE stack.
    Only active when using PostgreSQL (skipped for SQLite in tests).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Skip for non-PostgreSQL backends (e.g., SQLite in tests)
        if "postgresql" not in settings.DATABASES.get("default", {}).get("ENGINE", ""):
            return self.get_response(request)

        # Extract tenant_id from authenticated user
        tenant_id = self._get_tenant_id(request)
        is_superuser = self._is_superuser(request)

        if tenant_id or is_superuser:
            try:
                with connection.cursor() as cursor:
                    if tenant_id:
                        cursor.execute("SET LOCAL app.current_tenant_id = %s", [tenant_id])
                    if is_superuser:
                        cursor.execute("SET LOCAL app.is_superuser = %s", ["true"])
            except Exception:
                logger.exception("Failed to set tenant context for RLS")

        return self.get_response(request)

    def _get_tenant_id(self, request: HttpRequest) -> str | None:
        """Extract tenant_id from request context."""
        user = getattr(request, "user", None)
        if user and hasattr(user, "is_authenticated") and user.is_authenticated:
            return getattr(user, "tenant_id", None)
        return None

    def _is_superuser(self, request: HttpRequest) -> bool:
        """Check if user is a system-level superuser."""
        user = getattr(request, "user", None)
        if user and hasattr(user, "is_authenticated") and user.is_authenticated:
            if getattr(user, "is_superuser", False):
                return True
            roles = getattr(user, "roles", [])
            if "super_admin" in roles or "system_admin" in roles:
                return True
        return False
