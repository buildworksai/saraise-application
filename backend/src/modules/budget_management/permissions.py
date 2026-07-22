"""Fail-closed action authorization for budget-management v2."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id

PERMISSIONS: Final[tuple[str, ...]] = (
    "budget.budget:create", "budget.budget:read", "budget.budget:update", "budget.budget:delete",
    "budget.budget:submit", "budget.budget:approve", "budget.budget:close",
    "budget.budget_line:create", "budget.budget_line:read", "budget.budget_line:update",
    "budget.budget_line:delete", "budget.availability:read", "budget.actuals:sync",
    "budget.variance:read", "budget.variance:generate", "budget.variance:acknowledge",
    "budget.health:read",
)


class SessionAuthentication401(SessionAuthentication):
    """Retain session CSRF checks while advertising an authentication challenge."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class BudgetAccessMixin:
    """Bind the canonical request tenant and resolve actions deny-by-default."""

    authentication_classes = (SessionAuthentication401,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}
    action_quotas: dict[str, str] = {}
    required_entitlement = "module.budget_management"

    def get_permissions(self) -> list[object]:
        tenant = get_user_tenant_id(getattr(self.request, "user", None))
        try:
            self.request.tenant_id = UUID(str(tenant)) if tenant else None
        except (TypeError, ValueError, AttributeError):
            self.request.tenant_id = None
        action = str(getattr(self, "action", "") or getattr(self, "permission_action", ""))
        self.required_permission = self.action_permissions.get(action)
        self.required_entitlement = "module.budget_management"
        self.quota_resource = self.action_quotas.get(action)
        self.quota_cost = 1
        return [IsAuthenticated(), RequiresAccess()]


__all__ = ["BudgetAccessMixin", "PERMISSIONS", "SessionAuthentication401"]
