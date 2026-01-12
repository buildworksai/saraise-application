"""
BackupDisasterRecovery Permissions.

Defines permissions for the BackupDisasterRecovery module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "backup_disaster_recovery.resource:create",
    "backup_disaster_recovery.resource:read",
    "backup_disaster_recovery.resource:update",
    "backup_disaster_recovery.resource:delete",
    "backup_disaster_recovery.resource:activate",
    "backup_disaster_recovery.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "backup_disaster_recovery.resource:create",
    "backup_disaster_recovery.resource:delete",
]
