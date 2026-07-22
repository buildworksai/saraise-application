"""Fail-closed, action-aware authorization for multi-company API v2."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id

PERMISSIONS: Final[tuple[str, ...]] = (
    "multi_company.company:read", "multi_company.company:create",
    "multi_company.company:update", "multi_company.company:deactivate",
    "multi_company.company:delete", "multi_company.company:read_sensitive",
    "multi_company.company_access:read", "multi_company.company_access:grant",
    "multi_company.company_access:revoke", "multi_company.transaction:read",
    "multi_company.transaction:create", "multi_company.transaction:update",
    "multi_company.transaction:submit", "multi_company.transaction:approve",
    "multi_company.transaction:post", "multi_company.transaction:dispute",
    "multi_company.transaction:cancel", "multi_company.transaction:reverse",
    "multi_company.consolidation:read", "multi_company.consolidation:create",
    "multi_company.consolidation:update", "multi_company.consolidation:execute",
    "multi_company.consolidation:approve", "multi_company.consolidation:publish",
    "multi_company.elimination:read", "multi_company.elimination:create",
    "multi_company.transfer_pricing:read", "multi_company.transfer_pricing:create",
    "multi_company.transfer_pricing:update", "multi_company.transfer_pricing:delete",
    "multi_company.transfer_pricing:calculate", "multi_company.configuration:read",
    "multi_company.configuration:write", "multi_company.configuration:activate",
    "multi_company.configuration:rollback", "multi_company.configuration:import",
    "multi_company.configuration:export", "multi_company.extension:read",
    "multi_company.health:read",
)

SOD_ACTIONS: Final[tuple[str, ...]] = (
    "transaction_creator_vs_approver",
    "transaction_source_approver_vs_target_approver",
    "consolidation_executor_vs_approver",
    "consolidation_executor_vs_publisher",
    "production_configuration_author_vs_activator",
    "company_access_grantor_role_ceiling",
)


class SessionAuthentication401(SessionAuthentication):
    """Enforce normal DRF session CSRF while producing anonymous 401 responses."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class MultiCompanyAccessMixin:
    """Resolve tenant, permission, entitlement and quota before every action.

    An action absent from ``action_permissions`` leaves ``required_permission``
    unset; :class:`RequiresAccess` then denies it by default.
    """

    authentication_classes = (SessionAuthentication401,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}
    action_quotas: dict[str, str] = {}
    required_entitlement = "module.multi_company"

    def get_permissions(self) -> list[object]:
        raw_tenant = get_user_tenant_id(getattr(self.request, "user", None))
        try:
            self.request.tenant_id = UUID(str(raw_tenant)) if raw_tenant else None
        except (TypeError, ValueError, AttributeError):
            self.request.tenant_id = None
        action = str(getattr(self, "action", "") or getattr(self, "permission_action", ""))
        self.required_permission = self.action_permissions.get(action)
        self.required_entitlement = "module.multi_company"
        self.quota_resource = self.action_quotas.get(action)
        self.quota_cost = 1
        return [IsAuthenticated(), RequiresAccess()]


__all__ = [
    "MultiCompanyAccessMixin", "PERMISSIONS", "SOD_ACTIONS", "SessionAuthentication401",
]
