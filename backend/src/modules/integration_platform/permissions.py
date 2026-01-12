"""
IntegrationPlatform Permissions.

Defines permissions for the IntegrationPlatform module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "integration_platform.resource:create",
    "integration_platform.resource:read",
    "integration_platform.resource:update",
    "integration_platform.resource:delete",
    "integration_platform.resource:activate",
    "integration_platform.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "integration_platform.resource:create",
    "integration_platform.resource:delete",
]
