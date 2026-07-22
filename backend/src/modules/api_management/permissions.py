"""Fail-closed, manifest-aligned access declarations."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

RESOURCE_CREATE: Final = "api_management.resource:create"
RESOURCE_READ: Final = "api_management.resource:read"
RESOURCE_UPDATE: Final = "api_management.resource:update"
RESOURCE_DELETE: Final = "api_management.resource:delete"
RESOURCE_ACTIVATE: Final = "api_management.resource:activate"
RESOURCE_DEACTIVATE: Final = "api_management.resource:deactivate"
RESOURCE_RESTORE: Final = "api_management.resource:restore"
CONFIG_READ: Final = "api_management.configuration:read"
CONFIG_UPDATE: Final = "api_management.configuration:update"
CONFIG_ROLLBACK: Final = "api_management.configuration:rollback"
CONFIG_IMPORT: Final = "api_management.configuration:import"
CONFIG_EXPORT: Final = "api_management.configuration:export"
HEALTH_READ: Final = "api_management.health:read"

PERMISSIONS: Final = (
    RESOURCE_CREATE,
    RESOURCE_READ,
    RESOURCE_UPDATE,
    RESOURCE_DELETE,
    RESOURCE_ACTIVATE,
    RESOURCE_DEACTIVATE,
    RESOURCE_RESTORE,
    CONFIG_READ,
    CONFIG_UPDATE,
    CONFIG_ROLLBACK,
    CONFIG_IMPORT,
    CONFIG_EXPORT,
    HEALTH_READ,
)

SOD_ACTIONS: Final = (RESOURCE_CREATE, RESOURCE_DELETE, CONFIG_UPDATE, CONFIG_ROLLBACK)


class ActionAccessMixin:
    """Map every action to a permission; missing metadata denies by default."""

    authentication_classes = (RelaxedCsrfSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}

    def get_permissions(self) -> list[object]:
        raw_tenant = get_user_tenant_id(getattr(self.request, "user", None))
        try:
            self.request.tenant_id = UUID(str(raw_tenant)) if raw_tenant else None
        except (TypeError, ValueError, AttributeError):
            self.request.tenant_id = None
        permission = self.action_permissions.get(str(getattr(self, "action", "")))
        self.required_permission = permission
        self.required_entitlement = permission
        self.quota_resource = f"api_management.{getattr(self, 'action', 'unknown')}" if permission else None
        self.quota_cost = 1
        return [IsAuthenticated(), RequiresAccess()]


__all__ = ["ActionAccessMixin", "PERMISSIONS", "SOD_ACTIONS"]
