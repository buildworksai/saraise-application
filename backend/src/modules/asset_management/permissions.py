"""Fail-closed action access controls for Asset Management."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id

from .api_auth import StrictSessionAuthentication

ENTITLEMENT: Final = "asset_management"

ASSET_CREATE: Final = "asset.asset:create"
ASSET_READ: Final = "asset.asset:read"
ASSET_UPDATE: Final = "asset.asset:update"
ASSET_DELETE: Final = "asset.asset:delete"
ASSET_ACTIVATE: Final = "asset.asset:activate"
ASSET_DEACTIVATE: Final = "asset.asset:deactivate"
DEPRECIATION_READ: Final = "asset.depreciation:read"
CONFIGURATION_READ: Final = "asset.configuration:read"
CONFIGURATION_UPDATE: Final = "asset.configuration:update"
CONFIGURATION_ROLLBACK: Final = "asset.configuration:rollback"
CONFIGURATION_IMPORT: Final = "asset.configuration:import"
CONFIGURATION_EXPORT: Final = "asset.configuration:export"
HEALTH_READ: Final = "asset.health:read"
HEALTH_ACTION_PERMISSIONS: Final[dict[str, str]] = {"health": HEALTH_READ}

PERMISSIONS: Final = tuple(
    value for name, value in globals().items() if name.isupper() and isinstance(value, str) and value.startswith("asset.")
)
SOD_ACTIONS: Final[tuple[str, ...]] = ()


class AssetAccessMixin:
    """Attach exact action permission metadata before shared access evaluation."""

    authentication_classes = (StrictSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    required_entitlement = ENTITLEMENT
    action_permissions: dict[str | None, str] = {}

    def get_permissions(self) -> list[object]:
        try:
            raw_tenant = get_user_tenant_id(getattr(self.request, "user", None))
            self.request.tenant_id = UUID(str(raw_tenant)) if raw_tenant else None
        except Exception:
            self.request.tenant_id = None
        self.required_permission = self.action_permissions.get(getattr(self, "action", None))
        self.quota_resource = "asset_management.api.requests" if self.required_permission else None
        self.quota_cost = 1
        return [IsAuthenticated(), RequiresAccess()]


class ActionAccessMixin:
    """Resolve one manifest permission for the selected DRF action."""

    authentication_classes = (StrictSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}
    quota_cost = 1

    def get_permissions(self) -> list[object]:
        self.request.tenant_id = None
        action = getattr(self, "action", "")
        permission = self.action_permissions.get(action)
        self.required_permission = permission
        self.required_entitlement = permission
        self.quota_resource = "asset_management.api.requests" if permission else None

        try:
            tenant_value = get_user_tenant_id(getattr(self.request, "user", None))
            if tenant_value is not None:
                try:
                    self.request.tenant_id = UUID(str(tenant_value))
                except (AttributeError, TypeError, ValueError):
                    self.request.tenant_id = None
        except Exception:
            if action == "health":
                return [IsAuthenticated()]
            self.request.tenant_id = None

        return [IsAuthenticated(), RequiresAccess()]


__all__ = [
    "ActionAccessMixin",
    "AssetAccessMixin",
    "HEALTH_ACTION_PERMISSIONS",
    "PERMISSIONS",
    "SOD_ACTIONS",
    *[name for name, value in globals().items() if name.isupper() and isinstance(value, str)],
]
