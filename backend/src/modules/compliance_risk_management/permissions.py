"""Fail-closed access declarations for the compliance-risk API.

ViewSets consume these immutable declarations and pass them to
``src.core.access.RequiresAccess``.  Role names deliberately do not appear in
this module: tenant policy owns role-to-permission assignment.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping
from uuid import UUID

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request

from src.core.access import RequiresAccess
from src.core.auth_utils import get_user_tenant_id


class GovernedSessionAuthentication(SessionAuthentication):
    """Preserve session CSRF enforcement while returning an HTTP 401 challenge."""

    def authenticate_header(self, request: Request) -> str:
        del request
        return "Session"


class ActionAccessMixin:
    """Resolve DRF action metadata and deny when any declaration is absent.

    API classes may supply simple ``action_permissions`` strings or the richer
    ``action_access`` declarations exported below.  This keeps the public API
    concise while retaining explicit entitlement and quota metadata.
    """

    authentication_classes = (GovernedSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: Mapping[str, str] = MappingProxyType({})
    action_access: Mapping[str, "AccessRequirement"] = MappingProxyType({})
    action_quotas: Mapping[str, str] = MappingProxyType({})
    request: Request

    def get_permissions(self) -> list[object]:
        request = self.request
        raw_tenant = get_user_tenant_id(getattr(request, "user", None))
        try:
            request.tenant_id = UUID(str(raw_tenant)) if raw_tenant is not None else None
        except (TypeError, ValueError, AttributeError):
            request.tenant_id = None

        raw_action = getattr(self, "action", None)
        action = str(raw_action) if raw_action else ""
        if not action:
            # DRF resolves unsupported HTTP verbs without an action.  There is
            # no domain operation to authorize in that case; authentication is
            # still required before DRF returns the canonical 405 response.
            return [IsAuthenticated()]
        requirement = self.action_access.get(action)
        permission = requirement.permission if requirement else self.action_permissions.get(action)
        self.required_permission = permission
        self.required_entitlement = requirement.entitlement if requirement else (ENTITLEMENT if permission else None)
        self.quota_resource = (
            requirement.quota_resource
            if requirement
            else self.action_quotas.get(action, f"compliance_risk.{action}" if permission else None)
        )
        self.quota_cost = requirement.quota_cost if requirement else 1
        return [IsAuthenticated(), RequiresAccess()]


@dataclass(frozen=True, slots=True)
class AccessRequirement:
    """Complete access metadata for one API action."""

    permission: str
    entitlement: str
    quota_resource: str
    quota_cost: int = 1

    def __post_init__(self) -> None:
        if not self.permission or not self.entitlement or not self.quota_resource:
            raise ValueError("Compliance-risk access metadata must be complete")
        if isinstance(self.quota_cost, bool) or self.quota_cost <= 0:
            raise ValueError("Compliance-risk quota cost must be a positive integer")


ENTITLEMENT: Final = "compliance_risk_management"

PERMISSIONS: Final[tuple[str, ...]] = (
    "compliance_risk.risk:read",
    "compliance_risk.risk:create",
    "compliance_risk.risk:update",
    "compliance_risk.risk:delete",
    "compliance_risk.risk:transition",
    "compliance_risk.risk:read_sensitive",
    "compliance_risk.control:read",
    "compliance_risk.control:create",
    "compliance_risk.control:update",
    "compliance_risk.control:delete",
    "compliance_risk.control:transition",
    "compliance_risk.test:read",
    "compliance_risk.test:schedule",
    "compliance_risk.test:execute",
    "compliance_risk.requirement:read",
    "compliance_risk.requirement:create",
    "compliance_risk.requirement:update",
    "compliance_risk.requirement:delete",
    "compliance_risk.requirement:assess",
    "compliance_risk.calendar:read",
    "compliance_risk.calendar:create",
    "compliance_risk.calendar:update",
    "compliance_risk.calendar:delete",
    "compliance_risk.calendar:transition",
    "compliance_risk.remediation:read",
    "compliance_risk.remediation:create",
    "compliance_risk.remediation:update",
    "compliance_risk.remediation:delete",
    "compliance_risk.remediation:transition",
    "compliance_risk.dashboard:read",
    "compliance_risk.configuration:read",
    "compliance_risk.configuration:manage",
    "compliance_risk.configuration:rollback",
    "compliance_risk.health:read",
)


def _rule(permission: str, quota_resource: str, *, cost: int = 1) -> AccessRequirement:
    if permission not in PERMISSIONS:
        raise ValueError(f"Unknown compliance-risk permission: {permission}")
    return AccessRequirement(permission, ENTITLEMENT, quota_resource, cost)


def _actions(**rules: AccessRequirement) -> Mapping[str, AccessRequirement]:
    return MappingProxyType(rules)


RISK_ACTIONS: Final = _actions(
    list=_rule("compliance_risk.risk:read", "compliance_risk.risk_reads"),
    retrieve=_rule("compliance_risk.risk:read", "compliance_risk.risk_reads"),
    create=_rule("compliance_risk.risk:create", "compliance_risk.risk_writes"),
    partial_update=_rule("compliance_risk.risk:update", "compliance_risk.risk_writes"),
    destroy=_rule("compliance_risk.risk:delete", "compliance_risk.risk_writes"),
    transition=_rule("compliance_risk.risk:transition", "compliance_risk.risk_transitions"),
    score_preview=_rule("compliance_risk.risk:create", "compliance_risk.score_previews"),
    controls=_rule("compliance_risk.control:read", "compliance_risk.control_reads"),
    remediations=_rule("compliance_risk.remediation:read", "compliance_risk.remediation_reads"),
)
CONTROL_ACTIONS: Final = _actions(
    list=_rule("compliance_risk.control:read", "compliance_risk.control_reads"),
    retrieve=_rule("compliance_risk.control:read", "compliance_risk.control_reads"),
    create=_rule("compliance_risk.control:create", "compliance_risk.control_writes"),
    partial_update=_rule("compliance_risk.control:update", "compliance_risk.control_writes"),
    destroy=_rule("compliance_risk.control:delete", "compliance_risk.control_writes"),
    transition=_rule("compliance_risk.control:transition", "compliance_risk.control_transitions"),
    tests=_rule("compliance_risk.test:read", "compliance_risk.test_reads"),
)
TEST_ACTIONS: Final = _actions(
    list=_rule("compliance_risk.test:read", "compliance_risk.test_reads"),
    retrieve=_rule("compliance_risk.test:read", "compliance_risk.test_reads"),
    create=_rule("compliance_risk.test:schedule", "compliance_risk.test_schedules"),
    partial_update=_rule("compliance_risk.test:schedule", "compliance_risk.test_schedules"),
    start=_rule("compliance_risk.test:execute", "compliance_risk.test_executions"),
    result=_rule("compliance_risk.test:execute", "compliance_risk.test_executions"),
    cancel=_rule("compliance_risk.test:execute", "compliance_risk.test_executions"),
)
REQUIREMENT_ACTIONS: Final = _actions(
    list=_rule("compliance_risk.requirement:read", "compliance_risk.requirement_reads"),
    retrieve=_rule("compliance_risk.requirement:read", "compliance_risk.requirement_reads"),
    create=_rule("compliance_risk.requirement:create", "compliance_risk.requirement_writes"),
    partial_update=_rule("compliance_risk.requirement:update", "compliance_risk.requirement_writes"),
    destroy=_rule("compliance_risk.requirement:delete", "compliance_risk.requirement_writes"),
    assess=_rule("compliance_risk.requirement:assess", "compliance_risk.requirement_assessments"),
)
CALENDAR_ACTIONS: Final = _actions(
    list=_rule("compliance_risk.calendar:read", "compliance_risk.calendar_reads"),
    retrieve=_rule("compliance_risk.calendar:read", "compliance_risk.calendar_reads"),
    create=_rule("compliance_risk.calendar:create", "compliance_risk.calendar_writes"),
    partial_update=_rule("compliance_risk.calendar:update", "compliance_risk.calendar_writes"),
    destroy=_rule("compliance_risk.calendar:delete", "compliance_risk.calendar_writes"),
    transition=_rule("compliance_risk.calendar:transition", "compliance_risk.calendar_transitions"),
)
REMEDIATION_ACTIONS: Final = _actions(
    list=_rule("compliance_risk.remediation:read", "compliance_risk.remediation_reads"),
    retrieve=_rule("compliance_risk.remediation:read", "compliance_risk.remediation_reads"),
    create=_rule("compliance_risk.remediation:create", "compliance_risk.remediation_writes"),
    partial_update=_rule("compliance_risk.remediation:update", "compliance_risk.remediation_writes"),
    destroy=_rule("compliance_risk.remediation:delete", "compliance_risk.remediation_writes"),
    transition=_rule("compliance_risk.remediation:transition", "compliance_risk.remediation_transitions"),
)
DASHBOARD_ACTIONS: Final = _actions(get=_rule("compliance_risk.dashboard:read", "compliance_risk.dashboard_reads"))
HEATMAP_ACTIONS: Final = DASHBOARD_ACTIONS
CONFIGURATION_ACTIONS: Final = _actions(
    retrieve=_rule("compliance_risk.configuration:read", "compliance_risk.configuration_reads"),
    list=_rule("compliance_risk.configuration:read", "compliance_risk.configuration_reads"),
    update=_rule("compliance_risk.configuration:manage", "compliance_risk.configuration_writes"),
    preview=_rule("compliance_risk.configuration:manage", "compliance_risk.configuration_previews"),
    versions=_rule("compliance_risk.configuration:read", "compliance_risk.configuration_reads"),
    version_detail=_rule("compliance_risk.configuration:read", "compliance_risk.configuration_reads"),
    rollback=_rule("compliance_risk.configuration:rollback", "compliance_risk.configuration_rollbacks"),
    export=_rule("compliance_risk.configuration:read", "compliance_risk.configuration_exports"),
    import_document=_rule("compliance_risk.configuration:manage", "compliance_risk.configuration_imports"),
)
JOB_ACTIONS: Final = _actions(retrieve=_rule("compliance_risk.dashboard:read", "compliance_risk.job_reads"))
HEALTH_ACTIONS: Final = _actions(get=_rule("compliance_risk.health:read", "compliance_risk.health_reads"))

ACTION_ACCESS: Final[Mapping[str, Mapping[str, AccessRequirement]]] = MappingProxyType(
    {
        "risk": RISK_ACTIONS,
        "control": CONTROL_ACTIONS,
        "test": TEST_ACTIONS,
        "requirement": REQUIREMENT_ACTIONS,
        "calendar": CALENDAR_ACTIONS,
        "remediation": REMEDIATION_ACTIONS,
        "dashboard": DASHBOARD_ACTIONS,
        "heatmap": HEATMAP_ACTIONS,
        "configuration": CONFIGURATION_ACTIONS,
        "job": JOB_ACTIONS,
        "health": HEALTH_ACTIONS,
    }
)


def requirement_for(resource: str, action: str) -> AccessRequirement | None:
    """Return declared access metadata; unknown inputs intentionally return ``None``."""

    return ACTION_ACCESS.get(resource, {}).get(action)


# The former class authorized every authenticated principal.  Retaining its
# import name with RequiresAccess semantics is safe for downstream consumers.
IsComplianceRiskUser = RequiresAccess


__all__ = [
    "ACTION_ACCESS",
    "ActionAccessMixin",
    "AccessRequirement",
    "CALENDAR_ACTIONS",
    "CONFIGURATION_ACTIONS",
    "CONTROL_ACTIONS",
    "DASHBOARD_ACTIONS",
    "ENTITLEMENT",
    "GovernedSessionAuthentication",
    "HEALTH_ACTIONS",
    "HEATMAP_ACTIONS",
    "JOB_ACTIONS",
    "IsComplianceRiskUser",
    "PERMISSIONS",
    "REMEDIATION_ACTIONS",
    "REQUIREMENT_ACTIONS",
    "RISK_ACTIONS",
    "TEST_ACTIONS",
    "requirement_for",
]
