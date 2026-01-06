"""
Security & Access Control Permissions
"""

from rest_framework import permissions


class SecurityAdminPermission(permissions.BasePermission):
    """Permission check for security administrators."""

    def has_permission(self, request, view):
        """Check if user has security admin permissions."""
        # TODO: Integrate with Policy Engine
        # For now, check if user has security admin role
        if not request.user or not request.user.is_authenticated:
            return False

        # Check user roles (to be integrated with Policy Engine)
        user_roles = getattr(request.user, "roles", [])
        return "security_admin" in user_roles or "super_admin" in user_roles


class SecurityViewerPermission(permissions.BasePermission):
    """Permission check for security viewers (read-only)."""

    def has_permission(self, request, view):
        """Check if user has security viewer permissions."""
        if not request.user or not request.user.is_authenticated:
            return False

        # Allow read-only access for security viewers
        if request.method in permissions.SAFE_METHODS:
            user_roles = getattr(request.user, "roles", [])
            return "security_viewer" in user_roles or "security_admin" in user_roles

        return False
