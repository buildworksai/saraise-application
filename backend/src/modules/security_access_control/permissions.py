"""Policy-engine-backed permissions for security administration."""

from rest_framework.permissions import SAFE_METHODS

from src.core.auth.policy_permissions import PolicyRequiredPermission


class SecurityAdminPermission(PolicyRequiredPermission):
    """Require the exact manifest permission for the ViewSet resource/action."""

    ACTIONS = {
        "create": "create",
        "destroy": "delete",
        "list": "read",
        "retrieve": "read",
        "update": "update",
        "partial_update": "update",
        "assign_permission": "update",
        "revoke_permission": "update",
    }
    ALLOWED_PERMISSIONS = {
        "security.roles:create",
        "security.roles:read",
        "security.roles:update",
        "security.roles:delete",
        "security.permissions:read",
        "security.permission-sets:create",
        "security.permission-sets:read",
        "security.permission-sets:update",
        "security.permission-sets:delete",
        "security.security-profiles:create",
        "security.security-profiles:read",
        "security.security-profiles:update",
        "security.security-profiles:delete",
        "security.field-security:create",
        "security.field-security:read",
        "security.field-security:update",
        "security.field-security:delete",
        "security.row-security:create",
        "security.row-security:read",
        "security.row-security:update",
        "security.row-security:delete",
        "security.audit-logs:read",
    }

    def has_permission(self, request, view):
        resource = getattr(view, "permission_resource", None)
        action = self.ACTIONS.get(getattr(view, "action", ""))
        if not resource or not action:
            return False
        permission = f"{resource}:{action}"
        if permission not in self.ALLOWED_PERMISSIONS:
            return False
        view.required_permissions = [permission]
        return super().has_permission(request, view)


class SecurityViewerPermission(PolicyRequiredPermission):
    """Require read access and reject mutation attempts."""

    def has_permission(self, request, view):
        if request.method not in SAFE_METHODS:
            return False
        resource = getattr(view, "permission_resource", None)
        if not resource:
            return False
        permission = f"{resource}:read"
        if permission not in SecurityAdminPermission.ALLOWED_PERMISSIONS:
            return False
        view.required_permissions = [permission]
        return super().has_permission(request, view)
