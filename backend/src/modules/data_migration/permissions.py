"""Fail-closed, action-specific access declarations for data migration API v2."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_platform_role, get_user_tenant_id

CORE_ENTITLEMENT: Final = "data_migration.core"

JOB_READ: Final = "data_migration.job:read"
JOB_CREATE: Final = "data_migration.job:create"
JOB_UPDATE: Final = "data_migration.job:update"
JOB_DELETE: Final = "data_migration.job:delete"
JOB_EXPORT: Final = "data_migration.job:export"
JOB_IMPORT: Final = "data_migration.job:import"
MAPPING_MANAGE: Final = "data_migration.mapping:manage"
RULE_MANAGE: Final = "data_migration.rule:manage"
SOURCE_PREVIEW: Final = "data_migration.source:preview"
RUN_EXECUTE: Final = "data_migration.run:execute"
RUN_CANCEL: Final = "data_migration.run:cancel"
ROLLBACK_EXECUTE: Final = "data_migration.rollback:execute"
CONNECTION_READ: Final = "data_migration.connection:read"
CONNECTION_MANAGE: Final = "data_migration.connection:manage"
CONNECTION_TEST: Final = "data_migration.connection:test"
CONFIGURATION_READ: Final = "data_migration.job:read"
CONFIGURATION_MANAGE: Final = "data_migration.job:update"

PERMISSIONS: Final[tuple[str, ...]] = (
    JOB_READ,
    JOB_CREATE,
    JOB_UPDATE,
    JOB_DELETE,
    JOB_EXPORT,
    JOB_IMPORT,
    MAPPING_MANAGE,
    RULE_MANAGE,
    SOURCE_PREVIEW,
    RUN_EXECUTE,
    RUN_CANCEL,
    ROLLBACK_EXECUTE,
    CONNECTION_READ,
    CONNECTION_MANAGE,
    CONNECTION_TEST,
)

JOB_ACTION_PERMISSIONS: Final = {
    "list": JOB_READ,
    "retrieve": JOB_READ,
    "create": JOB_CREATE,
    "partial_update": JOB_UPDATE,
    "destroy": JOB_DELETE,
    "validate_definition": JOB_UPDATE,
    "archive": JOB_UPDATE,
    "restore": JOB_UPDATE,
    "attach_source": JOB_UPDATE,
    "inspect": SOURCE_PREVIEW,
    "preview": SOURCE_PREVIEW,
    "export_definition": JOB_EXPORT,
    "import_definition": JOB_IMPORT,
    "versions": JOB_READ,
    "restore_version": JOB_UPDATE,
    "mappings": JOB_READ,
    "create_mapping": MAPPING_MANAGE,
    "suggest_mappings": MAPPING_MANAGE,
    "apply_mappings": MAPPING_MANAGE,
    "validation_rules": JOB_READ,
    "create_validation_rule": RULE_MANAGE,
    "runs": JOB_READ,
    "request_run": RUN_EXECUTE,
    "request_dry_run": RUN_EXECUTE,
}
MAPPING_ACTION_PERMISSIONS: Final = {
    "retrieve": JOB_READ,
    "partial_update": MAPPING_MANAGE,
    "destroy": MAPPING_MANAGE,
}
RULE_ACTION_PERMISSIONS: Final = {
    "retrieve": JOB_READ,
    "partial_update": RULE_MANAGE,
    "destroy": RULE_MANAGE,
}
RUN_ACTION_PERMISSIONS: Final = {
    "retrieve": JOB_READ,
    "issues": JOB_READ,
    "export_issues": JOB_READ,
    "cancel": RUN_CANCEL,
    "rollback": ROLLBACK_EXECUTE,
}
ROLLBACK_ACTION_PERMISSIONS: Final = {"retrieve": JOB_READ}
CONNECTION_ACTION_PERMISSIONS: Final = {
    "list": CONNECTION_READ,
    "retrieve": CONNECTION_READ,
    "create": CONNECTION_MANAGE,
    "partial_update": CONNECTION_MANAGE,
    "deactivate": CONNECTION_MANAGE,
    "rotate_credential": CONNECTION_MANAGE,
    "test_connection": CONNECTION_TEST,
}
CONFIGURATION_ACTION_PERMISSIONS: Final = {
    "retrieve_configuration": CONFIGURATION_READ,
    "update_configuration": CONFIGURATION_MANAGE,
    "preview_configuration": CONFIGURATION_MANAGE,
    "configuration_versions": CONFIGURATION_READ,
    "restore_configuration": CONFIGURATION_MANAGE,
    "import_configuration": CONFIGURATION_MANAGE,
    "export_configuration": CONFIGURATION_READ,
}


class SessionAuthentication401(SessionAuthentication):
    """Keep strict CSRF enforcement while correctly challenging with HTTP 401."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


def is_platform_operator(user: object) -> bool:
    """Return operator status; this is an additional gate, never a policy bypass."""

    if not user or not bool(getattr(user, "is_authenticated", False)):
        return False
    roles = set(getattr(user, "roles", ()) or ())
    return bool(
        getattr(user, "is_superuser", False)
        or get_user_platform_role(user) in {"platform_owner", "platform_operator"}
        or roles.intersection({"system_admin", "super_admin"})
    )


class ActionAccessMixin:
    """Populate exact policy metadata before ``RequiresAccess`` evaluates.

    Unknown actions deliberately leave the permission blank and are denied by
    the shared access pipeline. Tenant identity comes only from the authenticated
    profile; a header, query parameter, or body value can never select it.
    """

    authentication_classes = (SessionAuthentication401,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}
    method_permissions: dict[str, dict[str, str]] = {}
    action_quotas: dict[str, str] = {}
    quota_cost = 1

    def get_permissions(self) -> list[object]:
        request = self.request
        request.tenant_id = None
        raw_tenant = get_user_tenant_id(getattr(request, "user", None))
        if raw_tenant is not None:
            try:
                request.tenant_id = raw_tenant if isinstance(raw_tenant, UUID) else UUID(str(raw_tenant))
            except (AttributeError, TypeError, ValueError):
                request.tenant_id = None

        action = getattr(self, "action", "")
        permission = self.method_permissions.get(action, {}).get(request.method.upper()) or self.action_permissions.get(action)
        self.required_permission = permission
        self.required_entitlement = CORE_ENTITLEMENT if permission else None
        self.quota_resource = self.action_quotas.get(getattr(self, "action", ""))
        return [IsAuthenticated(), RequiresAccess()]


__all__ = [
    "ActionAccessMixin",
    "CONNECTION_ACTION_PERMISSIONS",
    "CONFIGURATION_ACTION_PERMISSIONS",
    "CORE_ENTITLEMENT",
    "JOB_ACTION_PERMISSIONS",
    "MAPPING_ACTION_PERMISSIONS",
    "PERMISSIONS",
    "ROLLBACK_ACTION_PERMISSIONS",
    "RULE_ACTION_PERMISSIONS",
    "RUN_ACTION_PERMISSIONS",
    "SessionAuthentication401",
    "is_platform_operator",
]
