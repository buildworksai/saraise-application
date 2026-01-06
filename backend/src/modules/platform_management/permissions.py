"""
Platform Management Permissions
"""

from rest_framework import permissions


class PlatformAdminPermission(permissions.BasePermission):
    """Permission check for platform administrators."""

    def has_permission(self, request, view):
        """Check if user has platform admin permissions."""
        # TODO: Integrate with Policy Engine
        # For now, check if user has platform admin role
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check user roles (to be integrated with Policy Engine)
        user_roles = getattr(request.user, 'roles', [])
        return 'platform_admin' in user_roles or 'super_admin' in user_roles


class PlatformViewerPermission(permissions.BasePermission):
    """Permission check for platform viewers (read-only)."""

    def has_permission(self, request, view):
        """Check if user has platform viewer permissions."""
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Allow read-only access for platform viewers
        if request.method in permissions.SAFE_METHODS:
            user_roles = getattr(request.user, 'roles', [])
            return 'platform_viewer' in user_roles or 'platform_admin' in user_roles
        
        return False

