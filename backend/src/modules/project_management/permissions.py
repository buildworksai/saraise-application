"""Fail-closed, action-aware access declarations."""

from typing import Any, ClassVar
from uuid import UUID

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission, IsAuthenticated

from src.core.access import RequiresAccess
from src.core.auth_utils import get_user_tenant_id


class SessionAuthentication401(SessionAuthentication):
    def authenticate_header(self, request: object) -> str:
        return "Session"


class ActionAccessMixin:
    authentication_classes: ClassVar[Any] = (SessionAuthentication401,)
    permission_classes: ClassVar[Any] = (IsAuthenticated, RequiresAccess)
    action_permissions: ClassVar[dict[str, str]] = {}
    action_quotas: ClassVar[dict[str, str | None]] = {}
    archived_permission: ClassVar[str | None] = None
    entitlement: ClassVar[str] = "project_management.core"
    request: Any
    required_permission: str | None
    required_entitlement: str
    quota_resource: str | None
    quota_cost: int

    def get_permissions(self) -> list[BasePermission]:
        tenant = get_user_tenant_id(getattr(self.request, "user", None))
        try:
            self.request.tenant_id = UUID(str(tenant)) if tenant else None
        except (TypeError, ValueError, AttributeError):
            self.request.tenant_id = None
        action = str(getattr(self, "action", "") or getattr(self.request, "method", "")).lower()
        self.required_permission = self.action_permissions.get(action)
        self.required_entitlement = self.entitlement
        self.quota_resource = self.action_quotas.get(action)
        self.quota_cost = 1
        if action == "list" and str(self.request.query_params.get("include_archived", "")).lower() in {"1", "true"}:
            self.required_permission = self.archived_permission
        # The pre-existing v1 mount is a compatibility shim for self-hosted
        # clients. New capability/entitlement enforcement is authoritative on
        # v2; v1 retains its authenticated tenant boundary until removal.
        if str(getattr(self.request, "path", "")).startswith("/api/v1/project-management/"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), RequiresAccess()]


IsProjectUser = RequiresAccess
