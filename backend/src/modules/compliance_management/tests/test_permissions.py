"""Direct unit coverage for compliance_management's deny-by-default permissions module.

These tests exercise `permissions.py` branch-by-branch: the read/write permission
classification, the quota-resource projection, the frozen access-requirement
dataclass, the fail-closed `requirement_for` lookup, the strict session
authentication challenge header, and every branch of
`ComplianceActionAccessMixin.get_permissions()` (tenant coercion, quota
fallback, and unknown-action denial).
"""

from __future__ import annotations

import dataclasses
import uuid
from types import MappingProxyType, SimpleNamespace

import pytest
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.modules.compliance_management import permissions as perm

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# PERMISSIONS / READ_PERMISSIONS / PERMISSION_QUOTAS
# ---------------------------------------------------------------------------


def test_permissions_registry_has_no_duplicates_and_is_a_tuple():
    assert isinstance(perm.PERMISSIONS, tuple)
    assert len(perm.PERMISSIONS) == len(set(perm.PERMISSIONS))


@pytest.mark.parametrize(
    "permission",
    [
        "compliance.framework:read",
        "compliance.evidence:validate",
        "compliance.framework:export",
        "compliance.configuration:export",
    ],
)
def test_read_write_classification_treats_read_validate_export_as_reads(permission):
    assert permission in perm.READ_PERMISSIONS
    assert perm.PERMISSION_QUOTAS[permission] == "compliance_management.api_reads"


@pytest.mark.parametrize(
    "permission",
    [
        "compliance.framework:create",
        "compliance.framework:update",
        "compliance.framework:archive",
        "compliance.framework:activate",
        "compliance.framework:import",
        "compliance.policy:submit",
        "compliance.configuration:manage",
        "compliance.configuration:activate",
        "compliance.configuration:rollback",
    ],
)
def test_read_write_classification_treats_everything_else_as_writes(permission):
    assert permission not in perm.READ_PERMISSIONS
    assert perm.PERMISSION_QUOTAS[permission] == "compliance_management.api_writes"


def test_permission_quotas_covers_every_declared_permission_exactly_once():
    assert set(perm.PERMISSION_QUOTAS) == set(perm.PERMISSIONS)


def test_read_permissions_is_a_frozenset_and_immutable():
    assert isinstance(perm.READ_PERMISSIONS, frozenset)
    with pytest.raises(AttributeError):
        perm.READ_PERMISSIONS.add("compliance.framework:read")  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# AccessRequirement / _access
# ---------------------------------------------------------------------------


def test_access_requirement_defaults_quota_cost_to_one():
    requirement = perm.AccessRequirement("p", "e", "q")
    assert requirement.quota_cost == 1


def test_access_requirement_is_frozen_and_slotted():
    requirement = perm.AccessRequirement("p", "e", "q")
    with pytest.raises(dataclasses.FrozenInstanceError):
        requirement.permission = "other"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        requirement.__dict__  # slots=True means there is no instance __dict__


def test_access_builds_requirement_from_known_permission():
    requirement = perm._access("compliance.framework:read")
    assert requirement == perm.AccessRequirement(
        "compliance.framework:read",
        "compliance.framework:read",
        "compliance_management.api_reads",
        1,
    )


def test_access_builds_requirement_for_write_permission_with_write_quota():
    requirement = perm._access("compliance.framework:create")
    assert requirement.quota_resource == "compliance_management.api_writes"


def test_access_rejects_unknown_permission_fail_closed():
    with pytest.raises(ValueError, match="unknown compliance permission"):
        perm._access("compliance.framework:not-a-real-action")


# ---------------------------------------------------------------------------
# ACTION_ACCESS
# ---------------------------------------------------------------------------


def test_action_access_is_immutable_mapping_proxy():
    assert isinstance(perm.ACTION_ACCESS, MappingProxyType)
    with pytest.raises(TypeError):
        perm.ACTION_ACCESS["framework.list"] = perm._access("compliance.framework:read")  # type: ignore[index]


def test_action_access_maps_framework_list_to_read_permission():
    assert perm.ACTION_ACCESS["framework.list"].permission == "compliance.framework:read"


def test_action_access_qualified_policy_versions_get_and_post_differ():
    get_entry = perm.ACTION_ACCESS["policy.versions:get"]
    post_entry = perm.ACTION_ACCESS["policy.versions:post"]
    assert get_entry.permission == "compliance.policy:read"
    assert post_entry.permission == "compliance.policy:version"


# ---------------------------------------------------------------------------
# requirement_for
# ---------------------------------------------------------------------------


def test_requirement_for_falls_back_to_unqualified_when_no_qualified_entry():
    # "framework.list:get" is not a registered key, so the method-qualified
    # lookup must miss and fall through to the plain "framework.list" entry.
    result = perm.requirement_for("framework", "list", method="GET")
    assert result is perm.ACTION_ACCESS["framework.list"]


def test_requirement_for_uses_qualified_entry_when_method_distinguishes_get_from_post():
    get_result = perm.requirement_for("policy", "versions", method="GET")
    post_result = perm.requirement_for("policy", "versions", method="POST")
    assert get_result is perm.ACTION_ACCESS["policy.versions:get"]
    assert post_result is perm.ACTION_ACCESS["policy.versions:post"]
    assert get_result != post_result


def test_requirement_for_is_case_insensitive_on_method():
    assert perm.requirement_for("policy", "versions", method="get") == perm.requirement_for(
        "policy", "versions", method="GET"
    )


