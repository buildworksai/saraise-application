"""Deny-default permission contract for performance monitoring."""

PERMISSIONS = [
    "performance_monitoring.telemetry:read",
    "performance_monitoring.telemetry:ingest",
    "performance_monitoring.telemetry:configure",
    "performance_monitoring.alert:read",
    "performance_monitoring.alert:manage",
    "performance_monitoring.alert:respond",
    "performance_monitoring.sla:read",
    "performance_monitoring.sla:manage",
    "performance_monitoring.report:generate",
    "performance_monitoring.extension:read",
    "performance_monitoring.health:read",
]

SOD_ACTIONS = [
    "performance_monitoring.telemetry:configure",
    "performance_monitoring.alert:manage",
    "performance_monitoring.sla:manage",
]

__all__ = ["PERMISSIONS", "SOD_ACTIONS"]
