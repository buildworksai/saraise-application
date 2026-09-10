"""Fail-closed action metadata and access-pipeline integration tests."""

from __future__ import annotations

import dataclasses
from types import MappingProxyType, SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.exceptions import ImproperlyConfigured
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.modules.customization_framework import permissions as permissions_module
from src.modules.customization_framework.permissions import (
    ACTION_ACCESS,
    PERMISSIONS,
    AccessRequirement,
    _load_access_policy,
    requirement_for,
)


def _manifest(permissions, access_policy, sod_pairs=None, sod_actions=None):
    """Build a minimal well-formed manifest fragment for `_load_access_policy`."""

    pairs = sod_pairs or []
    flattened = [action for pair in pairs for action in pair]
    return {
        "permissions": list(permissions),
        "sod_actions": flattened if sod_actions is None else sod_actions,
        "metadata": {
            "access_policy": access_policy,
            "sod_pairs": [{"actions": list(pair)} for pair in pairs],
        },
    }


def test_action_access_is_immutable_complete_and_namespaced() -> None:
    assert isinstance(ACTION_ACCESS, MappingProxyType)
    assert ACTION_ACCESS
    assert len(PERMISSIONS) == len(set(PERMISSIONS))
    assert all(
        requirement.permission.startswith("customization_framework.")
        and requirement.entitlement.startswith("customization_framework.")
        and requirement.quota_resource.startswith("customization_framework.")
        and requirement.quota_cost > 0
        for requirement in ACTION_ACCESS.values()
    )


def test_every_required_permission_family_is_declared() -> None:
    expected = {
        "field_definition:read",
        "field_definition:create",
        "field_definition:update",
        "field_definition:delete",
        "field_definition:publish",
        "field_definition:rollback",
        "field_value:read",
        "field_value:write",
        "field_value:delete",
        "field_value:validate",
        "form:read",
        "form:create",
        "form:update",
        "form:delete",
        "form:publish",
        "form:archive",
        "rule:read",
        "rule:create",
        "rule:update",
        "rule:delete",
        "rule:publish",
        "rule:evaluate",
        "execution:read",
        "impact:read",
        "health:read",
        "configuration:read",
        "configuration:update",
        "configuration:rollback",
        "configuration:import",
        "configuration:export",
    }
    assert {permission.removeprefix("customization_framework.") for permission in PERMISSIONS} == expected


def test_method_qualified_actions_resolve_distinct_read_and_write_access() -> None:
    read = requirement_for("form", "layout_versions", "GET")
    write = requirement_for("form", "layout_versions", "POST")
    assert isinstance(read, AccessRequirement)
    assert isinstance(write, AccessRequirement)
    assert read.permission == "customization_framework.form:read"
    assert write.permission == "customization_framework.form:update"


def test_missing_action_mapping_denies_by_returning_none() -> None:
    assert requirement_for("field-definition", "put") is None
    assert requirement_for("unknown", "list") is None


def test_rule_evaluation_has_dedicated_quota_resource_and_positive_cost() -> None:
    requirement = requirement_for("rule", "evaluate")
    assert requirement is not None
    assert requirement.permission == "customization_framework.rule:evaluate"
    assert requirement.quota_resource.endswith("rule_evaluations")
    assert requirement.quota_cost >= 1


def test_requires_access_receives_complete_action_declaration() -> None:
    pipeline = Mock()
    pipeline.decide.return_value = SimpleNamespace(allowed=True)
    permission = RequiresAccess(pipeline=pipeline)
    request = SimpleNamespace(
        tenant_id="00000000-0000-0000-0000-000000000001",
        user=SimpleNamespace(is_authenticated=True),
    )
    requirement = ACTION_ACCESS["field-definition.list"]
    view = SimpleNamespace(
        required_permission=requirement.permission,
        required_entitlement=requirement.entitlement,
        quota_resource=requirement.quota_resource,
        quota_cost=requirement.quota_cost,
    )
    assert permission.has_permission(request, view) is True
    pipeline.decide.assert_called_once()


def test_governed_viewsets_compose_authentication_and_access_permissions() -> None:
    from src.modules.customization_framework.api import GovernedTenantViewSet

    assert tuple(GovernedTenantViewSet.permission_classes) == (
        IsAuthenticated,
        RequiresAccess,
    )


