"""Deny-by-default access declarations for the governed HR API.

The module deliberately contains no role names.  ``RequiresAccess`` resolves
these immutable permission, entitlement, and quota declarations through the
authoritative access policy for the current tenant and actor.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping

from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request


class GovernedSessionAuthentication(SessionAuthentication):
    """Use normal session authentication/CSRF while returning a real 401 challenge."""

    def authenticate_header(self, request: Request) -> str:
        del request
        return "Session"


@dataclass(frozen=True, slots=True)
class AccessRequirement:
    """Complete access metadata required to execute one DRF action."""

    permission: str
    entitlement: str
    quota_resource: str
    quota_cost: int = 1

    def __post_init__(self) -> None:
        if not self.permission or not self.entitlement or not self.quota_resource:
            raise ValueError("HR access declarations must be complete")
        if self.quota_cost <= 0:
            raise ValueError("HR quota cost must be positive")


ENTITLEMENT: Final = "human_resources"


def _rule(permission: str, quota_resource: str, *, cost: int = 1) -> AccessRequirement:
    return AccessRequirement(permission, ENTITLEMENT, quota_resource, cost)


DEPARTMENT_ACTION_PERMISSIONS: Final[Mapping[str, AccessRequirement]] = MappingProxyType(
    {
        "list": _rule("hr.department:read", "human_resources.department_reads"),
        "retrieve": _rule("hr.department:read", "human_resources.department_reads"),
        "tree": _rule("hr.department:read", "human_resources.department_reads"),
        "create": _rule("hr.department:create", "human_resources.department_writes"),
        "partial_update": _rule("hr.department:update", "human_resources.department_writes"),
        "destroy": _rule("hr.department:delete", "human_resources.department_writes"),
    }
)

EMPLOYEE_ACTION_PERMISSIONS: Final[Mapping[str, AccessRequirement]] = MappingProxyType(
    {
        "list": _rule("hr.employee:read", "human_resources.employee_reads"),
        "retrieve": _rule("hr.employee:read", "human_resources.employee_reads"),
        "reporting_tree": _rule("hr.employee:read", "human_resources.employee_reads"),
        "create": _rule("hr.employee:create", "human_resources.employee_writes"),
        "partial_update": _rule("hr.employee:update", "human_resources.employee_writes"),
        "destroy": _rule("hr.employee:delete", "human_resources.employee_writes"),
        "activate": _rule("hr.employee:transition", "human_resources.employee_transitions"),
        "deactivate": _rule("hr.employee:transition", "human_resources.employee_transitions"),
        "place_on_leave": _rule("hr.employee:transition", "human_resources.employee_transitions"),
        "return_from_leave": _rule("hr.employee:transition", "human_resources.employee_transitions"),
        "terminate": _rule("hr.employee:transition", "human_resources.employee_transitions"),
    }
)

ATTENDANCE_ACTION_PERMISSIONS: Final[Mapping[str, AccessRequirement]] = MappingProxyType(
    {
        "list": _rule("hr.attendance:read", "human_resources.attendance_reads"),
        "retrieve": _rule("hr.attendance:read", "human_resources.attendance_reads"),
        "create": _rule("hr.attendance:create", "human_resources.attendance_writes"),
        "partial_update": _rule("hr.attendance:update", "human_resources.attendance_writes"),
        "destroy": _rule("hr.attendance:delete", "human_resources.attendance_writes"),
        "clock_in": _rule("hr.attendance:clock", "human_resources.attendance_clock"),
        "clock_out": _rule("hr.attendance:clock", "human_resources.attendance_clock"),
    }
)

LEAVE_BALANCE_ACTION_PERMISSIONS: Final[Mapping[str, AccessRequirement]] = MappingProxyType(
    {
        "list": _rule("hr.leave_balance:read", "human_resources.leave_balance_reads"),
        "retrieve": _rule("hr.leave_balance:read", "human_resources.leave_balance_reads"),
        "create": _rule("hr.leave_balance:create", "human_resources.leave_balance_writes"),
        "partial_update": _rule("hr.leave_balance:adjust", "human_resources.leave_balance_adjustments"),
        "destroy": _rule("hr.leave_balance:delete", "human_resources.leave_balance_writes"),
    }
)

LEAVE_REQUEST_ACTION_PERMISSIONS: Final[Mapping[str, AccessRequirement]] = MappingProxyType(
    {
        "list": _rule("hr.leave_request:read", "human_resources.leave_request_reads"),
        "retrieve": _rule("hr.leave_request:read", "human_resources.leave_request_reads"),
        "create": _rule("hr.leave_request:create", "human_resources.leave_request_writes"),
        "partial_update": _rule("hr.leave_request:update", "human_resources.leave_request_writes"),
        "approve": _rule("hr.leave_request:approve", "human_resources.leave_request_approvals"),
        "reject": _rule("hr.leave_request:reject", "human_resources.leave_request_approvals"),
        "cancel": _rule("hr.leave_request:cancel", "human_resources.leave_request_transitions"),
        "destroy": _rule("hr.leave_request:delete", "human_resources.leave_request_writes"),
    }
)

HEALTH_ACTION_PERMISSIONS: Final[Mapping[str, AccessRequirement]] = MappingProxyType(
    {"get": _rule("hr.health:read", "human_resources.health_reads")}
)

ACTION_ACCESS: Final[Mapping[str, Mapping[str, AccessRequirement]]] = MappingProxyType(
    {
        "department": DEPARTMENT_ACTION_PERMISSIONS,
        "employee": EMPLOYEE_ACTION_PERMISSIONS,
        "attendance": ATTENDANCE_ACTION_PERMISSIONS,
        "leave-balance": LEAVE_BALANCE_ACTION_PERMISSIONS,
        "leave-request": LEAVE_REQUEST_ACTION_PERMISSIONS,
        "health": HEALTH_ACTION_PERMISSIONS,
    }
)

PERMISSIONS: Final[tuple[str, ...]] = tuple(
    sorted({rule.permission for actions in ACTION_ACCESS.values() for rule in actions.values()})
)


def requirement_for(resource: str, action: str) -> AccessRequirement | None:
    """Return access metadata, or ``None`` so the caller fails closed."""

    return ACTION_ACCESS.get(resource, {}).get(action)


__all__ = [
    "ACTION_ACCESS",
    "ATTENDANCE_ACTION_PERMISSIONS",
    "AccessRequirement",
    "DEPARTMENT_ACTION_PERMISSIONS",
    "EMPLOYEE_ACTION_PERMISSIONS",
    "ENTITLEMENT",
    "HEALTH_ACTION_PERMISSIONS",
    "LEAVE_BALANCE_ACTION_PERMISSIONS",
    "LEAVE_REQUEST_ACTION_PERMISSIONS",
    "PERMISSIONS",
    "GovernedSessionAuthentication",
    "requirement_for",
]
