"""Fail-closed access declarations for technical orchestration.

The strings in this module are part of the public module contract.  Keeping the
action map beside the manifest makes it straightforward for extensions and
security reviews to prove that every route has one explicit decision point.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFINITION_VIEW = "automation_orchestration.definition:view"
DEFINITION_MANAGE = "automation_orchestration.definition:manage"
DEFINITION_PUBLISH = "automation_orchestration.definition:publish"
SCHEDULE_VIEW = "automation_orchestration.schedule:view"
SCHEDULE_MANAGE = "automation_orchestration.schedule:manage"
RUN_VIEW = "automation_orchestration.run:view"
RUN_EXECUTE = "automation_orchestration.run:execute"
RUN_CONTROL = "automation_orchestration.run:control"
RUN_RETRY = "automation_orchestration.run:retry"
CATALOG_VIEW = "automation_orchestration.catalog:view"
# Configuration and health are governed by existing manifest permissions:
# configuration is definition policy, and health is runtime catalog metadata.
CONFIGURATION_VIEW = DEFINITION_VIEW
CONFIGURATION_MANAGE = DEFINITION_MANAGE
HEALTH_VIEW = CATALOG_VIEW

PERMISSIONS: tuple[str, ...] = (
    DEFINITION_VIEW,
    DEFINITION_MANAGE,
    DEFINITION_PUBLISH,
    SCHEDULE_VIEW,
    SCHEDULE_MANAGE,
    RUN_VIEW,
    RUN_EXECUTE,
    RUN_CONTROL,
    RUN_RETRY,
    CATALOG_VIEW,
)

# Publishing and execution are deliberately separated from editing.  This is
# the only segregation-of-duties pair owned by this technical DAG module.
SOD_ACTIONS: tuple[tuple[str, str], ...] = ((DEFINITION_MANAGE, DEFINITION_PUBLISH),)


@dataclass(frozen=True)
class AccessRequirement:
    """Permission, entitlement and quota metadata for a ViewSet action."""

    permission: str
    entitlement: str
    quota_resource: str
    quota_cost: int = 1


def read_access(permission: str) -> AccessRequirement:
    """Declare a non-metered read without weakening policy or entitlement."""

    # Read capacity is deliberately distinct from execution capacity; viewing
    # history can never exhaust or decrement a tenant's run quota.
    return AccessRequirement(permission, permission, f"{permission}:read", 1)


def write_access(permission: str, *, cost: int = 1) -> AccessRequirement:
    """Declare a state-changing operation and its idempotent charge point."""

    return AccessRequirement(permission, permission, permission, cost)


__all__ = [
    "AccessRequirement",
    "CATALOG_VIEW",
    "CONFIGURATION_MANAGE",
    "CONFIGURATION_VIEW",
    "DEFINITION_MANAGE",
    "DEFINITION_PUBLISH",
    "DEFINITION_VIEW",
    "HEALTH_VIEW",
    "PERMISSIONS",
    "RUN_CONTROL",
    "RUN_EXECUTE",
    "RUN_RETRY",
    "RUN_VIEW",
    "SCHEDULE_MANAGE",
    "SCHEDULE_VIEW",
    "SOD_ACTIONS",
    "read_access",
    "write_access",
]
