"""
Permission classes for Bank Reconciliation module.
"""

from rest_framework import permissions


class IsBankUser(permissions.BasePermission):
    """Permission check for bank reconciliation module access."""

    def has_permission(self, request, view):
        """Check if user has bank permissions."""
        return request.user and request.user.is_authenticated
