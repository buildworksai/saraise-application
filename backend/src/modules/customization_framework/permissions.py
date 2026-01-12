"""
CustomizationFramework Permissions.

Defines permissions for the CustomizationFramework module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "customization_framework.resource:create",
    "customization_framework.resource:read",
    "customization_framework.resource:update",
    "customization_framework.resource:delete",
    "customization_framework.resource:activate",
    "customization_framework.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "customization_framework.resource:create",
    "customization_framework.resource:delete",
]
