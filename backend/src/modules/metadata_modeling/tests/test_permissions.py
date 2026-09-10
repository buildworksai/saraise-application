"""Exhaustive deny-by-default access vocabulary tests."""

import dataclasses

import pytest

from src.modules.metadata_modeling import permissions as permissions_module
from src.modules.metadata_modeling.permissions import (
    CONFIG_ACTION_ACCESS,
    ENTITLEMENTS,
    ENTITY_ACTION_ACCESS,
    HEALTH_ACTION_ACCESS,
    PERMISSIONS,
    QUOTA_RESOURCES,
    RESOURCE_ACTION_ACCESS,
    SEQUENCE_ACTION_ACCESS,
    SOD_ACTIONS,
    AccessRequirement,
    access_for_action,
)


def test_permission_vocabulary_is_exact_and_unique():
    assert len(PERMISSIONS) == len(set(PERMISSIONS)) == 15
    assert PERMISSIONS[0] == "metadata_modeling.schema:read"
    assert PERMISSIONS[-1] == "metadata_modeling.health:read"
    assert set(ENTITLEMENTS) == {
        "metadata_modeling.schemas",
        "metadata_modeling.records",
        "metadata_modeling.schema_versions",
        "metadata_modeling.import_export",
    }
    assert len(set(QUOTA_RESOURCES)) == 5


def test_every_mapped_action_has_complete_governance_and_unknown_actions_deny():
    maps = (
        ENTITY_ACTION_ACCESS,
        RESOURCE_ACTION_ACCESS,
        SEQUENCE_ACTION_ACCESS,
        CONFIG_ACTION_ACCESS,
        HEALTH_ACTION_ACCESS,
    )
    for action_map in maps:
        assert access_for_action("unmapped", action_map) is None
        assert access_for_action(None, action_map) is None
        for requirement in action_map.values():
            assert requirement.permission in PERMISSIONS
            assert requirement.entitlement in ENTITLEMENTS
            assert requirement.quota_resource in QUOTA_RESOURCES
            assert requirement.quota_cost > 0


def test_sensitive_actions_never_share_a_weaker_permission():
    assert ENTITY_ACTION_ACCESS["publish_version"].permission.endswith("schema:publish")
    assert ENTITY_ACTION_ACCESS["import_schema"].permission.endswith("schema:import")
    assert RESOURCE_ACTION_ACCESS["submit"].permission.endswith("record:submit")
    assert RESOURCE_ACTION_ACCESS["cancel"].permission.endswith("record:cancel")
    assert SEQUENCE_ACTION_ACCESS["reset"].permission.endswith("sequence:reset")


