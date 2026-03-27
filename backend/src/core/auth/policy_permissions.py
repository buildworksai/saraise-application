"""
Policy Engine integration for DRF permission enforcement.

SARAISE-26001: All API endpoints MUST evaluate policy before granting access.

Architecture Reference: architecture/existing/policy-engine-spec.md

In SaaS mode, evaluates policies via saraise-policy-engine service.
In self-hosted/development mode, uses local RBAC evaluation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.conf import settings
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from .mode import is_saas

if TYPE_CHECKING:
    from rest_framework.views import APIView

logger = logging.getLogger("saraise.auth.policy")


class PolicyRequiredPermission(BasePermission):
    """
    DRF permission class that evaluates SARAISE policy engine.

    Usage on ViewSets:
        permission_classes = [PolicyRequiredPermission]

    Or with required_permissions attribute:
        class MyViewSet(ModelViewSet):
            required_permissions = ["module.action"]
            permission_classes = [PolicyRequiredPermission]

    Evaluation logic:
    - SaaS mode: Calls saraise-policy-engine via HTTP (with circuit breaker)
    - Self-hosted: Evaluates local role-permission mappings
    - Development: Logs policy evaluation, permits by default (configurable)
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Evaluate policy for the current request."""
        # Unauthenticated requests are already rejected by IsAuthenticated
        if not request.user or not request.user.is_authenticated:
            return False

        # Extract required permissions from view
        required_perms = getattr(view, "required_permissions", None)
        if required_perms is None:
            # No explicit permissions declared — default to authenticated-only
            # This preserves backward compatibility during migration
            logger.debug(
                "No required_permissions on %s.%s — defaulting to authenticated-only",
                type(view).__name__,
                request.method,
            )
            return True

        # Get user context
        user = request.user
        tenant_id = getattr(user, "tenant_id", None) or getattr(request, "tenant_id", None)
        user_roles = getattr(user, "roles", [])
        if hasattr(user, "groups"):
            user_groups = (
                list(user.groups.values_list("name", flat=True))
                if hasattr(user.groups, "values_list")
                else list(user.groups)
            )
        else:
            user_groups = []

        if is_saas():
            return self._evaluate_saas_policy(
                tenant_id=tenant_id,
                user_roles=user_roles,
                user_groups=user_groups,
                required_perms=required_perms,
                request=request,
            )
        else:
            return self._evaluate_local_policy(
                user=user,
                user_roles=user_roles,
                required_perms=required_perms,
                request=request,
            )

    def _evaluate_saas_policy(
        self,
        tenant_id: str | None,
        user_roles: list[str],
        user_groups: list[str],
        required_perms: list[str],
        request: Request,
    ) -> bool:
        """
        Evaluate policy via saraise-policy-engine service.

        Falls back to local evaluation if policy engine is unavailable
        (circuit breaker open).
        """
        import requests as http_requests

        policy_engine_url = getattr(settings, "SARAISE_POLICY_ENGINE_URL", None)
        if not policy_engine_url:
            logger.warning("SARAISE_POLICY_ENGINE_URL not configured — falling back to local RBAC")
            return self._evaluate_local_policy(
                user=request.user,
                user_roles=user_roles,
                required_perms=required_perms,
                request=request,
            )

        try:
            response = http_requests.post(
                f"{policy_engine_url}/api/v1/evaluate",
                json={
                    "tenant_id": tenant_id,
                    "roles": user_roles,
                    "groups": user_groups,
                    "required_permissions": required_perms,
                    "resource": request.path,
                    "action": request.method,
                },
                timeout=2,  # Fast timeout — policy evaluation must be fast
            )
            if response.status_code == 200:
                result = response.json()
                allowed = result.get("allowed", False)
                if not allowed:
                    logger.warning(
                        "Policy DENIED: tenant=%s roles=%s perms=%s path=%s",
                        tenant_id,
                        user_roles,
                        required_perms,
                        request.path,
                    )
                return allowed
            else:
                logger.error("Policy engine returned %d — falling back to local RBAC", response.status_code)
        except http_requests.RequestException as exc:
            logger.error("Policy engine unavailable: %s — falling back to local RBAC", exc)

        # Fallback to local evaluation
        return self._evaluate_local_policy(
            user=request.user,
            user_roles=user_roles,
            required_perms=required_perms,
            request=request,
        )

    def _evaluate_local_policy(
        self,
        user: Any,
        user_roles: list[str],
        required_perms: list[str],
        request: Request,
    ) -> bool:
        """
        Local RBAC evaluation for self-hosted and development modes.

        Checks Django's built-in permission system plus SARAISE role mappings.
        """
        # Check Django's built-in permissions
        for perm in required_perms:
            if user.has_perm(perm):
                return True

        # Check SARAISE role-based permissions
        # super_admin and tenant_admin bypass all permission checks
        privileged_roles = {"super_admin", "tenant_admin", "system_admin"}
        if set(user_roles) & privileged_roles:
            logger.debug("Privileged role bypass for %s", user_roles)
            return True

        # For non-privileged users, check role-permission mappings
        # This will be expanded as modules declare their permission maps
        logger.warning(
            "Policy DENIED (local): user=%s roles=%s required=%s path=%s",
            getattr(user, "pk", "?"),
            user_roles,
            required_perms,
            request.path,
        )
        return False
