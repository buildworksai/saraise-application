"""
Permission classes for Notifications module.
"""

from rest_framework import permissions


class IsNotificationUser(permissions.BasePermission):
    """Permission check for notifications module access."""

    def has_permission(self, request, view):
        """Check if user has notification permissions."""
        return request.user and request.user.is_authenticated
