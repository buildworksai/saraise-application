"""Action-aware, deny-by-default access declarations for DMS API v2."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id

FOLDER_READ: Final[str] = "dms.folder:read"
FOLDER_CREATE: Final[str] = "dms.folder:create"
FOLDER_UPDATE: Final[str] = "dms.folder:update"
FOLDER_DELETE: Final[str] = "dms.folder:delete"
DOCUMENT_READ: Final[str] = "dms.document:read"
DOCUMENT_CREATE: Final[str] = "dms.document:create"
DOCUMENT_UPDATE: Final[str] = "dms.document:update"
DOCUMENT_MOVE: Final[str] = "dms.document:move"
DOCUMENT_DOWNLOAD: Final[str] = "dms.document:download"
DOCUMENT_DELETE: Final[str] = "dms.document:delete"
VERSION_READ: Final[str] = "dms.version:read"
VERSION_CREATE: Final[str] = "dms.version:create"
VERSION_RESTORE: Final[str] = "dms.version:restore"
PERMISSION_READ: Final[str] = "dms.permission:read"
PERMISSION_GRANT: Final[str] = "dms.permission:grant"
PERMISSION_UPDATE: Final[str] = "dms.permission:update"
PERMISSION_REVOKE: Final[str] = "dms.permission:revoke"
SHARE_READ: Final[str] = "dms.share:read"
SHARE_CREATE: Final[str] = "dms.share:create"
SHARE_REVOKE: Final[str] = "dms.share:revoke"
HEALTH_READ: Final[str] = "dms.health:read"
CONFIGURATION_READ: Final[str] = "dms.configuration:read"
CONFIGURATION_WRITE: Final[str] = "dms.configuration:write"
CONFIGURATION_ROLLBACK: Final[str] = "dms.configuration:rollback"
CONFIGURATION_IMPORT: Final[str] = "dms.configuration:import"
CONFIGURATION_EXPORT: Final[str] = "dms.configuration:export"

PERMISSIONS: Final[tuple[str, ...]] = (
    FOLDER_READ,
    FOLDER_CREATE,
    FOLDER_UPDATE,
    FOLDER_DELETE,
    DOCUMENT_READ,
    DOCUMENT_CREATE,
    DOCUMENT_UPDATE,
    DOCUMENT_MOVE,
    DOCUMENT_DOWNLOAD,
    DOCUMENT_DELETE,
    VERSION_READ,
    VERSION_CREATE,
    VERSION_RESTORE,
    PERMISSION_READ,
    PERMISSION_GRANT,
    PERMISSION_UPDATE,
    PERMISSION_REVOKE,
    SHARE_READ,
    SHARE_CREATE,
    SHARE_REVOKE,
    HEALTH_READ,
    CONFIGURATION_READ,
    CONFIGURATION_WRITE,
    CONFIGURATION_ROLLBACK,
    CONFIGURATION_IMPORT,
    CONFIGURATION_EXPORT,
)

READ_PERMISSIONS: Final[frozenset[str]] = frozenset(
    {
        FOLDER_READ,
        DOCUMENT_READ,
        DOCUMENT_DOWNLOAD,
        VERSION_READ,
        PERMISSION_READ,
        SHARE_READ,
        HEALTH_READ,
        CONFIGURATION_READ,
        CONFIGURATION_EXPORT,
    }
)
PERMISSION_QUOTAS: Final[dict[str, str]] = {
    permission: "dms.api_reads" if permission in READ_PERMISSIONS else "dms.api_writes" for permission in PERMISSIONS
}

FOLDER_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": FOLDER_READ,
    "create": FOLDER_CREATE,
    "retrieve": FOLDER_READ,
    "partial_update": FOLDER_UPDATE,
    "destroy": FOLDER_DELETE,
    "move": FOLDER_UPDATE,
    "contents": FOLDER_READ,
}
DOCUMENT_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": DOCUMENT_READ,
    "create": DOCUMENT_CREATE,
    "retrieve": DOCUMENT_READ,
    "partial_update": DOCUMENT_UPDATE,
    "destroy": DOCUMENT_DELETE,
    "move": DOCUMENT_MOVE,
    "download": DOCUMENT_DOWNLOAD,
}
VERSION_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": VERSION_READ,
    "create": VERSION_CREATE,
    "retrieve": VERSION_READ,
    "restore": VERSION_RESTORE,
}
DOCUMENT_PERMISSION_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": PERMISSION_READ,
    "create": PERMISSION_GRANT,
    "retrieve": PERMISSION_READ,
    "partial_update": PERMISSION_UPDATE,
    "destroy": PERMISSION_REVOKE,
}
SHARE_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": SHARE_READ,
    "create": SHARE_CREATE,
    "retrieve": SHARE_READ,
    "revoke": SHARE_REVOKE,
}
HEALTH_ACTION_PERMISSIONS: Final[dict[str, str]] = {"health": HEALTH_READ}
PRINCIPAL_ACTION_PERMISSIONS: Final[dict[str, str]] = {"search": PERMISSION_GRANT}
CONFIGURATION_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "current": CONFIGURATION_READ,
    "update_current": CONFIGURATION_WRITE,
    "preview": CONFIGURATION_WRITE,
    "history": CONFIGURATION_READ,
    "audit": CONFIGURATION_READ,
    "rollback": CONFIGURATION_ROLLBACK,
    "import_configuration": CONFIGURATION_IMPORT,
    "export_configuration": CONFIGURATION_EXPORT,
}


class SessionAuthentication401(SessionAuthentication):
    """Strict CSRF-enforcing session authentication with a 401 challenge."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class ActionAccessMixin:
    """Resolve one manifest permission for the selected DRF action.

    No permission inference is performed.  A missing action declaration leaves
    ``required_permission`` unset, which ``RequiresAccess`` denies with its
    stable DENY_DEFAULT decision.
    """

    authentication_classes = (SessionAuthentication401,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}
    action_quotas: dict[str, str] = {}
    quota_cost = 1

    def get_permissions(self) -> list[object]:
        request = self.request
        # Always clear values injected by headers/body-aware middleware before
        # consulting the authenticated profile.
        request.tenant_id = None
        tenant_value = get_user_tenant_id(getattr(request, "user", None))
        if tenant_value is not None:
            try:
                request.tenant_id = UUID(str(tenant_value))
            except (AttributeError, TypeError, ValueError):
                request.tenant_id = None

        action = getattr(self, "action", "")
        permission = self.action_permissions.get(action)
        self.required_permission = permission
        self.required_entitlement = permission
        self.quota_resource = self.action_quotas.get(action) or (
            PERMISSION_QUOTAS.get(permission) if permission else None
        )
        return [IsAuthenticated(), RequiresAccess()]


__all__ = [
    "ActionAccessMixin",
    "CONFIGURATION_ACTION_PERMISSIONS",
    "DOCUMENT_ACTION_PERMISSIONS",
    "DOCUMENT_PERMISSION_ACTION_PERMISSIONS",
    "FOLDER_ACTION_PERMISSIONS",
    "HEALTH_ACTION_PERMISSIONS",
    "PERMISSIONS",
    "PERMISSION_QUOTAS",
    "PRINCIPAL_ACTION_PERMISSIONS",
    "SHARE_ACTION_PERMISSIONS",
    "SessionAuthentication401",
    "VERSION_ACTION_PERMISSIONS",
]
