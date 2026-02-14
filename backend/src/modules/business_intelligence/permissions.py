"""
Permission classes for Business Intelligence module.
"""

from rest_framework import permissions


class IsBIUser(permissions.BasePermission):
    """Permission check for BI module access."""

    def has_permission(self, request, view):
        """Check if user has BI permissions."""
        return request.user and request.user.is_authenticated
