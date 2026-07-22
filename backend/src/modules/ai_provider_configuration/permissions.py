"""Action-aware access policy for AI-provider configuration."""

from __future__ import annotations

from typing import Final

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.throttling import SimpleRateThrottle

from src.core.auth_utils import get_user_tenant_id, get_user_tenant_role

PERMISSIONS: Final[tuple[str, ...]] = (
    "ai_provider_configuration.provider:read",
    "ai_provider_configuration.credential:read",
    "ai_provider_configuration.credential:create",
    "ai_provider_configuration.credential:update",
    "ai_provider_configuration.credential:delete",
    "ai_provider_configuration.model:read",
    "ai_provider_configuration.deployment:read",
    "ai_provider_configuration.deployment:create",
    "ai_provider_configuration.deployment:update",
    "ai_provider_configuration.deployment:delete",
    "ai_provider_configuration.usage:read",
    "ai_provider_configuration.secret:rotate",
    "ai_provider_configuration.health:read",
)

SOD_ACTIONS: Final[tuple[tuple[str, str], ...]] = (
    (
        "ai_provider_configuration.credential:create",
        "ai_provider_configuration.credential:delete",
    ),
)


class SessionAuthentication401(SessionAuthentication):
    """Preserve session CSRF handling while making unauthenticated denial 401."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class AIProviderActionPermission(BasePermission):
    """Allow tenant reads and require an administrator or Django grant for writes."""

    message = "You do not have permission to manage AI provider configuration."
    SAFE_ACTIONS = frozenset({"list", "retrieve", "health"})
    ADMIN_ROLES = frozenset({"tenant_admin", "system_admin", "super_admin"})

    def has_permission(self, request: object, view: object) -> bool:
        user = getattr(request, "user", None)
        if user is None or not bool(getattr(user, "is_authenticated", False)):
            return False
        action = str(getattr(view, "action", ""))
        required = getattr(view, "action_permissions", {}).get(action)
        setattr(view, "required_permission", required)
        if not required:
            return False
        if bool(getattr(user, "is_superuser", False)):
            return True
        if action in self.SAFE_ACTIONS:
            return True
        if get_user_tenant_role(user) in self.ADMIN_ROLES:
            return True
        return bool(user.has_perm(required))


class TenantProviderThrottle(SimpleRateThrottle):
    """Bound traffic per tenant without trusting a request header."""

    scope = "ai_provider_configuration"
    rate = "120/min"

    def get_cache_key(self, request: object, view: object) -> str | None:
        del view
        user = getattr(request, "user", None)
        if user is None or not bool(getattr(user, "is_authenticated", False)):
            return None
        tenant_id = get_user_tenant_id(user)
        if tenant_id:
            return self.cache_format % {"scope": self.scope, "ident": f"tenant:{tenant_id}"}
        identifier = getattr(user, "pk", None)
        return self.cache_format % {"scope": self.scope, "ident": f"user:{identifier}"}


class ActionPermissionMixin:
    """Shared authentication and policy declaration for every ViewSet."""

    authentication_classes = (SessionAuthentication401,)
    permission_classes = (IsAuthenticated, AIProviderActionPermission)
    throttle_classes = (TenantProviderThrottle,)
    action_permissions: dict[str, str] = {}


__all__ = [
    "AIProviderActionPermission",
    "ActionPermissionMixin",
    "PERMISSIONS",
    "SOD_ACTIONS",
    "SessionAuthentication401",
    "TenantProviderThrottle",
]
