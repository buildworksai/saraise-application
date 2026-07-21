"""Action-aware fail-closed authorization for the v2 API."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id

PERMISSIONS: Final[tuple[str, ...]] = (
    "process_mining.event:read", "process_mining.event:ingest",
    "process_mining.export:read", "process_mining.export:create", "process_mining.export:download",
    "process_mining.export:cancel", "process_mining.export:delete",
    "process_mining.discovery:read", "process_mining.discovery:create", "process_mining.discovery:cancel",
    "process_mining.discovery:retry", "process_mining.discovery:delete",
    "process_mining.model:read", "process_mining.model:create", "process_mining.model:update",
    "process_mining.model:delete", "process_mining.model:set_reference",
    "process_mining.conformance:read", "process_mining.conformance:create", "process_mining.conformance:cancel",
    "process_mining.conformance:retry", "process_mining.conformance:delete",
    "process_mining.bottleneck:read", "process_mining.bottleneck:create", "process_mining.bottleneck:cancel",
    "process_mining.bottleneck:retry", "process_mining.bottleneck:delete", "process_mining.health:read",
)
SOD_ACTIONS: Final[tuple[tuple[str, str], ...]] = ()


class SessionAuthentication401(SessionAuthentication):
    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class ActionAccessMixin:
    authentication_classes = (SessionAuthentication401,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}
    action_quotas: dict[str, str] = {}

    def get_permissions(self) -> list[object]:
        action = getattr(self, "action", "")
        tenant = get_user_tenant_id(getattr(self.request, "user", None))
        try:
            self.request.tenant_id = UUID(str(tenant)) if tenant else None
        except (TypeError, ValueError, AttributeError):
            self.request.tenant_id = None
        self.required_permission = self.action_permissions.get(action)
        self.required_entitlement = "process_mining.core"
        self.quota_resource = self.action_quotas.get(action, "process_mining.api_reads")
        self.quota_cost = 1
        return [IsAuthenticated(), RequiresAccess()]


__all__ = ["ActionAccessMixin", "PERMISSIONS", "SOD_ACTIONS", "SessionAuthentication401"]
