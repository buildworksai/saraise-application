"""Fail-closed access declarations for metadata-modeling API actions."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping

PERMISSIONS: Final[tuple[str, ...]] = (
    "metadata_modeling.schema:read",
    "metadata_modeling.schema:create",
    "metadata_modeling.schema:update",
    "metadata_modeling.schema:publish",
    "metadata_modeling.schema:archive",
    "metadata_modeling.schema:import",
    "metadata_modeling.schema:export",
    "metadata_modeling.record:read",
    "metadata_modeling.record:create",
    "metadata_modeling.record:update",
    "metadata_modeling.record:delete",
    "metadata_modeling.record:submit",
    "metadata_modeling.record:cancel",
    "metadata_modeling.sequence:reset",
    "metadata_modeling.health:read",
)

ENTITLEMENTS: Final[tuple[str, ...]] = (
    "metadata_modeling.schemas",
    "metadata_modeling.records",
    "metadata_modeling.schema_versions",
    "metadata_modeling.import_export",
)

QUOTA_RESOURCES: Final[tuple[str, ...]] = (
    "metadata_modeling.schema_count",
    "metadata_modeling.fields_per_schema",
    "metadata_modeling.record_count",
    "metadata_modeling.api_reads",
    "metadata_modeling.api_writes",
)

# These commands require an explicit SoD decision.  In particular, publication
# policy compares the candidate's creator/updater with the publishing actor.
SOD_ACTIONS: Final[tuple[str, ...]] = (
    "metadata_modeling.schema:create",
    "metadata_modeling.schema:update",
    "metadata_modeling.schema:publish",
    "metadata_modeling.schema:import",
    "metadata_modeling.sequence:reset",
)


@dataclass(frozen=True, slots=True)
class AccessRequirement:
    """Complete governed access declaration for one DRF action."""

    permission: str
    entitlement: str
    quota_resource: str
    quota_cost: int = 1


def _requirements(
    actions: Mapping[str, tuple[str, str, str]],
) -> Mapping[str, AccessRequirement]:
    return MappingProxyType(
        {
            action: AccessRequirement(permission, entitlement, quota)
            for action, (permission, entitlement, quota) in actions.items()
        }
    )


ENTITY_ACTION_ACCESS: Final = _requirements(
    {
        "list": (PERMISSIONS[0], ENTITLEMENTS[0], QUOTA_RESOURCES[3]),
        "retrieve": (PERMISSIONS[0], ENTITLEMENTS[0], QUOTA_RESOURCES[3]),
        "create": (PERMISSIONS[1], ENTITLEMENTS[0], QUOTA_RESOURCES[0]),
        "update": (PERMISSIONS[2], ENTITLEMENTS[0], QUOTA_RESOURCES[4]),
        "partial_update": (PERMISSIONS[2], ENTITLEMENTS[0], QUOTA_RESOURCES[4]),
        "destroy": (PERMISSIONS[4], ENTITLEMENTS[0], QUOTA_RESOURCES[4]),
        "archive": (PERMISSIONS[4], ENTITLEMENTS[0], QUOTA_RESOURCES[4]),
        "restore": (PERMISSIONS[4], ENTITLEMENTS[0], QUOTA_RESOURCES[4]),
        "clone": (PERMISSIONS[1], ENTITLEMENTS[0], QUOTA_RESOURCES[0]),
        "preview": (PERMISSIONS[2], ENTITLEMENTS[0], QUOTA_RESOURCES[3]),
        "preview_new": (PERMISSIONS[2], ENTITLEMENTS[0], QUOTA_RESOURCES[3]),
        "export": (PERMISSIONS[6], ENTITLEMENTS[3], QUOTA_RESOURCES[3]),
        "import_schema": (PERMISSIONS[5], ENTITLEMENTS[3], QUOTA_RESOURCES[4]),
        "versions": (PERMISSIONS[0], ENTITLEMENTS[2], QUOTA_RESOURCES[3]),
        "create_version": (PERMISSIONS[2], ENTITLEMENTS[2], QUOTA_RESOURCES[4]),
        "version_detail": (PERMISSIONS[0], ENTITLEMENTS[2], QUOTA_RESOURCES[3]),
        "validate_version": (PERMISSIONS[2], ENTITLEMENTS[2], QUOTA_RESOURCES[3]),
        "publish_version": (PERMISSIONS[3], ENTITLEMENTS[2], QUOTA_RESOURCES[4]),
        "reject_version": (PERMISSIONS[3], ENTITLEMENTS[2], QUOTA_RESOURCES[4]),
        "rollback_version": (PERMISSIONS[3], ENTITLEMENTS[2], QUOTA_RESOURCES[4]),
        "diff_versions": (PERMISSIONS[0], ENTITLEMENTS[2], QUOTA_RESOURCES[3]),
    }
)

RESOURCE_ACTION_ACCESS: Final = _requirements(
    {
        "list": (PERMISSIONS[7], ENTITLEMENTS[1], QUOTA_RESOURCES[3]),
        "retrieve": (PERMISSIONS[7], ENTITLEMENTS[1], QUOTA_RESOURCES[3]),
        "create": (PERMISSIONS[8], ENTITLEMENTS[1], QUOTA_RESOURCES[2]),
        "update": (PERMISSIONS[9], ENTITLEMENTS[1], QUOTA_RESOURCES[4]),
        "partial_update": (PERMISSIONS[9], ENTITLEMENTS[1], QUOTA_RESOURCES[4]),
        "destroy": (PERMISSIONS[10], ENTITLEMENTS[1], QUOTA_RESOURCES[4]),
        "restore": (PERMISSIONS[10], ENTITLEMENTS[1], QUOTA_RESOURCES[4]),
        "duplicate": (PERMISSIONS[8], ENTITLEMENTS[1], QUOTA_RESOURCES[2]),
        "submit": (PERMISSIONS[11], ENTITLEMENTS[1], QUOTA_RESOURCES[4]),
        "cancel": (PERMISSIONS[12], ENTITLEMENTS[1], QUOTA_RESOURCES[4]),
        "versions": (PERMISSIONS[7], ENTITLEMENTS[1], QUOTA_RESOURCES[3]),
        "version_detail": (PERMISSIONS[7], ENTITLEMENTS[1], QUOTA_RESOURCES[3]),
    }
)

SEQUENCE_ACTION_ACCESS: Final = _requirements(
    {
        "list": (PERMISSIONS[0], ENTITLEMENTS[0], QUOTA_RESOURCES[3]),
        "retrieve": (PERMISSIONS[0], ENTITLEMENTS[0], QUOTA_RESOURCES[3]),
        "reset": (PERMISSIONS[13], ENTITLEMENTS[0], QUOTA_RESOURCES[4]),
        "preview": (PERMISSIONS[7], ENTITLEMENTS[1], QUOTA_RESOURCES[3]),
    }
)

HEALTH_ACTION_ACCESS: Final = _requirements({"health": (PERMISSIONS[14], ENTITLEMENTS[0], QUOTA_RESOURCES[3])})

CONFIG_ACTION_ACCESS: Final = _requirements(
    {
        "list": (PERMISSIONS[0], ENTITLEMENTS[0], QUOTA_RESOURCES[3]),
        "update": (PERMISSIONS[2], ENTITLEMENTS[0], QUOTA_RESOURCES[4]),
        "preview": (PERMISSIONS[2], ENTITLEMENTS[0], QUOTA_RESOURCES[3]),
        "versions": (PERMISSIONS[0], ENTITLEMENTS[2], QUOTA_RESOURCES[3]),
        "rollback": (PERMISSIONS[2], ENTITLEMENTS[2], QUOTA_RESOURCES[4]),
        "import_config": (PERMISSIONS[5], ENTITLEMENTS[3], QUOTA_RESOURCES[4]),
        "export_config": (PERMISSIONS[6], ENTITLEMENTS[3], QUOTA_RESOURCES[3]),
    }
)


def access_for_action(
    action: str | None,
    action_map: Mapping[str, AccessRequirement],
) -> AccessRequirement | None:
    """Return an explicit declaration; ``None`` intentionally means deny."""

    if action is None:
        return None
    return action_map.get(action)


__all__ = [
    "AccessRequirement",
    "CONFIG_ACTION_ACCESS",
    "ENTITLEMENTS",
    "ENTITY_ACTION_ACCESS",
    "HEALTH_ACTION_ACCESS",
    "PERMISSIONS",
    "QUOTA_RESOURCES",
    "RESOURCE_ACTION_ACCESS",
    "SEQUENCE_ACTION_ACCESS",
    "SOD_ACTIONS",
    "access_for_action",
]
