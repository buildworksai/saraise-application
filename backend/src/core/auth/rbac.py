"""
RBAC enforcement utilities for SARAISE DRF views.

SARAISE-26001: Role-based access control MUST be enforced on all endpoints.

Usage:
    from src.core.auth.rbac import require_roles, require_permissions

    class InvoiceViewSet(ModelViewSet):
        required_permissions = ["accounting.view_invoice"]

    @require_roles("tenant_admin", "finance_manager")
    class BudgetViewSet(ModelViewSet):
        ...
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request

logger = logging.getLogger("saraise.auth.rbac")


def require_roles(*roles: str) -> Callable:
    """
    Class decorator that enforces role-based access on a DRF ViewSet.

    Usage:
        @require_roles("tenant_admin", "finance_manager")
        class BudgetViewSet(ModelViewSet):
            ...

    The user must have at least ONE of the specified roles.
    """

    def decorator(view_class: type) -> type:
        original_check = getattr(view_class, "check_permissions", None)

        def check_permissions(self: Any, request: Request) -> None:
            # First run parent permission checks
            if original_check:
                original_check(self, request)

            user = request.user
            user_roles = set(getattr(user, "roles", []))

            # super_admin bypasses all role checks
            if "super_admin" in user_roles:
                return

            required = set(roles)
            if not user_roles & required:
                logger.warning(
                    "RBAC DENIED: user=%s has roles=%s, required one of=%s, path=%s",
                    getattr(user, "pk", "?"),
                    user_roles,
                    required,
                    request.path,
                )
                raise PermissionDenied(detail=f"This action requires one of these roles: {', '.join(sorted(required))}")

        view_class.check_permissions = check_permissions
        # Store roles metadata for introspection
        view_class._required_roles = roles
        return view_class

    return decorator


def require_permissions(*permissions: str) -> Callable:
    """
    Class decorator that sets required_permissions on a DRF ViewSet.

    Usage:
        @require_permissions("accounting.view_invoice", "accounting.manage_invoice")
        class InvoiceViewSet(ModelViewSet):
            ...

    Works with PolicyRequiredPermission to evaluate via policy engine.
    """

    def decorator(view_class: type) -> type:
        view_class.required_permissions = list(permissions)
        return view_class

    return decorator
