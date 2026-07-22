"""Fail-closed authorization primitives for the fixed-assets API v2."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id

PERMISSIONS: Final[tuple[str, ...]] = (
    "fixed_asset.category:read",
    "fixed_asset.category:create",
    "fixed_asset.category:update",
    "fixed_asset.category:delete",
    "fixed_asset.asset:read",
    "fixed_asset.asset:create",
    "fixed_asset.asset:update",
    "fixed_asset.asset:delete",
    "fixed_asset.asset:capitalize",
    "fixed_asset.asset:transfer",
    "fixed_asset.asset:impair",
    "fixed_asset.asset:dispose",
    "fixed_asset.depreciation:read",
    "fixed_asset.depreciation:calculate",
    "fixed_asset.depreciation:post",
    "fixed_asset.transaction:read",
)

READ_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "list",
        "retrieve",
        "transactions",
        "dashboard",
    }
)


class SessionAuthentication401(SessionAuthentication):
    """Keep normal CSRF enforcement while producing an explicit 401 challenge."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class ActionAccessMixin:
    """Resolve a declared DRF action to one governed access decision.

    An action missing from ``action_permissions`` deliberately leaves
    ``required_permission`` unset. :class:`RequiresAccess` then denies by
    default. Read operations never consume quota; only explicitly listed
    mutation actions do.
    """

    authentication_classes = (SessionAuthentication401,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}
    action_quotas: dict[str, str] = {}
    entitlement = "fixed_assets.core"

    def get_permissions(self) -> list[object]:
        action = str(getattr(self, "action", ""))
        tenant = get_user_tenant_id(getattr(self.request, "user", None))
        try:
            self.request.tenant_id = UUID(str(tenant)) if tenant else None
        except (TypeError, ValueError, AttributeError):
            self.request.tenant_id = None

        self.required_permission = self.action_permissions.get(action)
        self.required_entitlement = self.entitlement
        self.quota_resource = self.action_quotas.get(action)
        self.quota_cost = 1
        return [IsAuthenticated(), RequiresAccess()]


__all__ = [
    "ActionAccessMixin",
    "PERMISSIONS",
    "READ_ACTIONS",
    "SessionAuthentication401",
]
