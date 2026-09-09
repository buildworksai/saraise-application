"""Unit tests for the fail-closed inventory permission/quota metadata module.

These tests exercise ``permissions.py`` in isolation (no DB, no HTTP stack) so
that every branch of ``InventoryAccessMixin.get_permissions`` and every
constant/registry is pinned exactly, not merely smoke-tested.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.modules.inventory_management import permissions as perm_mod
from src.modules.inventory_management.permissions import (
    API_QUOTA,
    BATCH_CREATE,
    BULK_QUOTA,
    ENTITLEMENT,
    HEALTH_READ,
    ITEM_CREATE,
    PERMISSIONS,
    POST_QUOTA,
    SOD_ACTIONS,
    STOCK_ENTRY_APPROVE,
    STOCK_ENTRY_CREATE,
    STOCK_ENTRY_POST,
    WAREHOUSE_CREATE,
    WAREHOUSE_DELETE,
    WAREHOUSE_READ,
    WAREHOUSE_UPDATE,
    InventoryAccessMixin,
    InventorySessionAuthentication,
    IsInventoryUser,
    _permission,
)


# --------------------------------------------------------------------------
# _permission() helper
# --------------------------------------------------------------------------


def test_permission_helper_formats_resource_and_operation() -> None:
    assert _permission("warehouse", "create") == "inventory.warehouse:create"


def test_permission_helper_uses_colon_separator_not_dot() -> None:
    result = _permission("item", "read")
    assert result == "inventory.item:read"
    assert result.count(":") == 1
    assert not result.endswith(".read")


def test_permission_constants_match_generated_pattern() -> None:
    assert WAREHOUSE_CREATE == "inventory.warehouse:create"
    assert WAREHOUSE_READ == "inventory.warehouse:read"
    assert WAREHOUSE_UPDATE == "inventory.warehouse:update"
    assert WAREHOUSE_DELETE == "inventory.warehouse:delete"
    assert ITEM_CREATE == "inventory.item:create"
    assert BATCH_CREATE == "inventory.batch:create"
    assert HEALTH_READ == "inventory.health:read"


# --------------------------------------------------------------------------
# Module-level constants
# --------------------------------------------------------------------------


def test_entitlement_and_quota_names_are_pinned() -> None:
    assert ENTITLEMENT == "inventory_management"
    assert API_QUOTA == "inventory.api.requests"
    assert POST_QUOTA == "inventory.stock.post"
    assert BULK_QUOTA == "inventory.bulk.rows"


def test_permissions_tuple_exact_length_and_no_duplicates() -> None:
    assert len(PERMISSIONS) == 55
    assert len(set(PERMISSIONS)) == len(PERMISSIONS)


def test_permissions_tuple_starts_and_ends_with_expected_entries() -> None:
    assert PERMISSIONS[0] == WAREHOUSE_CREATE
    assert PERMISSIONS[-1] == HEALTH_READ


def test_permissions_tuple_is_a_tuple_not_list() -> None:
    assert isinstance(PERMISSIONS, tuple)


def test_sod_actions_pinned_exactly() -> None:
    assert SOD_ACTIONS == (STOCK_ENTRY_CREATE, STOCK_ENTRY_APPROVE)
    assert len(SOD_ACTIONS) == 2
    assert STOCK_ENTRY_POST not in SOD_ACTIONS


def test_is_inventory_user_is_requires_access_alias() -> None:
    assert IsInventoryUser is RequiresAccess


# --------------------------------------------------------------------------
# InventorySessionAuthentication.authenticate_header
# --------------------------------------------------------------------------


def test_authenticate_header_returns_session_literal() -> None:
    auth = InventorySessionAuthentication()
    assert auth.authenticate_header(request=object()) == "Session"


def test_authenticate_header_ignores_request_argument() -> None:
    auth = InventorySessionAuthentication()
    # Passing wildly different request objects must not change the result;
    # the method deliberately discards its argument.
    assert auth.authenticate_header(None) == "Session"
    assert auth.authenticate_header(SimpleNamespace(foo="bar")) == "Session"


def test_authenticate_header_is_not_empty_or_whitespace() -> None:
    auth = InventorySessionAuthentication()
    header = auth.authenticate_header(object())
    assert header != ""
    assert header.strip() == header
    assert len(header) == len("Session")


# --------------------------------------------------------------------------
# InventoryAccessMixin.get_permissions()
# --------------------------------------------------------------------------


class _FakeView(InventoryAccessMixin):
    """Minimal stand-in for a DRF ViewSet using the mixin."""

    def __init__(self, request: object, action: str | None = None) -> None:
        self.request = request
        if action is not None:
            self.action = action


def _make_request(user: object) -> SimpleNamespace:
    return SimpleNamespace(user=user)


def test_get_permissions_short_circuits_for_swagger_fake_view() -> None:
    view = _FakeView(request=_make_request(user=None), action="list")
    view.swagger_fake_view = True
    result = view.get_permissions()
    assert result == []


def test_get_permissions_returns_authenticated_and_requires_access_instances() -> None:
    view = _FakeView(request=_make_request(user=None), action="list")
    result = view.get_permissions()
    assert len(result) == 2
    assert isinstance(result[0], IsAuthenticated)
    assert isinstance(result[1], RequiresAccess)


def test_get_permissions_sets_tenant_id_from_valid_uuid_string(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_uuid = uuid4()
    monkeypatch.setattr(perm_mod, "get_user_tenant_id", lambda user: str(tenant_uuid))
    view = _FakeView(request=_make_request(user=object()), action="list")
    view.get_permissions()
    assert view.request.tenant_id == tenant_uuid
    assert isinstance(view.request.tenant_id, UUID)


def test_get_permissions_sets_tenant_id_none_when_raw_tenant_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(perm_mod, "get_user_tenant_id", lambda user: None)
    view = _FakeView(request=_make_request(user=object()), action="list")
    view.get_permissions()
    assert view.request.tenant_id is None


def test_get_permissions_sets_tenant_id_none_when_raw_tenant_is_falsy_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(perm_mod, "get_user_tenant_id", lambda user: "")
    view = _FakeView(request=_make_request(user=object()), action="list")
    view.get_permissions()
    assert view.request.tenant_id is None


def test_get_permissions_sets_tenant_id_none_on_invalid_uuid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(perm_mod, "get_user_tenant_id", lambda user: "not-a-uuid")
    view = _FakeView(request=_make_request(user=object()), action="list")
    view.get_permissions()
    assert view.request.tenant_id is None


def test_get_permissions_swallows_attribute_error_when_stringifying_raw_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ExplodesOnStr:
        def __str__(self) -> str:  # noqa: D105
            raise AttributeError("boom")

    monkeypatch.setattr(perm_mod, "get_user_tenant_id", lambda user: _ExplodesOnStr())
    view = _FakeView(request=_make_request(user=object()), action="list")
    # Must not propagate; tenant_id falls back to None.
    view.get_permissions()
    assert view.request.tenant_id is None


def test_get_permissions_resolves_known_action_to_declared_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(perm_mod, "get_user_tenant_id", lambda user: None)
    view = _FakeView(request=_make_request(user=None), action="list")
    view.action_permissions = {"list": WAREHOUSE_READ}
    view.get_permissions()
    assert view.required_permission == WAREHOUSE_READ


def test_get_permissions_unknown_action_yields_none_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(perm_mod, "get_user_tenant_id", lambda user: None)
    view = _FakeView(request=_make_request(user=None), action="destroy")
    view.action_permissions = {"list": WAREHOUSE_READ}
    view.get_permissions()
    assert view.required_permission is None


def test_get_permissions_missing_action_attribute_defaults_to_empty_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(perm_mod, "get_user_tenant_id", lambda user: None)
    view = _FakeView(request=_make_request(user=None))  # no action set
    view.action_permissions = {"": WAREHOUSE_READ}
    view.get_permissions()
    # str(getattr(self, "action", "")) must resolve to "" and match the dict.
    assert view.required_permission == WAREHOUSE_READ


def test_get_permissions_quota_resource_uses_action_quota_when_permission_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(perm_mod, "get_user_tenant_id", lambda user: None)
    view = _FakeView(request=_make_request(user=None), action="post")
    view.action_permissions = {"post": STOCK_ENTRY_POST}
    view.action_quotas = {"post": POST_QUOTA}
    view.get_permissions()
    assert view.quota_resource == POST_QUOTA


def test_get_permissions_quota_resource_defaults_to_api_quota_when_not_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(perm_mod, "get_user_tenant_id", lambda user: None)
    view = _FakeView(request=_make_request(user=None), action="list")
    view.action_permissions = {"list": WAREHOUSE_READ}
    view.action_quotas = {}
    view.get_permissions()
    assert view.quota_resource == API_QUOTA


def test_get_permissions_quota_resource_is_none_when_permission_not_required_even_if_quota_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-closed: an action_quotas entry must never leak a quota resource
    for an action that has no declared permission."""

    monkeypatch.setattr(perm_mod, "get_user_tenant_id", lambda user: None)
    view = _FakeView(request=_make_request(user=None), action="unlisted")
    view.action_permissions = {}
    view.action_quotas = {"unlisted": BULK_QUOTA}
    view.get_permissions()
    assert view.required_permission is None
    assert view.quota_resource is None


