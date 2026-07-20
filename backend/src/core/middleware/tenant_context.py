"""Bind an authenticated profile tenant to PostgreSQL RLS for one request."""

from __future__ import annotations

from typing import Callable

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from src.core.tenancy.rls import InvalidTenantContext, tenant_context


class TenantContextMiddleware:
    """
    Sets PostgreSQL session variables for Row-Level Security.

    Must be placed AFTER authentication middleware in the MIDDLEWARE stack.
    The context manager owns the transaction required by ``SET LOCAL``.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        tenant_id = self._get_tenant_id(request)
        if tenant_id is None:
            return self.get_response(request)

        try:
            with tenant_context(tenant_id):
                return self.get_response(request)
        except InvalidTenantContext as exc:
            raise PermissionDenied("Authenticated user has an invalid tenant context") from exc

    def _get_tenant_id(self, request: HttpRequest) -> str | None:
        """Extract tenant_id from request context."""
        user = getattr(request, "user", None)
        if user and hasattr(user, "is_authenticated") and user.is_authenticated:
            profile = getattr(user, "profile", None)
            return getattr(profile, "tenant_id", None)
        return None