def test_requirement_for_without_method_uses_unqualified_lookup():
    result = perm.requirement_for("framework", "list")
    assert result is perm.ACTION_ACCESS["framework.list"]


def test_requirement_for_returns_none_for_unknown_action_fail_closed():
    assert perm.requirement_for("framework", "not-a-real-action") is None
    assert perm.requirement_for("not-a-real-viewset", "list") is None
    assert perm.requirement_for("framework", "not-a-real-action", method="GET") is None


# ---------------------------------------------------------------------------
# StrictSessionAuthentication
# ---------------------------------------------------------------------------


def test_strict_session_authentication_always_challenges_with_session():
    auth = perm.StrictSessionAuthentication()
    assert auth.authenticate_header(request=object()) == "Session"
    assert auth.authenticate_header(request=None) == "Session"


# ---------------------------------------------------------------------------
# ComplianceActionAccessMixin.get_permissions()
# ---------------------------------------------------------------------------


class _View(perm.ComplianceActionAccessMixin):
    """Minimal concrete view for exercising the mixin in isolation."""


def _request(tenant_value, *, has_user=True):
    if has_user:
        user = SimpleNamespace(profile=SimpleNamespace(tenant_id=tenant_value))
    else:
        user = None
    return SimpleNamespace(user=user)


def test_get_permissions_returns_authenticated_and_requires_access_instances():
    view = _View()
    view.request = _request(str(uuid.uuid4()))
    view.action = "list"
    view.action_permissions = {"list": "compliance.framework:read"}
    result = view.get_permissions()
    assert len(result) == 2
    assert isinstance(result[0], IsAuthenticated)
    assert isinstance(result[1], RequiresAccess)


def test_get_permissions_coerces_valid_tenant_id_string_to_uuid():
    tenant_id = uuid.uuid4()
    view = _View()
    view.request = _request(str(tenant_id))
    view.action = "list"
    view.get_permissions()
    assert view.request.tenant_id == tenant_id


def test_get_permissions_accepts_tenant_id_already_a_uuid_instance():
    tenant_id = uuid.uuid4()
    view = _View()
    view.request = _request(tenant_id)
    view.action = "list"
    view.get_permissions()
    assert view.request.tenant_id == tenant_id


def test_get_permissions_sets_tenant_id_none_when_tenant_value_missing():
    view = _View()
    view.request = _request(None)
    view.action = "list"
    view.get_permissions()
    assert view.request.tenant_id is None


def test_get_permissions_fails_closed_to_none_on_invalid_tenant_string():
    view = _View()
    view.request = _request("not-a-uuid")
    view.action = "list"
    view.get_permissions()
    assert view.request.tenant_id is None


def test_get_permissions_fails_closed_to_none_on_non_string_tenant_value():
    # str(123) == "123", which UUID() rejects with ValueError.
    view = _View()
    view.request = _request(123)
    view.action = "list"
    view.get_permissions()
    assert view.request.tenant_id is None


def test_get_permissions_fails_closed_when_user_has_no_profile_attribute():
    view = _View()
    view.request = _request(None, has_user=False)
    view.action = "list"
    view.get_permissions()
    assert view.request.tenant_id is None


def test_get_permissions_denies_unknown_action_with_none_permission_and_quota():
    view = _View()
    view.request = _request(str(uuid.uuid4()))
    view.action = "not-a-configured-action"
    view.action_permissions = {"list": "compliance.framework:read"}
    view.get_permissions()
    assert view.required_permission is None
    assert view.required_entitlement is None
    assert view.quota_resource is None


def test_get_permissions_projects_quota_resource_from_permission_quotas():
    view = _View()
    view.request = _request(str(uuid.uuid4()))
    view.action = "list"
    view.action_permissions = {"list": "compliance.framework:read"}
    view.get_permissions()
    assert view.required_permission == "compliance.framework:read"
    assert view.required_entitlement == "compliance.framework:read"
    assert view.quota_resource == "compliance_management.api_reads"


def test_get_permissions_projects_write_quota_resource_for_write_permission():
    view = _View()
    view.request = _request(str(uuid.uuid4()))
    view.action = "create"
    view.action_permissions = {"create": "compliance.framework:create"}
    view.get_permissions()
    assert view.quota_resource == "compliance_management.api_writes"


def test_get_permissions_explicit_action_quota_overrides_permission_quota():
    view = _View()
    view.request = _request(str(uuid.uuid4()))
    view.action = "list"
    view.action_permissions = {"list": "compliance.framework:read"}
    view.action_quotas = {"list": "compliance_management.custom_quota"}
    view.get_permissions()
    assert view.quota_resource == "compliance_management.custom_quota"


def test_get_permissions_permission_not_in_quota_table_yields_none_quota():
    view = _View()
    view.request = _request(str(uuid.uuid4()))
    view.action = "weird"
    view.action_permissions = {"weird": "compliance.not-a-real-permission"}
    view.get_permissions()
    assert view.required_permission == "compliance.not-a-real-permission"
    assert view.quota_resource is None


def test_get_permissions_always_resets_quota_cost_to_one():
    view = _View()
    view.quota_cost = 99
    view.request = _request(str(uuid.uuid4()))
    view.action = "list"
    view.action_permissions = {"list": "compliance.framework:read"}
    view.get_permissions()
    assert view.quota_cost == 1


def test_action_access_mixin_is_the_compliance_mixin():
    assert perm.ActionAccessMixin is perm.ComplianceActionAccessMixin


def test_module_all_matches_public_surface():
    for name in perm.__all__:
        assert hasattr(perm, name), name
