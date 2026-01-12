"""
Localization Permissions.

Defines permissions for the Localization module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "localization.resource:create",
    "localization.resource:read",
    "localization.resource:update",
    "localization.resource:delete",
    "localization.resource:activate",
    "localization.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "localization.resource:create",
    "localization.resource:delete",
]
