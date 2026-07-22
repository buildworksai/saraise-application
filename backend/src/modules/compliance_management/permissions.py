"""Deny-by-default, action-aware access declarations for compliance API v2."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping
from uuid import UUID

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id

PERMISSIONS: Final[tuple[str, ...]] = (
    "compliance.framework:read",
    "compliance.framework:create",
    "compliance.framework:update",
    "compliance.framework:archive",
    "compliance.framework:activate",
    "compliance.framework:import",
    "compliance.framework:export",
    "compliance.requirement:read",
    "compliance.requirement:create",
    "compliance.requirement:update",
    "compliance.requirement:archive",
    "compliance.requirement:import",
    "compliance.policy:read",
    "compliance.policy:create",
    "compliance.policy:update",
    "compliance.policy:archive",
    "compliance.policy:version",
    "compliance.policy:submit",
    "compliance.policy:approve",
    "compliance.policy:publish",
    "compliance.mapping:read",
    "compliance.mapping:manage",
    "compliance.assessment:read",
    "compliance.assessment:create",
    "compliance.evidence:read",
    "compliance.evidence:create",
    "compliance.evidence:update",
    "compliance.evidence:archive",
    "compliance.evidence:validate",
    "compliance.evidence:link",
    "compliance.configuration:read",
    "compliance.configuration:manage",
    "compliance.configuration:activate",
    "compliance.configuration:rollback",
    "compliance.configuration:export",
    "compliance.audit:read",
    "compliance.dashboard:read",
    "compliance.job:read",
)

READ_PERMISSIONS: Final[frozenset[str]] = frozenset(
    permission
    for permission in PERMISSIONS
    if permission.endswith(":read") or permission.endswith(":validate") or permission.endswith(":export")
)
PERMISSION_QUOTAS: Final[dict[str, str]] = {
    permission: "compliance_management.api_reads"
    if permission in READ_PERMISSIONS
    else "compliance_management.api_writes"
    for permission in PERMISSIONS
}


@dataclass(frozen=True, slots=True)
class AccessRequirement:
    """Complete access declaration for one endpoint action."""

    permission: str
    entitlement: str
    quota_resource: str
    quota_cost: int = 1


def _access(permission: str) -> AccessRequirement:
    if permission not in PERMISSION_QUOTAS:
        raise ValueError(f"unknown compliance permission {permission!r}")
    return AccessRequirement(permission, permission, PERMISSION_QUOTAS[permission], 1)


_ACTION_ACCESS = {
    "framework.list": _access("compliance.framework:read"),
    "framework.retrieve": _access("compliance.framework:read"),
    "framework.create": _access("compliance.framework:create"),
    "framework.partial_update": _access("compliance.framework:update"),
    "framework.destroy": _access("compliance.framework:archive"),
    "framework.activate": _access("compliance.framework:activate"),
    "framework.export": _access("compliance.framework:export"),
    "framework.import_package": _access("compliance.framework:import"),
    "framework.status": _access("compliance.dashboard:read"),
    "requirement.list": _access("compliance.requirement:read"),
    "requirement.retrieve": _access("compliance.requirement:read"),
    "requirement.create": _access("compliance.requirement:create"),
    "requirement.partial_update": _access("compliance.requirement:update"),
    "requirement.destroy": _access("compliance.requirement:archive"),
    "requirement.restore": _access("compliance.requirement:update"),
    "requirement.import_rows": _access("compliance.requirement:import"),
    "policy.list": _access("compliance.policy:read"),
    "policy.retrieve": _access("compliance.policy:read"),
    "policy.create": _access("compliance.policy:create"),
    "policy.partial_update": _access("compliance.policy:update"),
    "policy.destroy": _access("compliance.policy:archive"),
    "policy.versions:get": _access("compliance.policy:read"),
    "policy.versions:post": _access("compliance.policy:version"),
    "policy.submit": _access("compliance.policy:submit"),
    "policy.request_changes": _access("compliance.policy:approve"),
    "policy.approve": _access("compliance.policy:approve"),
    "policy.publish": _access("compliance.policy:publish"),
    "policy.revise": _access("compliance.policy:version"),
    "mapping.list": _access("compliance.mapping:read"),
    "mapping.retrieve": _access("compliance.mapping:read"),
    "mapping.create": _access("compliance.mapping:manage"),
    "mapping.partial_update": _access("compliance.mapping:manage"),
    "mapping.destroy": _access("compliance.mapping:manage"),
    "mapping.bulk": _access("compliance.mapping:manage"),
    "assessment.list": _access("compliance.assessment:read"),
    "assessment.retrieve": _access("compliance.assessment:read"),
    "assessment.create": _access("compliance.assessment:create"),
    "assessment.scorecard": _access("compliance.dashboard:read"),
    "evidence.list": _access("compliance.evidence:read"),
    "evidence.retrieve": _access("compliance.evidence:read"),
    "evidence.create": _access("compliance.evidence:create"),
    "evidence.partial_update": _access("compliance.evidence:update"),
    "evidence.destroy": _access("compliance.evidence:archive"),
    "evidence.validate": _access("compliance.evidence:validate"),
    "evidence.requirements": _access("compliance.evidence:link"),
    "evidence-link.destroy": _access("compliance.evidence:link"),
    "configuration.list": _access("compliance.configuration:read"),
    "configuration.retrieve": _access("compliance.configuration:read"),
    "configuration.create": _access("compliance.configuration:manage"),
    "configuration.partial_update": _access("compliance.configuration:manage"),
    "configuration.preview": _access("compliance.configuration:read"),
    "configuration.activate": _access("compliance.configuration:activate"),
    "configuration.rollback": _access("compliance.configuration:rollback"),
    "configuration.export": _access("compliance.configuration:export"),
    "configuration.import_document": _access("compliance.configuration:manage"),
    "activity.list": _access("compliance.audit:read"),
    "dashboard.list": _access("compliance.dashboard:read"),
    "dashboard.retrieve": _access("compliance.dashboard:read"),
    "gap.list": _access("compliance.dashboard:read"),
    "job.retrieve": _access("compliance.job:read"),
}
ACTION_ACCESS: Final[Mapping[str, AccessRequirement]] = MappingProxyType(_ACTION_ACCESS)


def requirement_for(viewset: str, action: str, method: str | None = None) -> AccessRequirement | None:
    """Return explicit action metadata or ``None`` for fail-closed denial."""

    if method is not None:
        qualified = ACTION_ACCESS.get(f"{viewset}.{action}:{method.lower()}")
        if qualified is not None:
            return qualified
    return ACTION_ACCESS.get(f"{viewset}.{action}")

FRAMEWORK_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": "compliance.framework:read",
    "retrieve": "compliance.framework:read",
    "create": "compliance.framework:create",
    "partial_update": "compliance.framework:update",
    "destroy": "compliance.framework:archive",
    "activate": "compliance.framework:activate",
    "export": "compliance.framework:export",
    "import_framework": "compliance.framework:import",
    "status": "compliance.dashboard:read",
}
REQUIREMENT_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": "compliance.requirement:read",
    "retrieve": "compliance.requirement:read",
    "create": "compliance.requirement:create",
    "partial_update": "compliance.requirement:update",
    "destroy": "compliance.requirement:archive",
    "restore": "compliance.requirement:update",
    "import_requirements": "compliance.requirement:import",
}
POLICY_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": "compliance.policy:read",
    "retrieve": "compliance.policy:read",
    "create": "compliance.policy:create",
    "partial_update": "compliance.policy:update",
    "destroy": "compliance.policy:archive",
    "versions": "compliance.policy:read",
    "create_version": "compliance.policy:version",
    "submit": "compliance.policy:submit",
    "request_changes": "compliance.policy:approve",
    "approve": "compliance.policy:approve",
    "publish": "compliance.policy:publish",
    "revise": "compliance.policy:version",
}
MAPPING_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": "compliance.mapping:read",
    "retrieve": "compliance.mapping:read",
    "create": "compliance.mapping:manage",
    "partial_update": "compliance.mapping:manage",
    "destroy": "compliance.mapping:manage",
    "bulk": "compliance.mapping:manage",
}
ASSESSMENT_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": "compliance.assessment:read",
    "retrieve": "compliance.assessment:read",
    "create": "compliance.assessment:create",
    "scorecard": "compliance.dashboard:read",
}
EVIDENCE_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": "compliance.evidence:read",
    "retrieve": "compliance.evidence:read",
    "create": "compliance.evidence:create",
    "partial_update": "compliance.evidence:update",
    "destroy": "compliance.evidence:archive",
    "validate": "compliance.evidence:validate",
    "requirements": "compliance.evidence:link",
    "unlink": "compliance.evidence:link",
}
CONFIGURATION_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": "compliance.configuration:read",
    "retrieve": "compliance.configuration:read",
    "create": "compliance.configuration:manage",
    "partial_update": "compliance.configuration:manage",
    "preview": "compliance.configuration:read",
    "activate": "compliance.configuration:activate",
    "rollback": "compliance.configuration:rollback",
    "export": "compliance.configuration:export",
    "import_revision": "compliance.configuration:manage",
}


class StrictSessionAuthentication(SessionAuthentication):
    """Enforce normal Django CSRF checks while returning a 401 challenge."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class ComplianceActionAccessMixin:
    """Populate explicit permission, entitlement and quota metadata per action.

    Tenant identity is always rebound from the authenticated profile.  Headers,
    URL parameters, and request bodies can therefore never select a tenant.
    Missing action metadata deliberately remains unset and ``RequiresAccess``
    denies the request.
    """

    authentication_classes = (StrictSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}
    action_quotas: dict[str, str] = {}
    quota_cost = 1

    def get_permissions(self) -> list[object]:
        tenant_value = get_user_tenant_id(getattr(self.request, "user", None))
        try:
            self.request.tenant_id = UUID(str(tenant_value)) if tenant_value is not None else None
        except (AttributeError, TypeError, ValueError):
            self.request.tenant_id = None

        action = str(getattr(self, "action", ""))
        permission = self.action_permissions.get(action)
        self.required_permission = permission
        # Entitlements are projected per capability, not inferred from edition.
        self.required_entitlement = permission
        self.quota_resource = self.action_quotas.get(action) or (
            PERMISSION_QUOTAS.get(permission) if permission else None
        )
        self.quota_cost = 1
        return [IsAuthenticated(), RequiresAccess()]


# Compatibility name for callers that use the common module convention.
ActionAccessMixin = ComplianceActionAccessMixin

__all__ = [
    "ACTION_ACCESS",
    "ASSESSMENT_ACTION_PERMISSIONS",
    "AccessRequirement",
    "ActionAccessMixin",
    "ComplianceActionAccessMixin",
    "CONFIGURATION_ACTION_PERMISSIONS",
    "EVIDENCE_ACTION_PERMISSIONS",
    "FRAMEWORK_ACTION_PERMISSIONS",
    "MAPPING_ACTION_PERMISSIONS",
    "PERMISSIONS",
    "PERMISSION_QUOTAS",
    "POLICY_ACTION_PERMISSIONS",
    "REQUIREMENT_ACTION_PERMISSIONS",
    "StrictSessionAuthentication",
    "requirement_for",
]
