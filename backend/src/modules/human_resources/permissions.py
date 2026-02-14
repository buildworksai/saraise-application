"""
Permission classes for Human Resources module.
"""

from rest_framework import permissions


class IsHRUser(permissions.BasePermission):
    """Permission check for HR module access."""

    def has_permission(self, request, view):
        """Check if user has HR permissions."""
        return request.user and request.user.is_authenticated
