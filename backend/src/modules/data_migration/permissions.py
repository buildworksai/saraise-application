"""
DataMigration Permissions.

Defines permissions for the DataMigration module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "data_migration.resource:create",
    "data_migration.resource:read",
    "data_migration.resource:update",
    "data_migration.resource:delete",
    "data_migration.resource:activate",
    "data_migration.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "data_migration.resource:create",
    "data_migration.resource:delete",
]
