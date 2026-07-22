"""Deny-by-default action authorization for Accounting & Finance."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.core.access import RequiresAccess
from src.core.auth_utils import get_user_tenant_id

PERMISSIONS: Final[tuple[str, ...]] = (
    "accounting.account:create", "accounting.account:read", "accounting.account:update", "accounting.account:delete",
    "accounting.posting_period:create", "accounting.posting_period:read", "accounting.posting_period:update", "accounting.posting_period:close", "accounting.posting_period:lock",
    "accounting.journal_entry:create", "accounting.journal_entry:read", "accounting.journal_entry:update", "accounting.journal_entry:delete", "accounting.journal_entry:post", "accounting.journal_entry:reverse", "accounting.journal_entry:import",
    "accounting.ap_invoice:create", "accounting.ap_invoice:read", "accounting.ap_invoice:update", "accounting.ap_invoice:delete", "accounting.ap_invoice:approve", "accounting.ap_invoice:post",
    "accounting.ar_invoice:create", "accounting.ar_invoice:read", "accounting.ar_invoice:update", "accounting.ar_invoice:delete", "accounting.ar_invoice:post",
    "accounting.payment:create", "accounting.payment:read", "accounting.payment:update", "accounting.payment:void",
    "accounting.report:read",
)


class SessionAuthentication401(SessionAuthentication):
    """Strict session/CSRF authentication with an explicit 401 challenge."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class AccountingAccessMixin:
    authentication_classes = (SessionAuthentication401,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}
    action_quotas: dict[str, str] = {}
    entitlement = "accounting_finance"

    def get_permissions(self) -> list[object]:
        tenant = get_user_tenant_id(getattr(self.request, "user", None))
        try:
            self.request.tenant_id = UUID(str(tenant)) if tenant else None
        except (TypeError, ValueError, AttributeError):
            self.request.tenant_id = None
        action = str(getattr(self, "action", ""))
        self.required_permission = self.action_permissions.get(action)
        self.required_entitlement = self.entitlement
        # Reads do not consume write quota; mutations opt in to declared quotas.
        self.quota_resource = self.action_quotas.get(action)
        self.quota_cost = 1
        return [IsAuthenticated(), RequiresAccess()]


class IsAccountingUser(IsAuthenticated):
    """Deprecated import alias; canonical views also require RequiresAccess."""


__all__ = ["AccountingAccessMixin", "IsAccountingUser", "PERMISSIONS", "SessionAuthentication401"]
