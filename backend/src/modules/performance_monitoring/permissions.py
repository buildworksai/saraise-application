"""
PerformanceMonitoring Permissions.

Defines permissions for the PerformanceMonitoring module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "performance_monitoring.resource:create",
    "performance_monitoring.resource:read",
    "performance_monitoring.resource:update",
    "performance_monitoring.resource:delete",
    "performance_monitoring.resource:activate",
    "performance_monitoring.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "performance_monitoring.resource:create",
    "performance_monitoring.resource:delete",
]
