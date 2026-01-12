"""
BlockchainTraceability Permissions.

Defines permissions for the BlockchainTraceability module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "blockchain_traceability.resource:create",
    "blockchain_traceability.resource:read",
    "blockchain_traceability.resource:update",
    "blockchain_traceability.resource:delete",
    "blockchain_traceability.resource:activate",
    "blockchain_traceability.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "blockchain_traceability.resource:create",
    "blockchain_traceability.resource:delete",
]
