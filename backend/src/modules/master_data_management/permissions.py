"""
Permission classes for Master Data Management module.
"""

from rest_framework import permissions


class IsMDMUser(permissions.BasePermission):
    """Permission check for MDM module access."""

    def has_permission(self, request, view):
        """Check if user has MDM permissions."""
        return request.user and request.user.is_authenticated
