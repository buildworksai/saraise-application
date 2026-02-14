"""
Permission classes for Accounting & Finance module.
"""

from rest_framework import permissions


class IsAccountingUser(permissions.BasePermission):
    """Permission check for accounting module access."""

    def has_permission(self, request, view):
        """Check if user has accounting permissions."""
        return request.user and request.user.is_authenticated
