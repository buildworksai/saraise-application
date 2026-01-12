"""
AutomationOrchestration Permissions.

Defines permissions for the AutomationOrchestration module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "automation_orchestration.resource:create",
    "automation_orchestration.resource:read",
    "automation_orchestration.resource:update",
    "automation_orchestration.resource:delete",
    "automation_orchestration.resource:activate",
    "automation_orchestration.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "automation_orchestration.resource:create",
    "automation_orchestration.resource:delete",
]
