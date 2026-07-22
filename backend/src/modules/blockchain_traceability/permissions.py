"""Fail-closed, action-specific access declarations for traceability API v2."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id

NETWORK_READ: Final = "blockchain_traceability.network:read"
NETWORK_MANAGE: Final = "blockchain_traceability.network:manage"
NETWORK_PROBE: Final = "blockchain_traceability.network:probe"
ASSET_READ: Final = "blockchain_traceability.asset:read"
ASSET_CREATE: Final = "blockchain_traceability.asset:create"
ASSET_UPDATE: Final = "blockchain_traceability.asset:update"
ASSET_DELETE: Final = "blockchain_traceability.asset:delete"
ASSET_TRANSITION: Final = "blockchain_traceability.asset:transition"
EVENT_READ: Final = "blockchain_traceability.event:read"
EVENT_APPEND: Final = "blockchain_traceability.event:append"
EVENT_VERIFY: Final = "blockchain_traceability.event:verify"
ANCHOR_READ: Final = "blockchain_traceability.anchor:read"
ANCHOR_CREATE: Final = "blockchain_traceability.anchor:create"
ANCHOR_RETRY: Final = "blockchain_traceability.anchor:retry"
ANCHOR_VERIFY: Final = "blockchain_traceability.anchor:verify"
CREDENTIAL_READ: Final = "blockchain_traceability.credential:read"
CREDENTIAL_ISSUE: Final = "blockchain_traceability.credential:issue"
CREDENTIAL_REVOKE: Final = "blockchain_traceability.credential:revoke"
CREDENTIAL_VERIFY: Final = "blockchain_traceability.credential:verify"
COMPLIANCE_READ: Final = "blockchain_traceability.compliance:read"
COMPLIANCE_CREATE: Final = "blockchain_traceability.compliance:create"
COMPLIANCE_UPDATE: Final = "blockchain_traceability.compliance:update"
COMPLIANCE_DELETE: Final = "blockchain_traceability.compliance:delete"
COMPLIANCE_FINALIZE: Final = "blockchain_traceability.compliance:finalize"
COMPLIANCE_VERIFY: Final = "blockchain_traceability.compliance:verify"
VERIFICATION_READ: Final = "blockchain_traceability.verification:read"
HEALTH_READ: Final = "blockchain_traceability.health:read"
CONFIG_READ: Final = "blockchain_traceability.configuration:read"
CONFIG_UPDATE: Final = "blockchain_traceability.configuration:update"
CONFIG_ROLLBACK: Final = "blockchain_traceability.configuration:rollback"
CONFIG_IMPORT: Final = "blockchain_traceability.configuration:import"
CONFIG_EXPORT: Final = "blockchain_traceability.configuration:export"

PERMISSIONS: Final[tuple[str, ...]] = (
    NETWORK_READ,
    NETWORK_MANAGE,
    NETWORK_PROBE,
    ASSET_READ,
    ASSET_CREATE,
    ASSET_UPDATE,
    ASSET_DELETE,
    ASSET_TRANSITION,
    EVENT_READ,
    EVENT_APPEND,
    EVENT_VERIFY,
    ANCHOR_READ,
    ANCHOR_CREATE,
    ANCHOR_RETRY,
    ANCHOR_VERIFY,
    CREDENTIAL_READ,
    CREDENTIAL_ISSUE,
    CREDENTIAL_REVOKE,
    CREDENTIAL_VERIFY,
    COMPLIANCE_READ,
    COMPLIANCE_CREATE,
    COMPLIANCE_UPDATE,
    COMPLIANCE_DELETE,
    COMPLIANCE_FINALIZE,
    COMPLIANCE_VERIFY,
    VERIFICATION_READ,
    HEALTH_READ,
    CONFIG_READ,
    CONFIG_UPDATE,
    CONFIG_ROLLBACK,
    CONFIG_IMPORT,
    CONFIG_EXPORT,
)

# These pairs are the executable separation-of-duties policy. The manifest
# carries the same pair structure and startup validation rejects any drift.
SOD_ACTIONS: Final[tuple[tuple[str, str], ...]] = (
    (NETWORK_MANAGE, ANCHOR_VERIFY),
    (CREDENTIAL_ISSUE, CREDENTIAL_REVOKE),
    (COMPLIANCE_CREATE, COMPLIANCE_FINALIZE),
    (CONFIG_UPDATE, CONFIG_ROLLBACK),
)


class SessionAuthentication401(SessionAuthentication):
    """Strict CSRF-enforcing session authentication with an explicit challenge."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class ActionAccessMixin:
    """Bind each DRF action to an explicit permission, entitlement and quota."""

    authentication_classes = (SessionAuthentication401,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}
    action_quotas: dict[str, str] = {}
    unsupported_method_permission: str | None = None
    read_actions: frozenset[str] = frozenset({"list", "retrieve", "history"})

    def get_permissions(self) -> list[object]:
        action_name = getattr(self, "action", "")
        raw_tenant_id = get_user_tenant_id(getattr(self.request, "user", None))
        try:
            self.request.tenant_id = UUID(str(raw_tenant_id)) if raw_tenant_id else None
        except (AttributeError, TypeError, ValueError):
            # RequiresAccess deliberately fails closed for invalid ownership.
            self.request.tenant_id = None

        permission = self.action_permissions.get(action_name)
        allowed_methods = getattr(self, "http_method_names", ())
        if permission is None and self.request.method.lower() not in allowed_methods:
            permission = self.unsupported_method_permission
        self.required_permission = permission
        self.required_entitlement = permission
        self.quota_resource = self.action_quotas.get(
            action_name,
            (
                "blockchain_traceability.api_reads"
                if action_name in self.read_actions
                else "blockchain_traceability.api_writes"
            ),
        )
        self.quota_cost = 1
        return super().get_permissions()


__all__ = [
    "ANCHOR_CREATE",
    "ANCHOR_READ",
    "ANCHOR_RETRY",
    "ANCHOR_VERIFY",
    "ASSET_CREATE",
    "ASSET_DELETE",
    "ASSET_READ",
    "ASSET_TRANSITION",
    "ASSET_UPDATE",
    "ActionAccessMixin",
    "COMPLIANCE_CREATE",
    "COMPLIANCE_DELETE",
    "COMPLIANCE_FINALIZE",
    "COMPLIANCE_READ",
    "COMPLIANCE_UPDATE",
    "COMPLIANCE_VERIFY",
    "CONFIG_EXPORT",
    "CONFIG_IMPORT",
    "CONFIG_READ",
    "CONFIG_ROLLBACK",
    "CONFIG_UPDATE",
    "CREDENTIAL_ISSUE",
    "CREDENTIAL_READ",
    "CREDENTIAL_REVOKE",
    "CREDENTIAL_VERIFY",
    "EVENT_APPEND",
    "EVENT_READ",
    "EVENT_VERIFY",
    "HEALTH_READ",
    "NETWORK_MANAGE",
    "NETWORK_PROBE",
    "NETWORK_READ",
    "PERMISSIONS",
    "SOD_ACTIONS",
    "SessionAuthentication401",
    "VERIFICATION_READ",
]
