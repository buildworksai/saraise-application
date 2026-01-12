"""
Backup & Recovery (Extended) Permissions.

Defines permissions for the Backup & Recovery module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "backup.job:create",
    "backup.job:read",
    "backup.job:update",
    "backup.job:delete",
    "backup.schedule:create",
    "backup.schedule:read",
    "backup.schedule:update",
    "backup.schedule:delete",
    "backup.retention:create",
    "backup.retention:read",
    "backup.retention:update",
    "backup.retention:delete",
    "backup.archive:read",
    "backup.restore:execute",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "backup.job:create",
    "backup.restore:execute",
]
