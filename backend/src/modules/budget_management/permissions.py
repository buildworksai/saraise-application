"""
Permission classes for Budget Management module.
"""

from rest_framework import permissions


class IsBudgetUser(permissions.BasePermission):
    """Permission check for budget module access."""

    def has_permission(self, request, view):
        """Check if user has budget permissions."""
        return request.user and request.user.is_authenticated
