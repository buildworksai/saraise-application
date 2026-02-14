"""
Permission classes for Inventory Management module.
"""

from rest_framework import permissions


class IsInventoryUser(permissions.BasePermission):
    """Permission check for inventory module access."""

    def has_permission(self, request, view):
        """Check if user has inventory permissions."""
        return request.user and request.user.is_authenticated