def test_get_permissions_calls_get_quota_cost_with_action(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(perm_mod, "get_user_tenant_id", lambda user: None)
    view = _FakeView(request=_make_request(user=None), action="create")
    view.action_permissions = {"create": ITEM_CREATE}

    seen_actions: list[str] = []

    def spy(self: object, action: str) -> int:
        seen_actions.append(action)
        return 7

    view.get_quota_cost = spy.__get__(view, _FakeView)
    view.get_permissions()
    assert seen_actions == ["create"]
    assert view.quota_cost == 7


def test_get_permissions_default_quota_cost_is_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(perm_mod, "get_user_tenant_id", lambda user: None)
    view = _FakeView(request=_make_request(user=None), action="list")
    view.get_permissions()
    assert view.quota_cost == 1


def test_get_quota_cost_default_returns_one_regardless_of_action() -> None:
    view = _FakeView(request=_make_request(user=None), action="anything")
    assert view.get_quota_cost("create") == 1
    assert view.get_quota_cost("") == 1
    assert view.get_quota_cost("delete") == 1


def test_get_permissions_returns_list_type_not_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(perm_mod, "get_user_tenant_id", lambda user: None)
    view = _FakeView(request=_make_request(user=None), action="list")
    result = view.get_permissions()
    assert isinstance(result, list)


def test_get_permissions_swagger_fake_view_false_still_runs_normal_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(perm_mod, "get_user_tenant_id", lambda user: None)
    view = _FakeView(request=_make_request(user=None), action="list")
    view.swagger_fake_view = False
    result = view.get_permissions()
    assert len(result) == 2


def test_mixin_class_attributes_pinned() -> None:
    assert InventoryAccessMixin.authentication_classes == (InventorySessionAuthentication,)
    assert InventoryAccessMixin.permission_classes == (IsAuthenticated, RequiresAccess)
    assert InventoryAccessMixin.action_permissions == {}
    assert InventoryAccessMixin.action_quotas == {}
    assert InventoryAccessMixin.required_entitlement == ENTITLEMENT


# --------------------------------------------------------------------------
# __all__ export surface
# --------------------------------------------------------------------------


def test_all_exports_include_core_names() -> None:
    assert "InventoryAccessMixin" in perm_mod.__all__
    assert "InventorySessionAuthentication" in perm_mod.__all__
    assert "IsInventoryUser" in perm_mod.__all__
    assert "PERMISSIONS" in perm_mod.__all__
    assert "SOD_ACTIONS" in perm_mod.__all__
    assert "WAREHOUSE_CREATE" in perm_mod.__all__
    assert "HEALTH_READ" in perm_mod.__all__


def test_all_exports_exclude_lowercase_helpers() -> None:
    assert "_permission" not in perm_mod.__all__
