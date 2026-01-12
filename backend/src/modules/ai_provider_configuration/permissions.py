"""
AiProviderConfiguration Permissions.

Defines permissions for the AiProviderConfiguration module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "ai_provider_configuration.resource:create",
    "ai_provider_configuration.resource:read",
    "ai_provider_configuration.resource:update",
    "ai_provider_configuration.resource:delete",
    "ai_provider_configuration.resource:activate",
    "ai_provider_configuration.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "ai_provider_configuration.resource:create",
    "ai_provider_configuration.resource:delete",
]
