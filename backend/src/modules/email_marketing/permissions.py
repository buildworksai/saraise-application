"""
Permission classes for Email Marketing module.
"""

from rest_framework import permissions


class IsEmailMarketingUser(permissions.BasePermission):
    """Permission check for email marketing module access."""

    def has_permission(self, request, view):
        """Check if user has email marketing permissions."""
        return request.user and request.user.is_authenticated
