"""
Permission classes for Communication Hub module.
"""

from rest_framework import permissions


class IsCommunicationUser(permissions.BasePermission):
    """Permission check for communication module access."""

    def has_permission(self, request, view):
        """Check if user has communication permissions."""
        return request.user and request.user.is_authenticated
