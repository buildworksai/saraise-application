"""
Regional Permissions.

Defines permissions for the Regional module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "regional.resource:create",
    "regional.resource:read",
    "regional.resource:update",
    "regional.resource:delete",
    "regional.resource:activate",
    "regional.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "regional.resource:create",
    "regional.resource:delete",
]
