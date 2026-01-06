"""AI Agent Management Permissions.

Defines permissions for the AI Agent Management module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "ai.agent:create",
    "ai.agent:execute",
    "ai.agent:view",
    "ai.agent:update",
    "ai.agent:delete",
    "ai.agent:pause",
    "ai.agent:resume",
    "ai.agent:terminate",
    "ai.tool:register",
    "ai.tool:view",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "ai.agent:execute",
    "ai.agent:terminate",
]

