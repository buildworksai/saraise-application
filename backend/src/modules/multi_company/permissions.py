"""
Permission classes for Multi-Company module.
"""

from rest_framework import permissions


class IsMultiCompanyUser(permissions.BasePermission):
    """Permission check for multi-company module access."""

    def has_permission(self, request, view):
        """Check if user has multi-company permissions."""
        return request.user and request.user.is_authenticated
