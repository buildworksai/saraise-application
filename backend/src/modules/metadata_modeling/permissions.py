"""
MetadataModeling Permissions.

Defines permissions for the MetadataModeling module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "metadata_modeling.resource:create",
    "metadata_modeling.resource:read",
    "metadata_modeling.resource:update",
    "metadata_modeling.resource:delete",
    "metadata_modeling.resource:activate",
    "metadata_modeling.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "metadata_modeling.resource:create",
    "metadata_modeling.resource:delete",
]
