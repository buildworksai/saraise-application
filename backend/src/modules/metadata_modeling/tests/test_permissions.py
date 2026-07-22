"""Exhaustive deny-by-default access vocabulary tests."""

from src.modules.metadata_modeling.permissions import (
    CONFIG_ACTION_ACCESS,
    ENTITLEMENTS,
    ENTITY_ACTION_ACCESS,
    HEALTH_ACTION_ACCESS,
    PERMISSIONS,
    QUOTA_RESOURCES,
    RESOURCE_ACTION_ACCESS,
    SEQUENCE_ACTION_ACCESS,
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
