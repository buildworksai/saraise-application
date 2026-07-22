"""Fail-closed, action-aware access declarations."""
from uuid import UUID
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from src.core.access import RequiresAccess
from src.core.auth_utils import get_user_tenant_id


class SessionAuthentication401(SessionAuthentication):
    def authenticate_header(self, request): return "Session"


class ActionAccessMixin:
    authentication_classes = (SessionAuthentication401,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions = {}
    action_quotas = {}
    archived_permission = None
    entitlement = "project_management.core"
    def get_permissions(self):
        tenant = get_user_tenant_id(getattr(self.request, "user", None))
        try: self.request.tenant_id = UUID(str(tenant)) if tenant else None
        except (TypeError, ValueError, AttributeError): self.request.tenant_id = None
        action = str(getattr(self, "action", "")); self.required_permission = self.action_permissions.get(action); self.required_entitlement = self.entitlement; self.quota_resource = self.action_quotas.get(action); self.quota_cost = 1
        if action == "list" and str(self.request.query_params.get("include_archived", "")).lower() in {"1", "true"}:
            self.required_permission = self.archived_permission
        # The pre-existing v1 mount is a compatibility shim for self-hosted
        # clients. New capability/entitlement enforcement is authoritative on
        # v2; v1 retains its authenticated tenant boundary until removal.
        if str(getattr(self.request, "path", "")).startswith("/api/v1/project-management/"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), RequiresAccess()]


IsProjectUser = RequiresAccess
