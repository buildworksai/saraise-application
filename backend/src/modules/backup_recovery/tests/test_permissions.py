"""Backup recovery access metadata contract tests.

Pins every (resource, action) -> AccessRule field exactly, and exercises
access_rule() lookup fail-closed semantics plus AccessRule/_rule defaults.
"""

from __future__ import annotations

import pytest

from src.modules.backup_recovery.permissions import ACCESS_MAP, AccessRule, access_rule

# Expected (permission, required_entitlement, quota_resource, quota_cost) for every
# declared (resource, action) pair. Hand-derived from the source's _rule() calls so
# any literal mutation (string, default, or cost) is caught by an exact mismatch.
EXPECTED: dict[str, dict[str, tuple[str, str, str, int]]] = {
    "jobs": {
        "list": ("backup_recovery.job:read", "backup-recovery", "backup-recovery.job", 1),
        "retrieve": ("backup_recovery.job:read", "backup-recovery", "backup-recovery.job", 1),
        "create": (
            "backup_recovery.job:create",
            "backup-recovery",
            "backup-jobs-per-period",
            1,
        ),
        "partial_update": (
            "backup_recovery.job:update",
            "backup-recovery",
            "backup-recovery.job",
            1,
        ),
        "destroy": ("backup_recovery.job:delete", "backup-recovery", "backup-recovery.job", 1),
        "cancel": ("backup_recovery.job:cancel", "backup-recovery", "backup-recovery.job", 1),
        "retry": (
            "backup_recovery.job:retry",
            "backup-recovery",
            "backup-jobs-per-period",
            1,
        ),
    },
    "schedules": {
        "list": ("backup_recovery.schedule:read", "backup-recovery", "backup-recovery.schedule", 1),
        "retrieve": (
            "backup_recovery.schedule:read",
            "backup-recovery",
            "backup-recovery.schedule",
            1,
        ),
        "create": (
            "backup_recovery.schedule:create",
            "backup-recovery",
            "active-schedules",
            1,
        ),
        "partial_update": (
            "backup_recovery.schedule:update",
            "backup-recovery",
            "backup-recovery.schedule",
            1,
        ),
        "destroy": (
            "backup_recovery.schedule:delete",
            "backup-recovery",
            "backup-recovery.schedule",
            1,
        ),
        "activate": (
            "backup_recovery.schedule:activate",
            "backup-recovery",
            "active-schedules",
            1,
        ),
        "deactivate": (
            "backup_recovery.schedule:activate",
            "backup-recovery",
            "backup-recovery.schedule",
            1,
        ),
        "run_now": (
            "backup_recovery.schedule:execute",
            "backup-recovery",
            "backup-jobs-per-period",
            1,
        ),
    },
    "retention-policies": {
        "list": (
            "backup_recovery.retention:read",
            "backup-recovery",
            "backup-recovery.retention",
            1,
        ),
        "retrieve": (
            "backup_recovery.retention:read",
            "backup-recovery",
            "backup-recovery.retention",
            1,
        ),
        "create": (
            "backup_recovery.retention:create",
            "backup-recovery",
            "backup-recovery.retention",
            1,
        ),
        "partial_update": (
            "backup_recovery.retention:update",
            "backup-recovery",
            "backup-recovery.retention",
            1,
        ),
        "destroy": (
            "backup_recovery.retention:delete",
            "backup-recovery",
            "backup-recovery.retention",
            1,
        ),
        "activate": (
            "backup_recovery.retention:activate",
            "backup-recovery",
            "backup-recovery.retention",
            1,
        ),
        "deactivate": (
            "backup_recovery.retention:activate",
            "backup-recovery",
            "backup-recovery.retention",
            1,
        ),
        "preview": (
            "backup_recovery.retention:read",
            "backup-recovery",
            "backup-recovery.retention",
            1,
        ),
    },
    "storage-targets": {
        "list": (
            "backup_recovery.storage_target:read",
            "backup-recovery",
            "backup-recovery.storage_target",
            1,
        ),
        "retrieve": (
            "backup_recovery.storage_target:read",
            "backup-recovery",
            "backup-recovery.storage_target",
            1,
        ),
        "create": (
            "backup_recovery.storage_target:create",
            "backup-recovery",
            "backup-recovery.storage_target",
            1,
        ),
        "partial_update": (
            "backup_recovery.storage_target:update",
            "backup-recovery",
            "backup-recovery.storage_target",
            1,
        ),
        "destroy": (
            "backup_recovery.storage_target:delete",
            "backup-recovery",
            "backup-recovery.storage_target",
            1,
        ),
        "activate": (
            "backup_recovery.storage_target:update",
            "backup-recovery",
            "backup-recovery.storage_target",
            1,
        ),
        "deactivate": (
            "backup_recovery.storage_target:update",
            "backup-recovery",
            "backup-recovery.storage_target",
            1,
        ),
        "set_default": (
            "backup_recovery.storage_target:update",
            "backup-recovery",
            "backup-recovery.storage_target",
            1,
        ),
        "probe": (
            "backup_recovery.storage_target:probe",
            "backup-recovery",
            "provider-probes",
            1,
        ),
    },
    "archives": {
        "list": ("backup_recovery.archive:read", "backup-recovery", "backup-recovery.archive", 1),
        "retrieve": (
            "backup_recovery.archive:read",
            "backup-recovery",
            "backup-recovery.archive",
            1,
        ),
        "verify": (
            "backup_recovery.archive:verify",
            "backup-recovery",
            "integrity-verifications",
            1,
        ),
    },
    "verifications": {
        "list": ("backup_recovery.archive:read", "backup-recovery", "backup-recovery.archive", 1),
        "retrieve": (
            "backup_recovery.archive:read",
            "backup-recovery",
            "backup-recovery.archive",
            1,
        ),
        "cancel": (
            "backup_recovery.archive:verify",
            "backup-recovery",
            "backup-recovery.archive",
            1,
        ),
    },
    "health": {
        "list": ("backup_recovery.health:read", "backup-recovery", "backup-recovery.health", 1),
    },
}


