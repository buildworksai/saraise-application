"""Authorization contract for backup and disaster recovery.

Permissions are intentionally operation-specific.  Views must select a rule
from :data:`ACCESS_RULES` before ``RequiresAccess`` is evaluated; an unknown
action is therefore denied rather than inheriting a broad CRUD permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

ENTITLEMENT = "backup_disaster_recovery"


@dataclass(frozen=True, slots=True)
class AccessRule:
    """Policy, entitlement, and metering inputs for one API action."""

    permission: str
    quota_resource: str
    quota_key: str = "default"
    entitlement: str = ENTITLEMENT

    def quota_cost_for(self, tenant_id: UUID) -> int:
        """Resolve metering from the validated tenant configuration."""

        from .services import get_configuration

        document = get_configuration(tenant_id).document
        quota_costs = document.get("quota_costs")
        if not isinstance(quota_costs, dict):
            raise RuntimeError("quota_costs configuration is unavailable")
        value = quota_costs.get(self.quota_key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RuntimeError(f"quota cost {self.quota_key!r} is unavailable")
        return value


READ = AccessRule("backup_disaster_recovery.*:read", "bdr.api.read")
BACKUP_READ = AccessRule("backup_disaster_recovery.backup:read", "bdr.api.read")
BACKUP_EXECUTE = AccessRule("backup_disaster_recovery.backup:execute", "bdr.backup.execute", "backup_execution")
VERIFY_POINT = AccessRule(
    "backup_disaster_recovery.recovery_point:verify",
    "bdr.verification.execute",
    "verification",
)
RESTORE_CREATE = AccessRule("backup_disaster_recovery.restore:create", "bdr.restore.validate", "restore_validation")
RESTORE_EXECUTE = AccessRule("backup_disaster_recovery.restore:execute", "bdr.restore.execute", "restore_execution")
RUNBOOK_CREATE = AccessRule("backup_disaster_recovery.runbook:create", "bdr.api.write")
RUNBOOK_UPDATE = AccessRule("backup_disaster_recovery.runbook:update", "bdr.api.write")
RUNBOOK_DELETE = AccessRule("backup_disaster_recovery.runbook:delete", "bdr.api.write")
RUNBOOK_PUBLISH = AccessRule("backup_disaster_recovery.runbook:publish", "bdr.api.write")
EXERCISE_CREATE = AccessRule("backup_disaster_recovery.exercise:create", "bdr.api.write")
EXERCISE_UPDATE = AccessRule("backup_disaster_recovery.exercise:update", "bdr.api.write")
EXERCISE_EXECUTE = AccessRule("backup_disaster_recovery.exercise:execute", "bdr.exercise.execute", "exercise_execution")
REPORT_READ = AccessRule("backup_disaster_recovery.report:read", "bdr.api.read")
CONFIG_READ = AccessRule("backup_disaster_recovery.configuration:read", "bdr.configuration.read")
CONFIG_WRITE = AccessRule("backup_disaster_recovery.configuration:write", "bdr.configuration.write")
HEALTH_READ = AccessRule("backup_disaster_recovery.health:read", "bdr.health.read")


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
            CONFIG_READ,
            CONFIG_WRITE,
            HEALTH_READ,
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
    "configuration_read": CONFIG_READ,
    "configuration_write": CONFIG_WRITE,
    "health_read": HEALTH_READ,
}


__all__ = [
    "ACCESS_RULES",
    "AccessRule",
    "CONFIG_READ",
    "CONFIG_WRITE",
    "ENTITLEMENT",
    "HEALTH_READ",
    "PERMISSIONS",
    "SOD_ACTIONS",
]
