"""Fail-closed, action-specific access declarations for MDM API v2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

ENTITLEMENT: Final = "master_data_management"


@dataclass(frozen=True, slots=True)
class AccessRule:
    permission: str
    quota_resource: str | None = None
    quota_cost: int = 1
    entitlement: str = ENTITLEMENT


PERMISSIONS: Final[tuple[str, ...]] = (
    "mdm.entity_type:read",
    "mdm.entity_type:manage",
    "mdm.entity:read",
    "mdm.entity:create",
    "mdm.entity:update",
    "mdm.entity:archive",
    "mdm.entity:restore",
    "mdm.entity:rollback",
    "mdm.quality_rule:read",
    "mdm.quality_rule:manage",
    "mdm.quality_issue:read",
    "mdm.quality_issue:resolve",
    "mdm.matching_rule:read",
    "mdm.matching_rule:manage",
    "mdm.match:read",
    "mdm.match:review",
    "mdm.match:run",
    "mdm.merge:read",
    "mdm.merge:execute",
    "mdm.merge:reverse",
    "mdm.dashboard:read",
)


def access(permission: str, *, quota_resource: str | None = None, quota_cost: int = 1) -> AccessRule:
    if permission not in PERMISSIONS:
        raise ValueError(f"unknown MDM permission: {permission}")
    return AccessRule(permission, quota_resource, quota_cost)


ENTITY_TYPE_READ = access("mdm.entity_type:read")
ENTITY_TYPE_MANAGE = access("mdm.entity_type:manage")
ENTITY_READ = access("mdm.entity:read")
ENTITY_CREATE = access("mdm.entity:create")
ENTITY_UPDATE = access("mdm.entity:update")
ENTITY_ARCHIVE = access("mdm.entity:archive")
ENTITY_RESTORE = access("mdm.entity:restore")
ENTITY_ROLLBACK = access("mdm.entity:rollback")
QUALITY_RULE_READ = access("mdm.quality_rule:read")
QUALITY_RULE_MANAGE = access("mdm.quality_rule:manage")
QUALITY_ISSUE_READ = access("mdm.quality_issue:read")
QUALITY_ISSUE_RESOLVE = access("mdm.quality_issue:resolve")
MATCHING_RULE_READ = access("mdm.matching_rule:read")
MATCHING_RULE_MANAGE = access("mdm.matching_rule:manage")
MATCH_READ = access("mdm.match:read")
MATCH_REVIEW = access("mdm.match:review")
MATCH_RUN = access("mdm.match:run", quota_resource="mdm.match.scan", quota_cost=1)
QUALITY_SCAN = access("mdm.match:run", quota_resource="mdm.quality.scan", quota_cost=1)
MERGE_READ = access("mdm.merge:read")
MERGE_EXECUTE = access("mdm.merge:execute")
MERGE_REVERSE = access("mdm.merge:reverse")
DASHBOARD_READ = access("mdm.dashboard:read")


__all__ = ["AccessRule", "ENTITLEMENT", "PERMISSIONS"]
