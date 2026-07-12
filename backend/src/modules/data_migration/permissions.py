"""Authorization policy for tenant-scoped data migration operations."""

from typing import List

from rest_framework.permissions import SAFE_METHODS, BasePermission

PERMISSIONS: List[str] = [
    "data_migration.resource:create",
    "data_migration.resource:read",
    "data_migration.resource:update",
    "data_migration.resource:delete",
    "data_migration.resource:activate",
    "data_migration.resource:deactivate",
]

SOD_ACTIONS: List[str] = [
    "data_migration.resource:create",
    "data_migration.resource:delete",
]


class DataMigrationPermission(BasePermission):
    """Require an explicit data-migration permission or tenant-admin role."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        profile = getattr(request.user, "profile", None)
        tenant_role = getattr(profile, "tenant_role", None)
        roles = set(getattr(request.user, "roles", []))
        if tenant_role:
            roles.add(tenant_role)
        if roles.intersection({"tenant_admin", "system_admin", "super_admin"}):
            return True

        action = "read" if request.method in SAFE_METHODS else "update"
        if getattr(view, "action", None) == "create":
            action = "create"
        elif getattr(view, "action", None) == "destroy":
            action = "delete"
        elif getattr(view, "action", None) in {"execute", "dry_run"}:
            action = "activate"
        return request.user.has_perm(f"data_migration.resource:{action}")
