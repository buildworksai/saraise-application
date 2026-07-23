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
