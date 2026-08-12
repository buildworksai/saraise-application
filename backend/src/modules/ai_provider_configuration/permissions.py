"""Action-aware access policy for AI-provider configuration."""

from __future__ import annotations

from typing import Any, Final, Mapping

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from src.core.access import AccessDecisionPipeline
from src.core.auth_utils import get_user_tenant_id

PERMISSIONS: Final[tuple[str, ...]] = (
    "ai_provider_configuration.provider:read",
    "ai_provider_configuration.resource:read",
    "ai_provider_configuration.resource:create",
    "ai_provider_configuration.resource:update",
    "ai_provider_configuration.resource:delete",
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
    "ai_provider_configuration.configuration:read",
    "ai_provider_configuration.configuration:update",
    "ai_provider_configuration.configuration:preview",
    "ai_provider_configuration.configuration:rollback",
    "ai_provider_configuration.configuration:import",
    "ai_provider_configuration.configuration:export",
    "ai_provider_configuration.configuration:audit",
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
    """Require explicit manifest-declared grants for every action."""

    message = "You do not have permission to manage AI provider configuration."
    pipeline = AccessDecisionPipeline()

    def has_permission(self, request: Request, view: object) -> bool:
        user = getattr(request, "user", None)
        if user is None or not bool(getattr(user, "is_authenticated", False)):
            return False
        action = str(getattr(view, "action", ""))
        required = getattr(view, "action_permissions", {}).get(action)
        setattr(view, "required_permission", required)
        if not required:
            return False
        tenant_id = get_user_tenant_id(user)
        setattr(request, "tenant_id", tenant_id)
        decision = self.pipeline.decide(
            tenant_id,
            user,
            required,
            entitlement=getattr(view, "required_entitlement", required),
            quota=getattr(view, "quota_resource", required),
            quota_cost=getattr(view, "quota_cost", 1),
            request=request,
        )
        setattr(request, "access_decision", decision)
        return decision.allowed


class TenantProviderThrottle(SimpleRateThrottle):
    """Bound traffic per tenant without trusting a request header."""

    scope = "ai_provider_configuration"

    def get_rate(self) -> str | None:
        from .services import AIProviderRuntimeConfigurationService, _section

        tenant_id = None
        request = getattr(self, "request", None)
        if request is not None:
            tenant_id = get_user_tenant_id(getattr(request, "user", None))
        values = AIProviderRuntimeConfigurationService.runtime_values(tenant_id)
        rate_limits = _section(values, "rate_limits")
        limit = rate_limits.get("tenant_requests_per_minute") if isinstance(rate_limits, Mapping) else None
        if not isinstance(limit, int):
            limit = 120
        return f"{limit}/min"

    def allow_request(self, request: Request, view: APIView) -> bool:
        self.request = request
        return super().allow_request(request, view)

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
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

    authentication_classes: Any = (SessionAuthentication401,)
    permission_classes: Any = (IsAuthenticated, AIProviderActionPermission)
    throttle_classes: Any = (TenantProviderThrottle,)
    action_permissions: dict[str, str] = {}


__all__ = [
    "AIProviderActionPermission",
    "ActionPermissionMixin",
    "PERMISSIONS",
    "SOD_ACTIONS",
    "SessionAuthentication401",
    "TenantProviderThrottle",
]
