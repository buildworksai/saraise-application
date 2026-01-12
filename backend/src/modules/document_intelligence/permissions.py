"""
DocumentIntelligence Permissions.

Defines permissions for the DocumentIntelligence module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "document_intelligence.resource:create",
    "document_intelligence.resource:read",
    "document_intelligence.resource:update",
    "document_intelligence.resource:delete",
    "document_intelligence.resource:activate",
    "document_intelligence.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "document_intelligence.resource:create",
    "document_intelligence.resource:delete",
]
