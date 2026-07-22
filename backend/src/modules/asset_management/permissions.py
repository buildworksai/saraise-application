"""Action-aware access controls for Asset Management."""

from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist

from src.core.auth.policy_permissions import PolicyRequiredPermission


class IsAssetUser(PolicyRequiredPermission):
    """Action-aware policy adapter for the permissions in ``manifest.yaml``.

    The shared policy class cannot infer a ViewSet action.  This adapter keeps
    the manifest mapping explicit and fail-closed while retaining the local
    privileged-role semantics used by tenant administration.
    """

    message = "Asset Management permission is required."
    action_permissions: dict[str | None, str] = {
        "list": "asset.asset:read",
        "retrieve": "asset.asset:read",
        "create": "asset.asset:create",
        "update": "asset.asset:update",
        "partial_update": "asset.asset:update",
        "destroy": "asset.asset:delete",
        "calculate_depreciation": "asset.asset:update",
    }

    def has_permission(self, request: object, view: object) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        action = getattr(view, "action", "")
        permission = self.action_permissions.get(action)
        if permission is None:
            return False
        try:
            profile = user.profile
        except (AttributeError, ObjectDoesNotExist):
            profile = None
        try:
            UUID(str(getattr(profile, "tenant_id", "")))
        except (AttributeError, TypeError, ValueError):
            return False
        tenant_role = getattr(profile, "tenant_role", "")
        if tenant_role in {"tenant_admin", "system_admin", "super_admin"} or getattr(user, "is_superuser", False):
            return True
        return bool(user.has_perm(permission))


class IsDepreciationReader(IsAssetUser):
    action_permissions = {
        # Routers set action=None for unsupported methods. Authorizing the
        # read capability here lets DRF return the truthful 405; no mutation
        # handler exists and undeclared ViewSet actions remain fail-closed.
        None: "asset.depreciation:read",
        "list": "asset.depreciation:read",
        "retrieve": "asset.depreciation:read",
    }


__all__ = ["IsAssetUser", "IsDepreciationReader"]
