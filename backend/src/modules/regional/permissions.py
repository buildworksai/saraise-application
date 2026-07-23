"""Fail-closed, action-aware Regional permissions."""

from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist

from src.core.auth.policy_permissions import PolicyRequiredPermission

PERMISSIONS = [
    "regional.resource:create",
    "regional.resource:read",
    "regional.resource:update",
    "regional.resource:delete",
    "regional.resource:activate",
    "regional.resource:deactivate",
    "regional.configuration:read",
    "regional.configuration:write",
    "regional.configuration:rollback",
    "regional.configuration:import",
    "regional.configuration:export",
]

SOD_ACTIONS = [
    "regional.resource:create",
    "regional.resource:delete",
]


class RegionalPolicyPermission(PolicyRequiredPermission):
    """Map every router action to one manifest permission and deny unknowns."""

    message = "The required Regional permission was not granted."
    resource_action_permissions: dict[str, str] = {
        "list": "regional.resource:read",
        "retrieve": "regional.resource:read",
        "create": "regional.resource:create",
        "update": "regional.resource:update",
        "partial_update": "regional.resource:update",
        "destroy": "regional.resource:delete",
        "restore": "regional.resource:update",
        "activate": "regional.resource:activate",
        "deactivate": "regional.resource:deactivate",
    }
    configuration_action_permissions: dict[str, str] = {
        "list": "regional.configuration:read",
        "current": "regional.configuration:read",
        "preview": "regional.configuration:write",
        "history": "regional.configuration:read",
        "rollback": "regional.configuration:rollback",
        "import_document": "regional.configuration:import",
        "export_document": "regional.configuration:export",
    }

    def has_permission(self, request: object, view: object) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        try:
            profile = user.profile
        except (AttributeError, ObjectDoesNotExist):
            return False
        try:
            UUID(str(getattr(profile, "tenant_id", "")))
        except (AttributeError, TypeError, ValueError):
            return False
        mapping = (
            self.configuration_action_permissions
            if getattr(view, "permission_scope", "") == "configuration"
            else self.resource_action_permissions
        )
        action = str(getattr(view, "action", ""))
        if (
            getattr(view, "permission_scope", "") == "configuration"
            and action == "current"
            and str(getattr(request, "method", "GET")).upper() != "GET"
        ):
            permission = "regional.configuration:write"
        else:
            permission = mapping.get(action)
        if permission is None:
            return False
        role = str(getattr(profile, "tenant_role", ""))
        if role in {"tenant_admin", "system_admin", "super_admin"} or getattr(user, "is_superuser", False):
            return True
        return bool(user.has_perm(permission))
