"""Policy-backed permission declarations for tenant management."""

from rest_framework.permissions import SAFE_METHODS

from src.core.auth.policy_permissions import PolicyRequiredPermission


class TenantManagementPermission(PolicyRequiredPermission):
    """Enforce the permissions declared by the tenant module manifest."""

    def has_permission(self, request, view):
        resource = getattr(view, "permission_resource", None)
        if not resource:
            return False
        action = "read" if request.method in SAFE_METHODS else "write"
        view.required_permissions = [f"{resource}:{action}"]
        return super().has_permission(request, view)
