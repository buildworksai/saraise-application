"""Policy-engine-backed permissions for platform management."""

from rest_framework.permissions import SAFE_METHODS

from src.core.auth.policy_permissions import PolicyRequiredPermission


class PlatformAdminPermission(PolicyRequiredPermission):
    """Require the exact manifest permission for the ViewSet resource/action."""

    ACTIONS = {
        "create": "create",
        "destroy": "delete",
        "list": "read",
        "retrieve": "read",
        "update": "update",
        "partial_update": "update",
        "current": "read",
        "save": "create",
        "summary": "read",
        "toggle": "update",
    }
    ALLOWED_PERMISSIONS = {
        "platform.settings:create",
        "platform.settings:read",
        "platform.settings:update",
        "platform.settings:delete",
        "platform.feature-flags:create",
        "platform.feature-flags:read",
        "platform.feature-flags:update",
        "platform.feature-flags:delete",
        "platform.health:read",
        "platform.audit:read",
        "platform.metrics:create",
        "platform.metrics:read",
        "platform.metrics:update",
        "platform.metrics:delete",
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


class PlatformViewerPermission(PolicyRequiredPermission):
    """Require read access and reject mutation attempts."""

    def has_permission(self, request, view):
        if request.method not in SAFE_METHODS:
            return False
        resource = getattr(view, "permission_resource", None)
        if not resource:
            return False
        permission = f"{resource}:read"
        if permission not in PlatformAdminPermission.ALLOWED_PERMISSIONS:
            return False
        view.required_permissions = [permission]
        return super().has_permission(request, view)
