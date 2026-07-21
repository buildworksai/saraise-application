"""Authorization contract for backup and disaster recovery.

Permissions are intentionally operation-specific.  Views must select a rule
from :data:`ACCESS_RULES` before ``RequiresAccess`` is evaluated; an unknown
action is therefore denied rather than inheriting a broad CRUD permission.
"""

from __future__ import annotations

from dataclasses import dataclass


ENTITLEMENT = "backup_disaster_recovery"


@dataclass(frozen=True, slots=True)
class AccessRule:
    """Policy, entitlement, and metering inputs for one API action."""

    permission: str
    quota_resource: str
    quota_cost: int = 1
    entitlement: str = ENTITLEMENT


READ = AccessRule("backup_disaster_recovery.*:read", "bdr.api.read")
BACKUP_READ = AccessRule("backup_disaster_recovery.backup:read", "bdr.api.read")
BACKUP_EXECUTE = AccessRule(
    "backup_disaster_recovery.backup:execute", "bdr.backup.execute", 10
)
VERIFY_POINT = AccessRule(
    "backup_disaster_recovery.recovery_point:verify",
    "bdr.verification.execute",
    5,
)
RESTORE_CREATE = AccessRule(
    "backup_disaster_recovery.restore:create", "bdr.restore.validate", 5
)
RESTORE_EXECUTE = AccessRule(
    "backup_disaster_recovery.restore:execute", "bdr.restore.execute", 25
)
RUNBOOK_CREATE = AccessRule(
    "backup_disaster_recovery.runbook:create", "bdr.api.write"
)
RUNBOOK_UPDATE = AccessRule(
    "backup_disaster_recovery.runbook:update", "bdr.api.write"
)
RUNBOOK_DELETE = AccessRule(
    "backup_disaster_recovery.runbook:delete", "bdr.api.write"
)
RUNBOOK_PUBLISH = AccessRule(
    "backup_disaster_recovery.runbook:publish", "bdr.api.write"
)
EXERCISE_CREATE = AccessRule(
    "backup_disaster_recovery.exercise:create", "bdr.api.write"
)
EXERCISE_UPDATE = AccessRule(
    "backup_disaster_recovery.exercise:update", "bdr.api.write"
)
EXERCISE_EXECUTE = AccessRule(
    "backup_disaster_recovery.exercise:execute", "bdr.exercise.execute", 20
)
REPORT_READ = AccessRule(
    "backup_disaster_recovery.report:read", "bdr.api.read"
)


PERMISSIONS = sorted(
    {
        rule.permission
        for rule in (
            READ,
            BACKUP_READ,
            BACKUP_EXECUTE,
            VERIFY_POINT,
            RESTORE_CREATE,
            RESTORE_EXECUTE,
            RUNBOOK_CREATE,
            RUNBOOK_UPDATE,
            RUNBOOK_DELETE,
            RUNBOOK_PUBLISH,
            EXERCISE_CREATE,
            EXERCISE_UPDATE,
            EXERCISE_EXECUTE,
            REPORT_READ,
        )
    }
)

SOD_ACTIONS = [
    "backup_disaster_recovery.restore:execute",
    "backup_disaster_recovery.runbook:publish",
]


# Exported for tests, installers, and OpenAPI tooling.  API ViewSets use their
# own complete action maps because DRF action names are view-specific.
ACCESS_RULES = {
    "read": READ,
    "backup_read": BACKUP_READ,
    "backup_execute": BACKUP_EXECUTE,
    "recovery_point_verify": VERIFY_POINT,
    "restore_create": RESTORE_CREATE,
    "restore_execute": RESTORE_EXECUTE,
    "runbook_create": RUNBOOK_CREATE,
    "runbook_update": RUNBOOK_UPDATE,
    "runbook_delete": RUNBOOK_DELETE,
    "runbook_publish": RUNBOOK_PUBLISH,
    "exercise_create": EXERCISE_CREATE,
    "exercise_update": EXERCISE_UPDATE,
    "exercise_execute": EXERCISE_EXECUTE,
    "report_read": REPORT_READ,
}


__all__ = ["ACCESS_RULES", "AccessRule", "ENTITLEMENT", "PERMISSIONS", "SOD_ACTIONS"]
