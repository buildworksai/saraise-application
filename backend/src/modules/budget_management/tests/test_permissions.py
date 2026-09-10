"""Unit tests for budget_management.permissions — fail-closed action authorization.

Covers:
- SessionAuthentication401.authenticate_header always advertises "Session".
- BudgetAccessMixin.get_permissions tenant coercion: valid UUID string, invalid
  value, and no tenant at all.
- Action -> permission / quota resolution, including unmapped actions (fail
  closed to None) and the `permission_action` fallback when `action` is unset.
- required_entitlement is always pinned to "module.budget_management".
- quota_cost is always fixed at 1.
- get_permissions always returns a fresh [IsAuthenticated(), RequiresAccess()]
  pair regardless of branch taken.
- PERMISSIONS registry is pinned by exact membership, order, and count so any
  addition/removal/reorder is caught.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.modules.budget_management.permissions import PERMISSIONS, BudgetAccessMixin, SessionAuthentication401


class _View(BudgetAccessMixin):
    """Minimal concrete view stand-in exercising BudgetAccessMixin directly."""


def _make_view(*, action=None, permission_action=None, user=None, action_permissions=None, action_quotas=None):
    view = _View()
    view.request = SimpleNamespace(user=user)
    if action is not None:
        view.action = action
    if permission_action is not None:
        view.permission_action = permission_action
    if action_permissions is not None:
        view.action_permissions = action_permissions
    if action_quotas is not None:
        view.action_quotas = action_quotas
    return view


class _Profile:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


class _User:
    def __init__(self, tenant_id):
        self.profile = _Profile(tenant_id)


# --- SessionAuthentication401 -------------------------------------------------


def test_session_authentication_401_header_is_exactly_session():
    auth = SessionAuthentication401()
    assert auth.authenticate_header(request=object()) == "Session"


def test_session_authentication_401_header_ignores_request_argument():
    auth = SessionAuthentication401()
    # Different request objects must not change the returned header string.
    assert auth.authenticate_header(request=None) == auth.authenticate_header(request="anything")


def test_session_authentication_401_is_session_authentication_subclass():
    from rest_framework.authentication import SessionAuthentication

    assert issubclass(SessionAuthentication401, SessionAuthentication)


# --- Tenant coercion -----------------------------------------------------------


def test_get_permissions_valid_tenant_uuid_string_is_coerced():
    tenant_uuid = UUID("12345678-1234-5678-1234-567812345678")
    user = _User(str(tenant_uuid))
    view = _make_view(action="list", user=user)

    view.get_permissions()

    assert view.request.tenant_id == tenant_uuid
    assert isinstance(view.request.tenant_id, UUID)


def test_get_permissions_valid_tenant_uuid_object_is_coerced():
    tenant_uuid = UUID("87654321-4321-8765-4321-876543218765")
    user = _User(tenant_uuid)
    view = _make_view(action="list", user=user)

    view.get_permissions()

    assert view.request.tenant_id == tenant_uuid


def test_get_permissions_invalid_tenant_value_yields_none():
    user = _User("not-a-uuid")
    view = _make_view(action="list", user=user)

    view.get_permissions()

    assert view.request.tenant_id is None


def test_get_permissions_no_tenant_yields_none_without_raising():
    user = _User(None)
    view = _make_view(action="list", user=user)

    view.get_permissions()

    assert view.request.tenant_id is None


def test_get_permissions_missing_user_yields_none_tenant():
    view = _make_view(action="list", user=None)

    view.get_permissions()

    assert view.request.tenant_id is None


def test_get_permissions_empty_string_tenant_is_falsy_and_yields_none():
    # Empty string is falsy, so `if tenant else None` must short-circuit to None
    # rather than attempting UUID("").
    user = _User("")
    view = _make_view(action="list", user=user)

    view.get_permissions()

    assert view.request.tenant_id is None


# --- Action -> permission / quota resolution -----------------------------------


def test_get_permissions_maps_known_action_to_permission_and_quota():
    user = _User(None)
    view = _make_view(
        action="list",
        user=user,
        action_permissions={"list": "budget.budget:read"},
        action_quotas={"list": "budget_management.api_reads"},
    )

    view.get_permissions()

    assert view.required_permission == "budget.budget:read"
    assert view.quota_resource == "budget_management.api_reads"


def test_get_permissions_unmapped_action_fails_closed_to_none_permission():
    user = _User(None)
    view = _make_view(
        action="destroy",
        user=user,
        action_permissions={"list": "budget.budget:read"},
        action_quotas={"list": "budget_management.api_reads"},
    )

    view.get_permissions()

    assert view.required_permission is None
    assert view.quota_resource is None


def test_get_permissions_no_action_attribute_falls_back_to_permission_action():
    user = _User(None)
    view = _make_view(
        permission_action="calculate",
        user=user,
        action_permissions={"calculate": "budget.availability:read"},
        action_quotas={"calculate": "budget_management.api_reads"},
    )

    view.get_permissions()

    assert view.required_permission == "budget.availability:read"
    assert view.quota_resource == "budget_management.api_reads"


def test_get_permissions_prefers_action_over_permission_action_when_both_set():
    user = _User(None)
    view = _make_view(
        action="list",
        permission_action="calculate",
        user=user,
        action_permissions={"list": "budget.budget:read", "calculate": "budget.availability:read"},
        action_quotas={},
    )

    view.get_permissions()

    assert view.required_permission == "budget.budget:read"


def test_get_permissions_falsy_action_falls_back_to_permission_action():
    # action="" is falsy, so `str(getattr(self, "action", "") or ...)` must
    # fall through to permission_action rather than resolving to "".
    user = _User(None)
    view = _make_view(
        action="",
        permission_action="health",
        user=user,
        action_permissions={"health": "budget.health:read"},
        action_quotas={"health": "budget_management.api_reads"},
    )

    view.get_permissions()

    assert view.required_permission == "budget.health:read"


def test_get_permissions_neither_action_nor_permission_action_resolves_empty_string():
    user = _User(None)
    view = _make_view(user=user, action_permissions={"": "should-not-map"}, action_quotas={})

    view.get_permissions()

    # No action/permission_action set at all -> "" is looked up; ensure the
    # empty-string branch does not accidentally match a populated mapping
    # unless explicitly present (defensive: dict.get("") behaves normally).
    assert view.required_permission == "should-not-map"


def test_get_permissions_read_action_quota_branch_differs_from_write_action():
    """Read actions and write/mutating actions may map to different quota
    resources; verify both branches resolve independently and correctly."""
    user = _User(None)
    view = _make_view(
        action="create",
        user=user,
        action_permissions={
            "list": "budget.budget:read",
            "create": "budget.budget:create",
        },
        action_quotas={
            "list": "budget_management.api_reads",
            "create": "budget_management.api_writes",
        },
    )

    view.get_permissions()

    assert view.required_permission == "budget.budget:create"
    assert view.quota_resource == "budget_management.api_writes"

    # Now the read branch, same view class, different action.
    read_view = _make_view(
        action="list",
        user=user,
        action_permissions={
            "list": "budget.budget:read",
            "create": "budget.budget:create",
        },
        action_quotas={
            "list": "budget_management.api_reads",
            "create": "budget_management.api_writes",
        },
    )
    read_view.get_permissions()

    assert read_view.required_permission == "budget.budget:read"
    assert read_view.quota_resource == "budget_management.api_reads"


def test_get_permissions_default_action_permissions_and_quotas_are_empty_dicts():
    # Class-level defaults on BudgetAccessMixin itself, unsubclassed overrides.
    assert BudgetAccessMixin.action_permissions == {}
    assert BudgetAccessMixin.action_quotas == {}


# --- Fixed / pinned fields ------------------------------------------------------


def test_get_permissions_required_entitlement_is_always_module_budget_management():
    user = _User(None)
    view = _make_view(
        action="list",
        user=user,
        action_permissions={"list": "budget.budget:read"},
    )
    view.required_entitlement = "something-else-entirely"

    view.get_permissions()

    assert view.required_entitlement == "module.budget_management"


def test_get_permissions_quota_cost_is_always_exactly_one():
    user = _User(None)
    view = _make_view(action="list", user=user)

    view.get_permissions()

    assert view.quota_cost == 1


def test_class_level_required_entitlement_default_is_module_budget_management():
    assert BudgetAccessMixin.required_entitlement == "module.budget_management"


# --- Returned permission instances ----------------------------------------------


def test_get_permissions_returns_isauthenticated_and_requiresaccess_instances():
    user = _User(None)
    view = _make_view(action="list", user=user)

    result = view.get_permissions()

    assert len(result) == 2
    assert isinstance(result[0], IsAuthenticated)
    assert isinstance(result[1], RequiresAccess)


def test_get_permissions_returns_new_instances_on_each_call():
    user = _User(None)
    view = _make_view(action="list", user=user)

    first = view.get_permissions()
    second = view.get_permissions()

    assert first[0] is not second[0]
    assert first[1] is not second[1]


@pytest.mark.parametrize("action", ["list", "create", "unmapped-action", ""])
def test_get_permissions_always_returns_two_permission_instances(action):
    user = _User(None)
    view = _make_view(action=action, user=user)

    result = view.get_permissions()

    assert len(result) == 2


# --- PERMISSIONS registry: exact membership, order, and count -------------------


def test_permissions_registry_is_a_tuple():
    assert isinstance(PERMISSIONS, tuple)


def test_permissions_registry_exact_count():
    assert len(PERMISSIONS) == 17


def test_permissions_registry_exact_membership_and_order():
    assert PERMISSIONS == (
        "budget.budget:create",
        "budget.budget:read",
        "budget.budget:update",
        "budget.budget:delete",
        "budget.budget:submit",
        "budget.budget:approve",
        "budget.budget:close",
        "budget.budget_line:create",
        "budget.budget_line:read",
        "budget.budget_line:update",
        "budget.budget_line:delete",
        "budget.availability:read",
        "budget.actuals:sync",
        "budget.variance:read",
        "budget.variance:generate",
        "budget.variance:acknowledge",
        "budget.health:read",
    )


def test_permissions_registry_has_no_duplicate_entries():
    assert len(PERMISSIONS) == len(set(PERMISSIONS))


def test_permissions_registry_entries_are_namespaced_budget_dot():
    assert all(entry.startswith("budget.") for entry in PERMISSIONS)


def test_permissions_registry_entries_contain_exactly_one_colon():
    for entry in PERMISSIONS:
        assert entry.count(":") == 1


# --- __all__ / module exports ----------------------------------------------------


def test_module_exports_expected_public_names():
    from src.modules.budget_management import permissions as module

    assert set(module.__all__) == {"BudgetAccessMixin", "PERMISSIONS", "SessionAuthentication401"}
