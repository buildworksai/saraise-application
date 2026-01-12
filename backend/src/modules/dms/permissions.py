"""
Dms Permissions.

Defines permissions for the Dms module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "dms.resource:create",
    "dms.resource:read",
    "dms.resource:update",
    "dms.resource:delete",
    "dms.resource:activate",
    "dms.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "dms.resource:create",
    "dms.resource:delete",
]
