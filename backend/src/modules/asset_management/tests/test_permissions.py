"""Exhaustive branch coverage for asset_management.permissions fail-closed logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.modules import asset_management as asset_management_pkg
from src.modules.asset_management import permissions as perm_module
from src.modules.asset_management.permissions import (
    ASSET_ACTIVATE,
    ASSET_CREATE,
    ASSET_DEACTIVATE,
    ASSET_DELETE,
    ASSET_READ,
    ASSET_UPDATE,
    CONFIGURATION_EXPORT,
    CONFIGURATION_IMPORT,
    CONFIGURATION_READ,
    CONFIGURATION_ROLLBACK,
    CONFIGURATION_UPDATE,
    DEPRECIATION_READ,
    ENTITLEMENT,
    HEALTH_ACTION_PERMISSIONS,
    HEALTH_READ,
    PERMISSIONS,
    SOD_ACTIONS,
    ActionAccessMixin,
    AssetAccessMixin,
)


del asset_management_pkg


# --------------------------------------------------------------------------
# Constant / registry pin tests
# --------------------------------------------------------------------------


def test_entitlement_exact_value():
    assert ENTITLEMENT == "asset_management"


@pytest.mark.parametrize(
    ("constant", "expected"),
    [
        (ASSET_CREATE, "asset.asset:create"),
        (ASSET_READ, "asset.asset:read"),
        (ASSET_UPDATE, "asset.asset:update"),
        (ASSET_DELETE, "asset.asset:delete"),
        (ASSET_ACTIVATE, "asset.asset:activate"),
        (ASSET_DEACTIVATE, "asset.asset:deactivate"),
        (DEPRECIATION_READ, "asset.depreciation:read"),
        (CONFIGURATION_READ, "asset.configuration:read"),
        (CONFIGURATION_UPDATE, "asset.configuration:update"),
        (CONFIGURATION_ROLLBACK, "asset.configuration:rollback"),
        (CONFIGURATION_IMPORT, "asset.configuration:import"),
        (CONFIGURATION_EXPORT, "asset.configuration:export"),
        (HEALTH_READ, "asset.health:read"),
    ],
)
def test_action_permission_constants_exact_value(constant, expected):
    assert constant == expected


def test_health_action_permissions_exact_mapping():
    assert HEALTH_ACTION_PERMISSIONS == {"health": HEALTH_READ}
    assert len(HEALTH_ACTION_PERMISSIONS) == 1


def test_permissions_tuple_exact_membership():
    expected = {
        ASSET_CREATE,
        ASSET_READ,
        ASSET_UPDATE,
        ASSET_DELETE,
        ASSET_ACTIVATE,
        ASSET_DEACTIVATE,
        DEPRECIATION_READ,
        CONFIGURATION_READ,
        CONFIGURATION_UPDATE,
        CONFIGURATION_ROLLBACK,
        CONFIGURATION_IMPORT,
        CONFIGURATION_EXPORT,
        HEALTH_READ,
    }
    assert set(PERMISSIONS) == expected
    assert len(PERMISSIONS) == len(expected)
    for value in PERMISSIONS:
        assert value.startswith("asset.")


def test_sod_actions_is_empty_tuple():
    assert SOD_ACTIONS == ()
    assert isinstance(SOD_ACTIONS, tuple)


def test_dunder_all_contents():
    assert "ActionAccessMixin" in perm_module.__all__
    assert "AssetAccessMixin" in perm_module.__all__
    assert "HEALTH_ACTION_PERMISSIONS" in perm_module.__all__
    assert "PERMISSIONS" in perm_module.__all__
    assert "SOD_ACTIONS" in perm_module.__all__
    assert "ASSET_CREATE" in perm_module.__all__
    assert "ENTITLEMENT" in perm_module.__all__


def test_dunder_all_is_exactly_the_fixed_names_plus_upper_string_constants():
    # Pin the exact __all__ membership so a filter regression (e.g. swapping the
    # `and` in `name.isupper() and isinstance(value, str)` for `or`) is caught —
    # an `or` would additionally pull in every string-valued dunder (__name__,
    # __doc__, __file__, __package__, ...) which are not upper-case identifiers.
    fixed_names = {
        "ActionAccessMixin",
        "AssetAccessMixin",
        "HEALTH_ACTION_PERMISSIONS",
        "PERMISSIONS",
        "SOD_ACTIONS",
    }
    upper_string_constant_names = {
        name
        for name, value in vars(perm_module).items()
        if name.isupper() and isinstance(value, str)
    }
    assert set(perm_module.__all__) == fixed_names | upper_string_constant_names
    # None of the module's lower/dunder string globals (which satisfy
    # `isinstance(value, str)` but not `isupper()`) may leak in.
    assert "__name__" not in perm_module.__all__
    assert "__doc__" not in perm_module.__all__
    assert "__file__" not in perm_module.__all__


# --------------------------------------------------------------------------
# AssetAccessMixin.get_permissions
# --------------------------------------------------------------------------


def _make_asset_view(*, action, tenant_id, action_permissions):
    view = AssetAccessMixin()
    view.action = action
    view.action_permissions = action_permissions
    view.request = SimpleNamespace(user=SimpleNamespace())
    with patch.object(perm_module, "get_user_tenant_id", return_value=tenant_id):
        result = view.get_permissions()
    return view, result


def test_asset_access_mixin_class_attrs():
    assert AssetAccessMixin.required_entitlement == ENTITLEMENT
    assert AssetAccessMixin.action_permissions == {}
    assert AssetAccessMixin.authentication_classes == (perm_module.StrictSessionAuthentication,)
    assert AssetAccessMixin.permission_classes == (IsAuthenticated, RequiresAccess)


def test_asset_access_mixin_valid_tenant_coerces_to_uuid():
    tenant = uuid4()
    view, result = _make_asset_view(action="list", tenant_id=str(tenant), action_permissions={})
    assert view.request.tenant_id == tenant
    assert isinstance(view.request.tenant_id, UUID)
    assert len(result) == 2
    assert isinstance(result[0], IsAuthenticated)
    assert isinstance(result[1], RequiresAccess)


def test_asset_access_mixin_none_tenant_yields_none():
    view, _ = _make_asset_view(action="list", tenant_id=None, action_permissions={})
    assert view.request.tenant_id is None


def test_asset_access_mixin_invalid_tenant_swallowed_to_none():
    # A raw value UUID() cannot parse must not propagate — fail closed to None.
    view, _ = _make_asset_view(action="list", tenant_id="not-a-uuid", action_permissions={})
    assert view.request.tenant_id is None


def test_asset_access_mixin_unexpected_lookup_failure_swallowed_to_none():
    view = AssetAccessMixin()
    view.action = "list"
    view.action_permissions = {}
    view.request = SimpleNamespace(user=SimpleNamespace())
    with patch.object(perm_module, "get_user_tenant_id", side_effect=RuntimeError("boom")):
        view.get_permissions()
    assert view.request.tenant_id is None


def test_asset_access_mixin_known_action_sets_permission_and_quota():
    view, _ = _make_asset_view(
        action="create",
        tenant_id=None,
        action_permissions={"create": ASSET_CREATE},
    )
    assert view.required_permission == ASSET_CREATE
    assert view.quota_resource == "asset_management.api.requests"
    assert view.quota_cost == 1


def test_asset_access_mixin_unknown_action_has_no_permission_or_quota():
    view, _ = _make_asset_view(
        action="destroy",
        tenant_id=None,
        action_permissions={"create": ASSET_CREATE},
    )
    assert view.required_permission is None
    assert view.quota_resource is None
    assert view.quota_cost == 1


def test_asset_access_mixin_missing_action_attribute_defaults_to_none_lookup():
    view = AssetAccessMixin()
    view.action_permissions = {}
    view.request = SimpleNamespace(user=SimpleNamespace())
    with patch.object(perm_module, "get_user_tenant_id", return_value=None):
        view.get_permissions()
    assert view.required_permission is None
    assert view.quota_resource is None


# --------------------------------------------------------------------------
# ActionAccessMixin.get_permissions
# --------------------------------------------------------------------------


def _make_action_view(*, action=None, action_permissions, tenant_side_effect=None, tenant_value=None):
    view = ActionAccessMixin()
    if action is not None:
        view.action = action
    view.action_permissions = action_permissions
    view.request = SimpleNamespace(user=SimpleNamespace())
    if tenant_side_effect is not None:
        patcher = patch.object(perm_module, "get_user_tenant_id", side_effect=tenant_side_effect)
    else:
        patcher = patch.object(perm_module, "get_user_tenant_id", return_value=tenant_value)
    with patcher:
        result = view.get_permissions()
    return view, result


def test_action_access_mixin_class_attrs():
    assert ActionAccessMixin.action_permissions == {}
    assert ActionAccessMixin.quota_cost == 1
    assert ActionAccessMixin.authentication_classes == (perm_module.StrictSessionAuthentication,)
    assert ActionAccessMixin.permission_classes == (IsAuthenticated, RequiresAccess)


def test_action_access_mixin_default_action_is_empty_string_when_missing():
    view, result = _make_action_view(action_permissions={}, tenant_value=None)
    assert view.required_permission is None
    assert view.required_entitlement is None
    assert view.quota_resource is None
    assert len(result) == 2
    assert isinstance(result[0], IsAuthenticated)
    assert isinstance(result[1], RequiresAccess)


def test_action_access_mixin_known_action_sets_permission_entitlement_and_quota():
    view, _ = _make_action_view(
        action="read",
        action_permissions={"read": ASSET_READ},
        tenant_value=None,
    )
    assert view.required_permission == ASSET_READ
    assert view.required_entitlement == ASSET_READ
    assert view.quota_resource == "asset_management.api.requests"


def test_action_access_mixin_unknown_action_has_no_permission_entitlement_or_quota():
    view, _ = _make_action_view(
        action="unmapped",
        action_permissions={"read": ASSET_READ},
        tenant_value=None,
    )
    assert view.required_permission is None
    assert view.required_entitlement is None
    assert view.quota_resource is None


def test_action_access_mixin_tenant_none_leaves_tenant_id_none():
    view, _ = _make_action_view(action="read", action_permissions={}, tenant_value=None)
    assert view.request.tenant_id is None


def test_action_access_mixin_valid_tenant_value_sets_uuid():
    tenant = uuid4()
    view, _ = _make_action_view(action="read", action_permissions={}, tenant_value=str(tenant))
    assert view.request.tenant_id == tenant
    assert isinstance(view.request.tenant_id, UUID)


def test_action_access_mixin_invalid_tenant_value_reset_to_none():
    view, _ = _make_action_view(action="read", action_permissions={}, tenant_value="garbage-not-uuid")
    assert view.request.tenant_id is None


def test_action_access_mixin_tenant_value_type_error_reset_to_none():
    # A tenant value whose str() succeeds but UUID() rejects via TypeError-class path.
    view, _ = _make_action_view(action="read", action_permissions={}, tenant_value=object())
    assert view.request.tenant_id is None


def test_action_access_mixin_lookup_failure_on_non_health_action_defaults_tenant_none():
    view, result = _make_action_view(
        action="read",
        action_permissions={"read": ASSET_READ},
        tenant_side_effect=RuntimeError("boom"),
    )
    assert view.request.tenant_id is None
    # Non-health failure path still falls through to the standard permission pair.
    assert len(result) == 2
    assert isinstance(result[0], IsAuthenticated)
    assert isinstance(result[1], RequiresAccess)
    # required_permission/entitlement were already computed before the failure.
    assert view.required_permission == ASSET_READ
    assert view.required_entitlement == ASSET_READ


def test_action_access_mixin_lookup_failure_on_health_action_returns_authenticated_only():
    view, result = _make_action_view(
        action="health",
        action_permissions=HEALTH_ACTION_PERMISSIONS,
        tenant_side_effect=RuntimeError("boom"),
    )
    assert len(result) == 1
    assert isinstance(result[0], IsAuthenticated)
    assert not isinstance(result[0], RequiresAccess)
    # required_permission was resolved from action_permissions before the failure.
    assert view.required_permission == HEALTH_READ


def test_action_access_mixin_health_check_uses_exact_equality_not_ordering():
    # A pin against `action == "health"` being weakened to `action <= "health"`:
    # "apple" <= "health" is also True, so a `<=` mutant would wrongly treat a
    # non-health action as the health action on lookup failure.
    view, result = _make_action_view(
        action="apple",
        action_permissions={},
        tenant_side_effect=RuntimeError("boom"),
    )
    assert len(result) == 2
    assert isinstance(result[0], IsAuthenticated)
    assert isinstance(result[1], RequiresAccess)
    assert view.request.tenant_id is None


def test_action_access_mixin_health_check_uses_equality_not_identity():
    # A pin against `action == "health"` being weakened to `action is "health"`.
    # Build the action string at runtime via join so it is guaranteed to be a
    # distinct object from any interned "health" literal in the source module,
    # while still comparing equal by value.
    dynamic_health = "".join(["h", "e", "a", "l", "t", "h"])
    assert dynamic_health == "health"
    view, result = _make_action_view(
        action=dynamic_health,
        action_permissions=HEALTH_ACTION_PERMISSIONS,
        tenant_side_effect=RuntimeError("boom"),
    )
    assert len(result) == 1
    assert isinstance(result[0], IsAuthenticated)
    assert not isinstance(result[0], RequiresAccess)


class _StrRaises:
    """Helper whose str() raises a specific exception type, to drive UUID(str(x))."""

    def __init__(self, exc: type[BaseException]):
        self._exc = exc

    def __str__(self):  # noqa: DUNDER
        raise self._exc("forced failure")


def test_action_access_mixin_inner_except_catches_attribute_error():
    # If AttributeError is dropped from the inner `except (AttributeError,
    # TypeError, ValueError)` tuple, str(tenant_value) raising AttributeError
    # propagates to the outer `except Exception:` instead, which for the
    # "health" action short-circuits to a single-permission return — a
    # detectable behavioral difference from the correctly-caught inner path.
    view, result = _make_action_view(
        action="health",
        action_permissions=HEALTH_ACTION_PERMISSIONS,
        tenant_value=_StrRaises(AttributeError),
    )
    assert len(result) == 2
    assert isinstance(result[0], IsAuthenticated)
    assert isinstance(result[1], RequiresAccess)
    assert view.request.tenant_id is None


def test_action_access_mixin_inner_except_catches_type_error():
    view, result = _make_action_view(
        action="health",
        action_permissions=HEALTH_ACTION_PERMISSIONS,
        tenant_value=_StrRaises(TypeError),
    )
    assert len(result) == 2
    assert isinstance(result[0], IsAuthenticated)
    assert isinstance(result[1], RequiresAccess)
    assert view.request.tenant_id is None


def test_action_access_mixin_inner_except_catches_value_error():
    # A plain non-UUID string drives UUID(str(x)) to raise ValueError directly.
    view, result = _make_action_view(
        action="health",
        action_permissions=HEALTH_ACTION_PERMISSIONS,
        tenant_value="not-a-real-uuid",
    )
    assert len(result) == 2
    assert isinstance(result[0], IsAuthenticated)
    assert isinstance(result[1], RequiresAccess)
    assert view.request.tenant_id is None


def test_action_access_mixin_tenant_id_reset_to_none_at_start_each_call():
    view = ActionAccessMixin()
    view.action = "read"
    view.action_permissions = {}
    view.request = SimpleNamespace(user=SimpleNamespace(), tenant_id=uuid4())
    with patch.object(perm_module, "get_user_tenant_id", return_value=None):
        view.get_permissions()
    assert view.request.tenant_id is None
