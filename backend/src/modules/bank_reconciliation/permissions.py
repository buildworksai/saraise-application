"""Action-aware, fail-closed access declarations for API v2."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id

PERMISSIONS: Final[tuple[str, ...]] = (
    "bank_reconciliation.account:read",
    "bank_reconciliation.account:create",
    "bank_reconciliation.account:update",
    "bank_reconciliation.account:archive",
    "bank_reconciliation.account:reveal",
    "bank_reconciliation.statement:read",
    "bank_reconciliation.statement:create",
    "bank_reconciliation.statement:void",
    "bank_reconciliation.transaction:read",
    "bank_reconciliation.transaction:create",
    "bank_reconciliation.transaction:update",
    "bank_reconciliation.import:read",
    "bank_reconciliation.import:create",
    "bank_reconciliation.import:retry",
    "bank_reconciliation.import:cancel",
    "bank_reconciliation.rule:read",
    "bank_reconciliation.rule:create",
    "bank_reconciliation.rule:update",
    "bank_reconciliation.rule:delete",
    "bank_reconciliation.reconciliation:read",
    "bank_reconciliation.reconciliation:create",
    "bank_reconciliation.reconciliation:update",
    "bank_reconciliation.reconciliation:review",
    "bank_reconciliation.reconciliation:finalize",
    "bank_reconciliation.reconciliation:void",
    "bank_reconciliation.reconciliation:export",
    "bank_reconciliation.match:read",
    "bank_reconciliation.match:create",
    "bank_reconciliation.match:confirm",
    "bank_reconciliation.match:reverse",
    "bank_reconciliation.health:read",
)

READ_ACTIONS: Final[frozenset[str]] = frozenset({"list", "retrieve", "transactions", "report", "summary", "health"})


class SessionAuthentication401(SessionAuthentication):
    """Strict session authentication: standard CSRF enforcement, explicit 401."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class ActionAccessMixin:
    """Map the selected DRF action to permission, entitlement and quota."""

    authentication_classes = (SessionAuthentication401,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}
    action_quotas: dict[str, str] = {}

    def get_permissions(self) -> list[object]:
        action = getattr(self, "action", "")
        tenant_id = get_user_tenant_id(getattr(self.request, "user", None))
        if tenant_id is not None:
            try:
                self.request.tenant_id = UUID(str(tenant_id))
            except (TypeError, ValueError, AttributeError):
                self.request.tenant_id = None
        self.required_permission = self.action_permissions.get(action)
        self.required_entitlement = self.required_permission
        self.quota_resource = self.action_quotas.get(
            action,
            "bank_reconciliation.api_reads" if action in READ_ACTIONS else "bank_reconciliation.api_writes",
        )
        return [IsAuthenticated(), RequiresAccess()]


# Compatibility name for any old imports; its semantics are intentionally the
# same fail-closed action mixin, not authentication-only permission.
IsBankUser = RequiresAccess

__all__ = ["ActionAccessMixin", "IsBankUser", "PERMISSIONS", "SessionAuthentication401"]
