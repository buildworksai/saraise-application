"""Policy-engine-backed permissions for security administration."""

from types import SimpleNamespace

from rest_framework.permissions import SAFE_METHODS

from src.core.auth.policy_permissions import PolicyRequiredPermission


class SecurityAdminPermission(PolicyRequiredPermission):
    """Require manifest-declared role administration permissions."""

    def has_permission(self, request, view):
        view = view or SimpleNamespace()
        view.required_permissions = [
            "security.roles:read" if request.method in SAFE_METHODS else "security.roles:update"
        ]
        return super().has_permission(request, view)


class SecurityViewerPermission(PolicyRequiredPermission):
    """Require read access and reject mutation attempts."""

    def has_permission(self, request, view):
        if request.method not in SAFE_METHODS:
            return False
        view = view or SimpleNamespace()
        view.required_permissions = ["security.roles:read"]
        return super().has_permission(request, view)
