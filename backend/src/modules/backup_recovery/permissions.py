"""Fail-closed action-level access declarations for backup recovery."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class AccessRule:
    permission: str
    required_entitlement: str = "backup-recovery"
    quota_resource: str = "backup-recovery.read"
    quota_cost: int = 0


def _rule(resource: str, action: str, *, quota: str | None = None, cost: int = 0) -> AccessRule:
    return AccessRule(
        permission=f"backup_recovery.{resource}:{action}",
        quota_resource=quota or f"backup-recovery.{resource}",
        quota_cost=cost,
    )


ACCESS_MAP = MappingProxyType(
    {
        "jobs": MappingProxyType(
            {
                "list": _rule("job", "read"),
                "retrieve": _rule("job", "read"),
                "create": _rule("job", "create", quota="backup-jobs-per-period", cost=1),
                "partial_update": _rule("job", "update"),
                "destroy": _rule("job", "delete"),
                "cancel": _rule("job", "cancel"),
                "retry": _rule("job", "retry", quota="backup-jobs-per-period", cost=1),
            }
        ),
        "schedules": MappingProxyType(
            {
                "list": _rule("schedule", "read"),
                "retrieve": _rule("schedule", "read"),
                "create": _rule("schedule", "create", quota="active-schedules", cost=1),
                "partial_update": _rule("schedule", "update"),
                "destroy": _rule("schedule", "delete"),
                "activate": _rule("schedule", "activate", quota="active-schedules", cost=1),
                "deactivate": _rule("schedule", "activate"),
                "run_now": _rule("schedule", "execute", quota="backup-jobs-per-period", cost=1),
            }
        ),
        "retention-policies": MappingProxyType(
            {
                "list": _rule("retention", "read"),
                "retrieve": _rule("retention", "read"),
                "create": _rule("retention", "create"),
                "partial_update": _rule("retention", "update"),
                "destroy": _rule("retention", "delete"),
                "activate": _rule("retention", "activate"),
                "deactivate": _rule("retention", "activate"),
                "preview": _rule("retention", "read"),
            }
        ),
        "storage-targets": MappingProxyType(
            {
                "list": _rule("storage_target", "read"),
                "retrieve": _rule("storage_target", "read"),
                "create": _rule("storage_target", "create"),
                "partial_update": _rule("storage_target", "update"),
                "destroy": _rule("storage_target", "delete"),
                "activate": _rule("storage_target", "update"),
                "deactivate": _rule("storage_target", "update"),
                "set_default": _rule("storage_target", "update"),
                "probe": _rule("storage_target", "probe", quota="provider-probes", cost=1),
            }
        ),
        "archives": MappingProxyType(
            {
                "list": _rule("archive", "read"),
                "retrieve": _rule("archive", "read"),
                "verify": _rule("archive", "verify", quota="integrity-verifications", cost=1),
            }
        ),
        "verifications": MappingProxyType(
            {
                "list": _rule("archive", "read"),
                "retrieve": _rule("archive", "read"),
                "cancel": _rule("archive", "verify"),
            }
        ),
        "health": MappingProxyType({"list": _rule("health", "read")}),
    }
)


def access_rule(resource: str, action: str) -> AccessRule | None:
    """Return action metadata; unknown actions intentionally return no rule."""

    return ACCESS_MAP.get(resource, {}).get(action)