def test_permissions_tuple_is_pinned_exactly_in_order():
    assert PERMISSIONS == (
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


def test_entitlements_tuple_is_pinned_exactly_in_order():
    assert ENTITLEMENTS == (
        "metadata_modeling.schemas",
        "metadata_modeling.records",
        "metadata_modeling.schema_versions",
        "metadata_modeling.import_export",
    )


def test_quota_resources_tuple_is_pinned_exactly_in_order():
    assert QUOTA_RESOURCES == (
        "metadata_modeling.schema_count",
        "metadata_modeling.fields_per_schema",
        "metadata_modeling.record_count",
        "metadata_modeling.api_reads",
        "metadata_modeling.api_writes",
    )


def test_sod_actions_tuple_is_pinned_exactly_in_order():
    assert SOD_ACTIONS == (
        "metadata_modeling.schema:create",
        "metadata_modeling.schema:update",
        "metadata_modeling.schema:publish",
        "metadata_modeling.schema:import",
        "metadata_modeling.sequence:reset",
    )
    assert len(SOD_ACTIONS) == len(set(SOD_ACTIONS)) == 5


def _req(permission, entitlement, quota_resource, quota_cost=1):
    return AccessRequirement(
        permission=permission,
        entitlement=entitlement,
        quota_resource=quota_resource,
        quota_cost=quota_cost,
    )


def test_entity_action_access_is_pinned_exactly():
    expected = {
        "list": _req("metadata_modeling.schema:read", "metadata_modeling.schemas", "metadata_modeling.api_reads"),
        "retrieve": _req("metadata_modeling.schema:read", "metadata_modeling.schemas", "metadata_modeling.api_reads"),
        "create": _req(
            "metadata_modeling.schema:create", "metadata_modeling.schemas", "metadata_modeling.schema_count"
        ),
        "update": _req("metadata_modeling.schema:update", "metadata_modeling.schemas", "metadata_modeling.api_writes"),
        "partial_update": _req(
            "metadata_modeling.schema:update", "metadata_modeling.schemas", "metadata_modeling.api_writes"
        ),
        "destroy": _req(
            "metadata_modeling.schema:archive", "metadata_modeling.schemas", "metadata_modeling.api_writes"
        ),
        "archive": _req(
            "metadata_modeling.schema:archive", "metadata_modeling.schemas", "metadata_modeling.api_writes"
        ),
        "restore": _req(
            "metadata_modeling.schema:archive", "metadata_modeling.schemas", "metadata_modeling.api_writes"
        ),
        "clone": _req("metadata_modeling.schema:create", "metadata_modeling.schemas", "metadata_modeling.schema_count"),
        "preview": _req("metadata_modeling.schema:update", "metadata_modeling.schemas", "metadata_modeling.api_reads"),
        "preview_new": _req(
            "metadata_modeling.schema:update", "metadata_modeling.schemas", "metadata_modeling.api_reads"
        ),
        "export": _req(
            "metadata_modeling.schema:export", "metadata_modeling.import_export", "metadata_modeling.api_reads"
        ),
        "import_schema": _req(
            "metadata_modeling.schema:import", "metadata_modeling.import_export", "metadata_modeling.api_writes"
        ),
        "versions": _req(
            "metadata_modeling.schema:read", "metadata_modeling.schema_versions", "metadata_modeling.api_reads"
        ),
        "create_version": _req(
            "metadata_modeling.schema:update", "metadata_modeling.schema_versions", "metadata_modeling.api_writes"
        ),
        "version_detail": _req(
            "metadata_modeling.schema:read", "metadata_modeling.schema_versions", "metadata_modeling.api_reads"
        ),
        "validate_version": _req(
            "metadata_modeling.schema:update", "metadata_modeling.schema_versions", "metadata_modeling.api_reads"
        ),
        "publish_version": _req(
            "metadata_modeling.schema:publish", "metadata_modeling.schema_versions", "metadata_modeling.api_writes"
        ),
        "reject_version": _req(
            "metadata_modeling.schema:publish", "metadata_modeling.schema_versions", "metadata_modeling.api_writes"
        ),
        "rollback_version": _req(
            "metadata_modeling.schema:publish", "metadata_modeling.schema_versions", "metadata_modeling.api_writes"
        ),
        "diff_versions": _req(
            "metadata_modeling.schema:read", "metadata_modeling.schema_versions", "metadata_modeling.api_reads"
        ),
    }
    assert dict(ENTITY_ACTION_ACCESS) == expected
    assert set(ENTITY_ACTION_ACCESS.keys()) == set(expected.keys())


def test_resource_action_access_is_pinned_exactly():
    expected = {
        "list": _req("metadata_modeling.record:read", "metadata_modeling.records", "metadata_modeling.api_reads"),
        "retrieve": _req("metadata_modeling.record:read", "metadata_modeling.records", "metadata_modeling.api_reads"),
        "create": _req(
            "metadata_modeling.record:create", "metadata_modeling.records", "metadata_modeling.record_count"
        ),
        "update": _req("metadata_modeling.record:update", "metadata_modeling.records", "metadata_modeling.api_writes"),
        "partial_update": _req(
            "metadata_modeling.record:update", "metadata_modeling.records", "metadata_modeling.api_writes"
        ),
        "destroy": _req("metadata_modeling.record:delete", "metadata_modeling.records", "metadata_modeling.api_writes"),
        "restore": _req("metadata_modeling.record:delete", "metadata_modeling.records", "metadata_modeling.api_writes"),
        "duplicate": _req(
            "metadata_modeling.record:create", "metadata_modeling.records", "metadata_modeling.record_count"
        ),
        "submit": _req("metadata_modeling.record:submit", "metadata_modeling.records", "metadata_modeling.api_writes"),
        "cancel": _req("metadata_modeling.record:cancel", "metadata_modeling.records", "metadata_modeling.api_writes"),
        "versions": _req("metadata_modeling.record:read", "metadata_modeling.records", "metadata_modeling.api_reads"),
        "version_detail": _req(
            "metadata_modeling.record:read", "metadata_modeling.records", "metadata_modeling.api_reads"
        ),
    }
    assert dict(RESOURCE_ACTION_ACCESS) == expected
    assert set(RESOURCE_ACTION_ACCESS.keys()) == set(expected.keys())


def test_sequence_action_access_is_pinned_exactly():
    expected = {
        "list": _req("metadata_modeling.schema:read", "metadata_modeling.schemas", "metadata_modeling.api_reads"),
        "retrieve": _req("metadata_modeling.schema:read", "metadata_modeling.schemas", "metadata_modeling.api_reads"),
        "reset": _req("metadata_modeling.sequence:reset", "metadata_modeling.schemas", "metadata_modeling.api_writes"),
        "preview": _req("metadata_modeling.record:read", "metadata_modeling.records", "metadata_modeling.api_reads"),
    }
    assert dict(SEQUENCE_ACTION_ACCESS) == expected
    assert set(SEQUENCE_ACTION_ACCESS.keys()) == set(expected.keys())


def test_health_action_access_is_pinned_exactly():
    expected = {
        "health": _req("metadata_modeling.health:read", "metadata_modeling.schemas", "metadata_modeling.api_reads"),
    }
    assert dict(HEALTH_ACTION_ACCESS) == expected
    assert set(HEALTH_ACTION_ACCESS.keys()) == {"health"}


def test_config_action_access_is_pinned_exactly():
    expected = {
        "list": _req("metadata_modeling.schema:read", "metadata_modeling.schemas", "metadata_modeling.api_reads"),
        "update": _req("metadata_modeling.schema:update", "metadata_modeling.schemas", "metadata_modeling.api_writes"),
        "preview": _req("metadata_modeling.schema:update", "metadata_modeling.schemas", "metadata_modeling.api_reads"),
        "versions": _req(
            "metadata_modeling.schema:read", "metadata_modeling.schema_versions", "metadata_modeling.api_reads"
        ),
        "rollback": _req(
            "metadata_modeling.schema:update", "metadata_modeling.schema_versions", "metadata_modeling.api_writes"
        ),
        "import_config": _req(
            "metadata_modeling.schema:import", "metadata_modeling.import_export", "metadata_modeling.api_writes"
        ),
        "export_config": _req(
            "metadata_modeling.schema:export", "metadata_modeling.import_export", "metadata_modeling.api_reads"
        ),
    }
    assert dict(CONFIG_ACTION_ACCESS) == expected
    assert set(CONFIG_ACTION_ACCESS.keys()) == set(expected.keys())


def test_access_requirement_defaults_and_immutability():
    req = AccessRequirement(
        permission="metadata_modeling.schema:read",
        entitlement="metadata_modeling.schemas",
        quota_resource="metadata_modeling.api_reads",
    )
    assert req.quota_cost == 1
    assert dataclasses.is_dataclass(req)
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.quota_cost = 2
    # slots=True means no __dict__ is created for instances.
    assert not hasattr(req, "__dict__")


def test_access_for_action_returns_none_for_none_action_before_lookup():
    # Passing None must short-circuit and never touch the mapping.
    assert access_for_action(None, ENTITY_ACTION_ACCESS) is None
    assert access_for_action(None, {}) is None


def test_access_for_action_returns_none_for_unmapped_action_on_every_map():
    for action_map in (
        ENTITY_ACTION_ACCESS,
        RESOURCE_ACTION_ACCESS,
        SEQUENCE_ACTION_ACCESS,
        CONFIG_ACTION_ACCESS,
        HEALTH_ACTION_ACCESS,
    ):
        assert access_for_action("definitely-not-a-real-action", action_map) is None


def test_access_for_action_returns_the_exact_mapped_requirement_object():
    requirement = access_for_action("list", ENTITY_ACTION_ACCESS)
    assert requirement is ENTITY_ACTION_ACCESS["list"]
    assert requirement == AccessRequirement(
        permission="metadata_modeling.schema:read",
        entitlement="metadata_modeling.schemas",
        quota_resource="metadata_modeling.api_reads",
        quota_cost=1,
    )


def test_requirements_helper_produces_immutable_mapping():
    built = permissions_module._requirements(
        {"only": ("perm", "ent", "quota")},
    )
    assert isinstance(built, permissions_module.MappingProxyType)
    assert built["only"] == AccessRequirement(permission="perm", entitlement="ent", quota_resource="quota")
    with pytest.raises(TypeError):
        built["only"] = AccessRequirement(permission="x", entitlement="y", quota_resource="z")


def test_dunder_all_matches_public_surface_exactly():
    assert permissions_module.__all__ == [
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
