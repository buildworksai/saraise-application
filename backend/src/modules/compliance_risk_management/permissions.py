"""
Permission classes for Compliance Risk Management module.
"""

from rest_framework import permissions


class IsComplianceRiskUser(permissions.BasePermission):
    """Permission check for compliance risk module access."""

    def has_permission(self, request, view):
        """Check if user has compliance risk permissions."""
        return request.user and request.user.is_authenticated