def test_access_map_resource_keys_match_expected() -> None:
    assert set(ACCESS_MAP.keys()) == set(EXPECTED.keys())


@pytest.mark.parametrize(
    ("resource", "action"),
    [(resource, action) for resource, actions in EXPECTED.items() for action in actions],
)
def test_access_map_rule_fields_pinned(resource: str, action: str) -> None:
    rule = ACCESS_MAP[resource][action]
    permission, entitlement, quota_resource, quota_cost = EXPECTED[resource][action]

    assert rule.permission == permission
    assert rule.required_entitlement == entitlement
    assert rule.quota_resource == quota_resource
    assert rule.quota_cost == quota_cost


@pytest.mark.parametrize("resource", list(EXPECTED.keys()))
def test_access_map_action_keys_match_expected(resource: str) -> None:
    assert set(ACCESS_MAP[resource].keys()) == set(EXPECTED[resource].keys())


def test_access_rules_have_positive_quota_costs() -> None:
    for action_map in ACCESS_MAP.values():
        for rule in action_map.values():
            assert rule.quota_cost >= 1


def test_access_map_total_rule_count() -> None:
    total = sum(len(actions) for actions in ACCESS_MAP.values())
    expected_total = sum(len(actions) for actions in EXPECTED.values())
    assert total == expected_total == 39


def test_access_rule_returns_known_rule() -> None:
    rule = access_rule("jobs", "create")
    assert rule is not None
    assert rule.permission == "backup_recovery.job:create"
    assert rule.quota_resource == "backup-jobs-per-period"
    assert rule.quota_cost == 1


def test_access_rule_unknown_resource_returns_none() -> None:
    assert access_rule("not-a-resource", "list") is None


def test_access_rule_known_resource_unknown_action_returns_none() -> None:
    assert access_rule("jobs", "not-an-action") is None


def test_access_rule_unknown_resource_and_action_returns_none() -> None:
    assert access_rule("nope", "nope") is None


def test_access_rule_empty_strings_return_none() -> None:
    assert access_rule("", "") is None


def test_access_map_is_read_only_mapping_proxy() -> None:
    with pytest.raises(TypeError):
        ACCESS_MAP["jobs"] = {}  # type: ignore[index]


def test_access_map_nested_resource_is_read_only_mapping_proxy() -> None:
    with pytest.raises(TypeError):
        ACCESS_MAP["jobs"]["list"] = None  # type: ignore[index]


def test_access_rule_dataclass_defaults() -> None:
    rule = AccessRule(permission="custom.permission:read")
    assert rule.permission == "custom.permission:read"
    assert rule.required_entitlement == "backup-recovery"
    assert rule.quota_resource == "backup-recovery.read"
    assert rule.quota_cost == 1


def test_access_rule_dataclass_explicit_overrides() -> None:
    rule = AccessRule(
        permission="custom.permission:write",
        required_entitlement="custom-ent",
        quota_resource="custom-quota",
        quota_cost=5,
    )
    assert rule.permission == "custom.permission:write"
    assert rule.required_entitlement == "custom-ent"
    assert rule.quota_resource == "custom-quota"
    assert rule.quota_cost == 5


def test_access_rule_dataclass_is_frozen() -> None:
    rule = AccessRule(permission="x")
    with pytest.raises(AttributeError):
        rule.permission = "y"  # type: ignore[misc]


def test_access_rule_dataclass_equality_by_value() -> None:
    a = AccessRule(permission="x", quota_cost=2)
    b = AccessRule(permission="x", quota_cost=2)
    c = AccessRule(permission="x", quota_cost=3)
    assert a == b
    assert a != c
