"""
WorkflowAutomation Permissions.

Defines permissions for the WorkflowAutomation module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "workflow_automation.resource:create",
    "workflow_automation.resource:read",
    "workflow_automation.resource:update",
    "workflow_automation.resource:delete",
    "workflow_automation.resource:activate",
    "workflow_automation.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "workflow_automation.resource:create",
    "workflow_automation.resource:delete",
]
