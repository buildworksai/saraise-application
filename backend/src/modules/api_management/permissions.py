"""
ApiManagement Permissions.

Defines permissions for the ApiManagement module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "api_management.resource:create",
    "api_management.resource:read",
    "api_management.resource:update",
    "api_management.resource:delete",
    "api_management.resource:activate",
    "api_management.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "api_management.resource:create",
    "api_management.resource:delete",
]
