"""
Permission classes for Compliance Management module.
"""

from rest_framework import permissions


class IsComplianceUser(permissions.BasePermission):
    """Permission check for compliance module access."""

    def has_permission(self, request, view):
        """Check if user has compliance permissions."""
        return request.user and request.user.is_authenticated
