"""
Permission classes for Asset Management module.
"""

from rest_framework import permissions


class IsAssetUser(permissions.BasePermission):
    """Permission check for asset module access."""

    def has_permission(self, request, view):
        """Check if user has asset permissions."""
        return request.user and request.user.is_authenticated
