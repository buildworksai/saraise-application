"""Fail-closed permission declaration tests for every MDM API capability."""

from __future__ import annotations

import pytest

from src.modules.master_data_management import permissions


def test_permission_catalog_exactly_matches_public_contract() -> None:
    assert set(permissions.PERMISSIONS) == {
        "mdm.entity_type:read",
        "mdm.entity_type:manage",
        "mdm.entity:read",
        "mdm.entity:create",
        "mdm.entity:update",
        "mdm.entity:archive",
        "mdm.entity:restore",
        "mdm.entity:rollback",
        "mdm.quality_rule:read",
        "mdm.quality_rule:manage",
        "mdm.quality_issue:read",
        "mdm.quality_issue:resolve",
        "mdm.quality:scan",
        "mdm.matching_rule:read",
        "mdm.matching_rule:manage",
        "mdm.match:read",
        "mdm.match:review",
        "mdm.match:run",
        "mdm.merge:read",
        "mdm.merge:execute",
        "mdm.merge:reverse",
        "mdm.dashboard:read",
        "mdm.configuration:read",
        "mdm.configuration:manage",
    }
    assert len(permissions.PERMISSIONS) == len(set(permissions.PERMISSIONS))


def test_unknown_permissions_fail_closed() -> None:
    with pytest.raises(ValueError, match="unknown MDM permission"):
        permissions.access("mdm.entity:hard_delete")


def test_standard_operations_do_not_consume_quota() -> None:
    rules = [
        value
        for name, value in vars(permissions).items()
        if name.isupper() and isinstance(value, permissions.AccessRule)
    ]
    ordinary = [rule for rule in rules if rule not in {permissions.MATCH_RUN, permissions.QUALITY_SCAN}]
    assert ordinary
    assert all(rule.quota_resource is None for rule in ordinary)
    assert all(rule.entitlement == permissions.ENTITLEMENT for rule in rules)


def test_only_bounded_batch_scans_consume_explicit_quota() -> None:
    assert permissions.MATCH_RUN.permission == "mdm.match:run"
    assert permissions.MATCH_RUN.quota_resource == "mdm.match.scan"
    assert permissions.MATCH_RUN.quota_cost == 1
    assert permissions.QUALITY_SCAN.permission == "mdm.quality:scan"
    assert permissions.QUALITY_SCAN.quota_resource == "mdm.quality.scan"
    assert permissions.QUALITY_SCAN.quota_cost == 1


def test_access_rule_is_immutable() -> None:
    with pytest.raises((AttributeError, TypeError)):
        permissions.ENTITY_READ.permission = "mdm.entity:update"  # type: ignore[misc]


def test_access_rule_has_no_dynamic_attributes() -> None:
    # slots=True must actually remove __dict__; otherwise arbitrary
    # attributes could be attached to a rule and immutability would be
    # only partial.
    with pytest.raises((AttributeError, TypeError)):
        permissions.ENTITY_READ.extra = "nope"  # type: ignore[attr-defined]


def test_access_rule_equality_is_value_based() -> None:
    # frozen dataclasses generate __eq__ from field values; confirm two
    # independently constructed rules with identical fields compare equal
    # and that a differing field breaks equality.
    assert permissions.AccessRule("mdm.entity:read") == permissions.ENTITY_READ
    assert permissions.AccessRule("mdm.entity:update") != permissions.ENTITY_READ
    assert permissions.AccessRule("mdm.entity:read", quota_cost=2) != permissions.ENTITY_READ


@pytest.mark.parametrize(
    ("name", "permission", "quota_resource", "quota_cost"),
    [
        ("ENTITY_TYPE_READ", "mdm.entity_type:read", None, 1),
        ("ENTITY_TYPE_MANAGE", "mdm.entity_type:manage", None, 1),
        ("ENTITY_READ", "mdm.entity:read", None, 1),
        ("ENTITY_CREATE", "mdm.entity:create", None, 1),
        ("ENTITY_UPDATE", "mdm.entity:update", None, 1),
        ("ENTITY_ARCHIVE", "mdm.entity:archive", None, 1),
        ("ENTITY_RESTORE", "mdm.entity:restore", None, 1),
        ("ENTITY_ROLLBACK", "mdm.entity:rollback", None, 1),
        ("QUALITY_RULE_READ", "mdm.quality_rule:read", None, 1),
        ("QUALITY_RULE_MANAGE", "mdm.quality_rule:manage", None, 1),
        ("QUALITY_ISSUE_READ", "mdm.quality_issue:read", None, 1),
        ("QUALITY_ISSUE_RESOLVE", "mdm.quality_issue:resolve", None, 1),
        ("MATCHING_RULE_READ", "mdm.matching_rule:read", None, 1),
        ("MATCHING_RULE_MANAGE", "mdm.matching_rule:manage", None, 1),
        ("MATCH_READ", "mdm.match:read", None, 1),
        ("MATCH_REVIEW", "mdm.match:review", None, 1),
        ("MATCH_RUN", "mdm.match:run", "mdm.match.scan", 1),
        ("QUALITY_SCAN", "mdm.quality:scan", "mdm.quality.scan", 1),
        ("MERGE_READ", "mdm.merge:read", None, 1),
        ("MERGE_EXECUTE", "mdm.merge:execute", None, 1),
        ("MERGE_REVERSE", "mdm.merge:reverse", None, 1),
        ("DASHBOARD_READ", "mdm.dashboard:read", None, 1),
        ("CONFIGURATION_READ", "mdm.configuration:read", None, 1),
        ("CONFIGURATION_MANAGE", "mdm.configuration:manage", None, 1),
    ],
)
def test_each_named_rule_is_pinned_to_its_exact_declaration(
    name: str, permission: str, quota_resource: str | None, quota_cost: int
) -> None:
    rule = getattr(permissions, name)
    assert rule.permission == permission
    assert rule.quota_resource == quota_resource
    assert rule.quota_cost == quota_cost
    assert rule.entitlement == permissions.ENTITLEMENT


def test_named_rule_constants_cover_every_declared_permission_exactly_once() -> None:
    # Guards against a rule silently duplicating another permission or a
    # permission having no named constant pointing at it.
    rules = [
        value
        for name, value in vars(permissions).items()
        if name.isupper() and isinstance(value, permissions.AccessRule)
    ]
    assert sorted(rule.permission for rule in rules) == sorted(permissions.PERMISSIONS)


def test_entitlement_constant_value() -> None:
    assert permissions.ENTITLEMENT == "master_data_management"


def test_access_rejects_permission_not_in_catalog_with_the_offending_value_in_message() -> None:
    with pytest.raises(ValueError, match=r"unknown MDM permission: mdm\.entity:hard_delete"):
        permissions.access("mdm.entity:hard_delete")


def test_access_default_quota_resource_and_cost() -> None:
    rule = permissions.access("mdm.entity:read")
    assert rule.quota_resource is None
    assert rule.quota_cost == 1
    assert rule.permission == "mdm.entity:read"


def test_access_honors_explicit_quota_resource_and_cost() -> None:
    rule = permissions.access("mdm.entity:read", quota_resource="custom.resource", quota_cost=5)
    assert rule.quota_resource == "custom.resource"
    assert rule.quota_cost == 5


def test_module_all_exports_exactly_the_public_contract() -> None:
    assert permissions.__all__ == ["AccessRule", "ENTITLEMENT", "PERMISSIONS"]
