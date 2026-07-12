"""Policy-backed permission declarations for tenant management."""

from rest_framework.permissions import SAFE_METHODS

from src.core.auth.policy_permissions import PolicyRequiredPermission


class TenantManagementPermission(PolicyRequiredPermission):
    """Enforce the permissions declared by the tenant module manifest."""

    def has_permission(self, request, view):
        view.required_permissions = ["tenant:read" if request.method in SAFE_METHODS else "tenant:write"]
        return super().has_permission(request, view)
