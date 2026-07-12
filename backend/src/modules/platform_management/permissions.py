"""Policy-engine-backed permissions for platform management."""

from types import SimpleNamespace

from rest_framework.permissions import SAFE_METHODS

from src.core.auth.policy_permissions import PolicyRequiredPermission


class PlatformAdminPermission(PolicyRequiredPermission):
    """Require the manifest-declared setting write permission."""

    def has_permission(self, request, view):
        view = view or SimpleNamespace()
        view.required_permissions = [
            "platform.settings:read" if request.method in SAFE_METHODS else "platform.settings:update"
        ]
        return super().has_permission(request, view)


class PlatformViewerPermission(PolicyRequiredPermission):
    """Require read access and reject mutation attempts."""

    def has_permission(self, request, view):
        if request.method not in SAFE_METHODS:
            return False
        view = view or SimpleNamespace()
        view.required_permissions = ["platform.settings:read"]
        return super().has_permission(request, view)
