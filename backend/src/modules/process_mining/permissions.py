"""
ProcessMining Permissions.

Defines permissions for the ProcessMining module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "process_mining.resource:create",
    "process_mining.resource:read",
    "process_mining.resource:update",
    "process_mining.resource:delete",
    "process_mining.resource:activate",
    "process_mining.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "process_mining.resource:create",
    "process_mining.resource:delete",
]
