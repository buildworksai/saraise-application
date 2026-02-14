"""
Permission classes for Fixed Assets module.
"""

from rest_framework import permissions


class IsFixedAssetUser(permissions.BasePermission):
    """Permission check for fixed assets module access."""

    def has_permission(self, request, view):
        """Check if user has fixed asset permissions."""
        return request.user and request.user.is_authenticated
