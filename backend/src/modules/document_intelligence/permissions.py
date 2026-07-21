"""Action-aware, fail-closed access declarations for API v2."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id

PERMISSIONS: Final[tuple[str, ...]] = (
    "document_intelligence.extraction:read",
    "document_intelligence.extraction:create",
    "document_intelligence.extraction:cancel",
    "document_intelligence.extraction:retry",
    "document_intelligence.extraction:delete",
    "document_intelligence.classification:read",
    "document_intelligence.classification:create",
    "document_intelligence.classification:review",
    "document_intelligence.classification:cancel",
    "document_intelligence.classification:retry",
    "document_intelligence.classification:delete",
    "document_intelligence.template:read",
    "document_intelligence.template:create",
    "document_intelligence.template:update",
    "document_intelligence.template:delete",
    "document_intelligence.template:activate",
    "document_intelligence.training:read",
    "document_intelligence.training:create",
    "document_intelligence.training:cancel",
    "document_intelligence.training:retry",
    "document_intelligence.model:read",
    "document_intelligence.model:activate",
    "document_intelligence.model:rollback",
    "document_intelligence.health:read",
)


class SessionAuthentication401(SessionAuthentication):
    """Strict CSRF-enforcing session auth that advertises a 401 challenge."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class ActionAccessMixin:
    """Resolve permission and quota from the already-selected DRF action."""

    authentication_classes = (SessionAuthentication401,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}
    action_quotas: dict[str, str] = {}

    def get_permissions(self) -> list[object]:
        action = getattr(self, "action", "")
        tenant_id = get_user_tenant_id(getattr(self.request, "user", None))
        if tenant_id is not None:
            try:
                self.request.tenant_id = UUID(str(tenant_id))
            except (TypeError, ValueError, AttributeError):
                # RequiresAccess will fail closed with a stable tenant denial.
                self.request.tenant_id = None
        self.required_permission = self.action_permissions.get(action)
        self.required_entitlement = self.required_permission
        self.quota_resource = self.action_quotas.get(
            action,
            (
                "document_intelligence.api_reads"
                if action in {"list", "retrieve", "pages", "scores"}
                else "document_intelligence.api_writes"
            ),
        )
        return [IsAuthenticated(), RequiresAccess()]


__all__ = ["ActionAccessMixin", "PERMISSIONS", "SessionAuthentication401"]
