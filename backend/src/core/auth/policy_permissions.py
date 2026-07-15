"""
Policy Engine integration for DRF permission enforcement.

SARAISE-26001: All API endpoints MUST evaluate policy before granting access.

Architecture Reference: architecture/existing/policy-engine-spec.md

In SaaS mode, evaluates policies via saraise-policy-engine service.
In self-hosted/development mode, uses local RBAC evaluation.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from .mode import is_saas

if TYPE_CHECKING:
    from rest_framework.views import APIView

logger = logging.getLogger("saraise.auth.policy")
T = TypeVar("T")


class _PolicyCircuitBreaker:
    """Thread-safe fail-fast guard for the external policy service."""

    def __init__(self, threshold: int = 5, reset_seconds: float = 30.0) -> None:
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self._failures = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    def call(
        self,
        operation: Callable[[], T],
        *,
        is_failure: Callable[[T], bool] | None = None,
    ) -> T:
        with self._lock:
            if self._failures >= self.threshold and time.monotonic() - self._opened_at < self.reset_seconds:
                raise RuntimeError("policy engine circuit breaker is open")
        try:
            result = operation()
        except Exception:
            with self._lock:
                self._failures += 1
                self._opened_at = time.monotonic()
            raise
        with self._lock:
            if is_failure is not None and is_failure(result):
                self._failures += 1
                self._opened_at = time.monotonic()
            else:
                self._failures = 0
        return result


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
    - Development: Uses the same local RBAC evaluation as self-hosted mode
    """

    _circuit_breaker = _PolicyCircuitBreaker()

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Evaluate policy for the current request."""
        # Unauthenticated requests are already rejected by IsAuthenticated
        if not request.user or not request.user.is_authenticated:
            return False

        # Extract required permissions from view
        required_perms = getattr(view, "required_permissions", None)
        if not required_perms:
            logger.error(
                "Policy DENIED: no required_permissions declared on %s.%s",
                type(view).__name__,
                request.method,
            )
            return False

        # Get user context
        user = request.user
        tenant_id = getattr(user, "tenant_id", None) or getattr(request, "tenant_id", None)
        user_roles = self._get_user_roles(user)
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

        Fails closed if policy configuration or the service is unavailable.
        """
        import requests as http_requests

        policy_engine_url = getattr(settings, "SARAISE_POLICY_ENGINE_URL", None)
        if not policy_engine_url:
            logger.error("Policy DENIED: SARAISE_POLICY_ENGINE_URL is not configured")
            return False

        try:
            response = self._circuit_breaker.call(
                lambda: http_requests.post(
                    f"{policy_engine_url}/api/v1/evaluate",
                    json={
                        "tenant_id": tenant_id,
                        "roles": user_roles,
                        "groups": user_groups,
                        "required_permissions": required_perms,
                        "resource": request.path,
                        "action": request.method,
                    },
                    timeout=2,
                ),
                is_failure=lambda result: result.status_code == 429 or result.status_code >= 500,
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
                logger.error("Policy DENIED: policy engine returned %d", response.status_code)
        except (http_requests.RequestException, RuntimeError) as exc:
            logger.error("Policy DENIED: policy engine unavailable: %s", exc)

        return False

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

        role_permissions = {
            "super_admin": ("",),
            "platform_owner": ("platform.", "security.", "tenant:", "tenant."),
            "platform_admin": ("platform.",),
            "platform_operator": ("platform.",),
            "security_admin": ("security.",),
            "tenant_admin": ("tenant:", "tenant."),
        }
        for role in user_roles:
            prefixes = role_permissions.get(role, ())
            if role == "platform_operator" and not all(permission.endswith(":read") for permission in required_perms):
                continue
            if prefixes and all(
                any(permission.startswith(prefix) for prefix in prefixes) for permission in required_perms
            ):
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

    @staticmethod
    def _get_user_roles(user: Any) -> list[str]:
        """Read roles from both delegated sessions and the real UserProfile model."""
        roles = set(getattr(user, "roles", []) or [])
        try:
            profile = user.profile
        except (AttributeError, ObjectDoesNotExist):
            profile = None
        if profile is not None:
            roles.update(role for role in (profile.platform_role, profile.tenant_role) if role)
        return sorted(roles)
