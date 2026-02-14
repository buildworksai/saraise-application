"""
Permission classes for Project Management module.
"""

from rest_framework import permissions


class IsProjectUser(permissions.BasePermission):
    """Permission check for project module access."""

    def has_permission(self, request, view):
        """Check if user has project permissions."""
        return request.user and request.user.is_authenticated
