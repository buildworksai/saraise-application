"""
Permission classes for Sales Management module.
"""

from rest_framework import permissions


class IsSalesUser(permissions.BasePermission):
    """Permission check for sales module access."""

    def has_permission(self, request, view):
        """Check if user has sales permissions."""
        return request.user and request.user.is_authenticated