def test_access_requirement_is_frozen() -> None:
    requirement = AccessRequirement("p", "e", "q", 1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        requirement.permission = "changed"


def test_access_requirement_has_no_instance_dict_due_to_slots() -> None:
    requirement = AccessRequirement("p", "e", "q", 1)
    assert not hasattr(requirement, "__dict__")


def test_quota_resource_that_is_a_non_string_truthy_value_is_rejected() -> None:
    manifest = _manifest(
        ["p1"],
        {"a": {"permission": "p1", "entitlement": "e1", "quota_resource": 5, "quota_cost": 1}},
    )
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_quota_cost_of_zero_is_rejected() -> None:
    manifest = _manifest(
        ["p1"],
        {"a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 0}},
    )
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_quota_cost_of_exactly_one_is_the_minimum_accepted_value() -> None:
    manifest = _manifest(
        ["p1"],
        {"a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1}},
    )
    policy, permissions, pairs = _load_access_policy(manifest)
    assert policy["a"].quota_cost == 1
    assert permissions == ("p1",)
    assert pairs == ()


def test_access_requirement_quota_cost_defaults_to_one() -> None:
    assert AccessRequirement("p", "e", "q").quota_cost == 1


def test_permissions_list_containing_a_non_string_item_is_rejected() -> None:
    manifest = _manifest(
        ["p1", 5],
        {"a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1}},
    )
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_permissions_field_must_be_a_list_not_merely_list_like() -> None:
    """A tuple behaves identically to a list for every downstream operation in
    this function, so only the explicit `isinstance(..., list)` guard rejects
    it — the test must not rely on any other check to raise instead."""

    manifest = {
        "permissions": ("p1",),
        "sod_actions": [],
        "metadata": {
            "access_policy": {"a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1}},
            "sod_pairs": [],
        },
    }
    with pytest.raises(ImproperlyConfigured, match=r"must be a list of strings"):
        _load_access_policy(manifest)


def test_empty_access_policy_is_rejected_even_when_permissions_list_is_empty() -> None:
    manifest = {
        "permissions": [],
        "sod_actions": [],
        "metadata": {"access_policy": {}, "sod_pairs": []},
    }
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_sod_pair_actions_with_wrong_length_is_rejected() -> None:
    manifest = _manifest(
        ["p1", "p2"],
        {
            "a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1},
            "b": {"permission": "p2", "entitlement": "e2", "quota_resource": "q2", "quota_cost": 1},
        },
    )
    manifest["metadata"]["sod_pairs"] = [{"actions": ["p1"]}]
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_duplicate_sod_pairs_are_rejected() -> None:
    manifest = _manifest(
        ["p1", "p2"],
        {
            "a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1},
            "b": {"permission": "p2", "entitlement": "e2", "quota_resource": "q2", "quota_cost": 1},
        },
        sod_pairs=[("p1", "p2"), ("p1", "p2")],
    )
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_access_policy_entry_declaration_must_be_a_mapping() -> None:
    manifest = _manifest(["p1"], {"a": "not-a-mapping-declaration"})
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_sod_actions_must_exactly_match_flattened_sod_pairs() -> None:
    manifest = _manifest(
        ["p1", "p2"],
        {
            "a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1},
            "b": {"permission": "p2", "entitlement": "e2", "quota_resource": "q2", "quota_cost": 1},
        },
        sod_pairs=[("p1", "p2")],
    )
    manifest["sod_actions"] = ["p2", "p1"]
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_load_manifest_wraps_os_error(monkeypatch, tmp_path) -> None:
    missing = tmp_path / "missing.yaml"
    monkeypatch.setattr(permissions_module, "Path", lambda *_: SimpleNamespace(with_name=lambda name: missing))
    with pytest.raises(ImproperlyConfigured):
        permissions_module._load_manifest()


def test_load_manifest_wraps_yaml_error(monkeypatch, tmp_path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("{ invalid: [", encoding="utf-8")
    monkeypatch.setattr(permissions_module, "Path", lambda *_: SimpleNamespace(with_name=lambda name: bad))
    with pytest.raises(ImproperlyConfigured):
        permissions_module._load_manifest()


def test_permissions_list_with_duplicate_entries_is_rejected() -> None:
    manifest = _manifest(
        ["p1", "p1"],
        {"a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1}},
    )
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_access_policy_action_key_must_not_be_empty() -> None:
    manifest = _manifest(
        ["p1"],
        {"": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1}},
    )
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_action_permission_not_in_manifest_permissions_is_rejected() -> None:
    """Match the exact message: an undeclared permission also fails the later
    'every permission must be used' check, so a bare `pytest.raises` would
    pass even if this specific per-entry validation were disabled."""

    manifest = _manifest(
        ["p1"],
        {"a": {"permission": "not-declared", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1}},
    )
    with pytest.raises(ImproperlyConfigured, match=r"entry 'a' is invalid"):
        _load_access_policy(manifest)


def test_entitlement_must_be_a_string() -> None:
    manifest = _manifest(
        ["p1"],
        {"a": {"permission": "p1", "entitlement": 5, "quota_resource": "q1", "quota_cost": 1}},
    )
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_entitlement_must_not_be_empty() -> None:
    manifest = _manifest(
        ["p1"],
        {"a": {"permission": "p1", "entitlement": "", "quota_resource": "q1", "quota_cost": 1}},
    )
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_quota_cost_must_be_an_integer() -> None:
    manifest = _manifest(
        ["p1"],
        {"a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1.5}},
    )
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_quota_cost_must_not_be_a_boolean() -> None:
    manifest = _manifest(
        ["p1"],
        {"a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": True}},
    )
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_quota_cost_of_two_is_accepted() -> None:
    manifest = _manifest(
        ["p1"],
        {"a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 2}},
    )
    policy, _permissions, _pairs = _load_access_policy(manifest)
    assert policy["a"].quota_cost == 2


def test_every_declared_permission_must_be_used_by_the_access_policy() -> None:
    manifest = _manifest(
        ["p1", "p2"],
        {"a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1}},
    )
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_sod_pair_actions_provided_as_a_string_instead_of_a_list_is_rejected() -> None:
    manifest = _manifest(
        ["p", "q"],
        {
            "a": {"permission": "p", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1},
            "b": {"permission": "q", "entitlement": "e2", "quota_resource": "q2", "quota_cost": 1},
        },
    )
    manifest["metadata"]["sod_pairs"] = [{"actions": "pq"}]
    with pytest.raises(ImproperlyConfigured, match=r"two distinct manifest permissions"):
        _load_access_policy(manifest)


def test_sod_pair_actions_with_more_than_two_members_is_rejected() -> None:
    manifest = _manifest(
        ["p1", "p2", "p3"],
        {
            "a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1},
            "b": {"permission": "p2", "entitlement": "e2", "quota_resource": "q2", "quota_cost": 1},
            "c": {"permission": "p3", "entitlement": "e3", "quota_resource": "q3", "quota_cost": 1},
        },
    )
    manifest["metadata"]["sod_pairs"] = [{"actions": ["p1", "p2", "p3"]}]
    with pytest.raises(ImproperlyConfigured, match=r"two distinct manifest permissions"):
        _load_access_policy(manifest)


def test_sod_pair_action_not_declared_in_manifest_permissions_is_rejected() -> None:
    manifest = _manifest(
        ["p1", "p2"],
        {
            "a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1},
            "b": {"permission": "p2", "entitlement": "e2", "quota_resource": "q2", "quota_cost": 1},
        },
    )
    manifest["metadata"]["sod_pairs"] = [{"actions": ["p1", "not-declared"]}]
    with pytest.raises(ImproperlyConfigured, match=r"two distinct manifest permissions"):
        _load_access_policy(manifest)


def test_sod_pair_actions_that_are_equal_by_value_are_rejected() -> None:
    duplicate = "".join(["p", "1"])
    manifest = _manifest(
        ["p1"],
        {"a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1}},
    )
    manifest["metadata"]["sod_pairs"] = [{"actions": [duplicate, "p1"]}]
    with pytest.raises(ImproperlyConfigured, match=r"two distinct manifest permissions"):
        _load_access_policy(manifest)


def test_sod_actions_missing_a_pair_member_is_rejected() -> None:
    manifest = _manifest(
        ["p1", "p2"],
        {
            "a": {"permission": "p1", "entitlement": "e1", "quota_resource": "q1", "quota_cost": 1},
            "b": {"permission": "p2", "entitlement": "e2", "quota_resource": "q2", "quota_cost": 1},
        },
        sod_pairs=[("p1", "p2")],
    )
    manifest["sod_actions"] = ["p1"]
    with pytest.raises(ImproperlyConfigured):
        _load_access_policy(manifest)


def test_large_sod_pairs_list_without_duplicates_does_not_raise() -> None:
    """`len(pairs)` and `len(set(pairs))` must be compared by value, not identity.

    CPython caches small ints (-5..256), so an accidental identity comparison
    would coincidentally behave like an equality check for short lists. Use a
    pair count well past that cache boundary so freshly allocated, unequal
    `int` objects with equal values would wrongly trip an identity check.
    """
    permissions = [f"customization_framework.synthetic:{i}" for i in range(600)]
    pairs = [(permissions[i], permissions[i + 1]) for i in range(0, 600, 2)]
    access_policy = {
        f"action_{i}": {
            "permission": permission,
            "entitlement": "e",
            "quota_resource": "q",
            "quota_cost": 1,
        }
        for i, permission in enumerate(permissions)
    }
    manifest = _manifest(permissions, access_policy, sod_pairs=pairs)
    _, resolved_permissions, resolved_pairs = _load_access_policy(manifest)
    assert len(resolved_permissions) == 600
    assert len(resolved_pairs) == len(pairs)
