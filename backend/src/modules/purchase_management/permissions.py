"""
Permission classes for Purchase Management module.
"""

from rest_framework import permissions


class IsPurchaseUser(permissions.BasePermission):
    """Permission check for purchase module access."""

    def has_permission(self, request, view):
        """Check if user has purchase permissions."""
        return request.user and request.user.is_authenticated
