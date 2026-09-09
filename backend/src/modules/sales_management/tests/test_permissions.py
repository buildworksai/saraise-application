"""Direct unit tests for src/modules/sales_management/permissions.py.

Covers the RBAC contract this module enforces independent of any single
ViewSet: the PERMISSIONS / SOD_ACTIONS registries, every declared action
constant, the fail-closed identity/tenant resolution and the
"unimplemented action" 405-not-403 carve-out in
SalesAccessMixin.get_permissions(), and the SalesSessionAuthentication
challenge header.
"""

from types import SimpleNamespace
from uuid import UUID, uuid4

from rest_framework.permissions import BasePermission, IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.modules.sales_management import permissions as perm_module
from src.modules.sales_management.permissions import (
    CONFIG_EXPORT,
    CONFIG_IMPORT,
    CONFIG_READ,
    CONFIG_ROLLBACK,
    CONFIG_UPDATE,
    CUSTOMER_CREATE,
    CUSTOMER_DELETE,
    CUSTOMER_READ,
    CUSTOMER_UPDATE,
    DELIVERY_CANCEL,
    DELIVERY_COMPLETE,
    DELIVERY_CREATE,
    DELIVERY_DELETE,
    DELIVERY_READ,
    DELIVERY_UPDATE,
    ENTITLEMENT,
    ORDER_CANCEL,
    ORDER_CONFIRM,
    ORDER_CREATE,
    ORDER_DELETE,
    ORDER_FULFILL,
    ORDER_INVOICE,
    ORDER_READ,
    ORDER_UPDATE,
    PERMISSIONS,
    PRICING_OVERRIDE,
    QUOTATION_ACCEPT,
    QUOTATION_CONVERT,
    QUOTATION_CREATE,
    QUOTATION_DELETE,
    QUOTATION_READ,
    QUOTATION_REJECT,
    QUOTATION_SEND,
    QUOTATION_UPDATE,
    SOD_ACTIONS,
    SalesAccessMixin,
    SalesSessionAuthentication,
)

# ---------------------------------------------------------------------------
# Constant values — pinned exactly, not just membership
# ---------------------------------------------------------------------------


def test_entitlement_constant_value():
    assert ENTITLEMENT == "sales_management"


def test_action_constant_values_are_pinned_exactly():
    assert CUSTOMER_CREATE == "sales.customer:create"
    assert CUSTOMER_READ == "sales.customer:read"
    assert CUSTOMER_UPDATE == "sales.customer:update"
    assert CUSTOMER_DELETE == "sales.customer:delete"
    assert QUOTATION_CREATE == "sales.quotation:create"
    assert QUOTATION_READ == "sales.quotation:read"
    assert QUOTATION_UPDATE == "sales.quotation:update"
    assert QUOTATION_DELETE == "sales.quotation:delete"
    assert QUOTATION_SEND == "sales.quotation:send"
    assert QUOTATION_ACCEPT == "sales.quotation:accept"
    assert QUOTATION_REJECT == "sales.quotation:reject"
    assert QUOTATION_CONVERT == "sales.quotation:convert"
    assert ORDER_CREATE == "sales.sales_order:create"
    assert ORDER_READ == "sales.sales_order:read"
    assert ORDER_UPDATE == "sales.sales_order:update"
    assert ORDER_DELETE == "sales.sales_order:delete"
    assert ORDER_CONFIRM == "sales.sales_order:confirm"
    assert ORDER_FULFILL == "sales.sales_order:fulfill"
    assert ORDER_CANCEL == "sales.sales_order:cancel"
    assert ORDER_INVOICE == "sales.sales_order:invoice"
    assert DELIVERY_CREATE == "sales.delivery_note:create"
    assert DELIVERY_READ == "sales.delivery_note:read"
    assert DELIVERY_UPDATE == "sales.delivery_note:update"
    assert DELIVERY_DELETE == "sales.delivery_note:delete"
    assert DELIVERY_COMPLETE == "sales.delivery_note:complete"
    assert DELIVERY_CANCEL == "sales.delivery_note:cancel"
    assert PRICING_OVERRIDE == "sales.pricing:override"
    assert CONFIG_READ == "sales.configuration:read"
    assert CONFIG_UPDATE == "sales.configuration:update"
    assert CONFIG_ROLLBACK == "sales.configuration:rollback"
    assert CONFIG_IMPORT == "sales.configuration:import"
    assert CONFIG_EXPORT == "sales.configuration:export"


def test_permissions_registry_is_exactly_every_sales_dot_prefixed_constant():
    expected = {
        CUSTOMER_CREATE,
        CUSTOMER_READ,
        CUSTOMER_UPDATE,
        CUSTOMER_DELETE,
        QUOTATION_CREATE,
        QUOTATION_READ,
        QUOTATION_UPDATE,
        QUOTATION_DELETE,
        QUOTATION_SEND,
        QUOTATION_ACCEPT,
        QUOTATION_REJECT,
        QUOTATION_CONVERT,
        ORDER_CREATE,
        ORDER_READ,
        ORDER_UPDATE,
        ORDER_DELETE,
        ORDER_CONFIRM,
        ORDER_FULFILL,
        ORDER_CANCEL,
        ORDER_INVOICE,
        DELIVERY_CREATE,
        DELIVERY_READ,
        DELIVERY_UPDATE,
        DELIVERY_DELETE,
        DELIVERY_COMPLETE,
        DELIVERY_CANCEL,
        PRICING_OVERRIDE,
        CONFIG_READ,
        CONFIG_UPDATE,
        CONFIG_ROLLBACK,
        CONFIG_IMPORT,
        CONFIG_EXPORT,
    }
    assert set(PERMISSIONS) == expected
    assert len(PERMISSIONS) == len(set(PERMISSIONS)), "PERMISSIONS must not contain duplicates"
    # ENTITLEMENT does not start with "sales." and must never leak into the registry.
    assert ENTITLEMENT not in PERMISSIONS


def test_sod_actions_is_exactly_order_create_and_delivery_create():
    assert SOD_ACTIONS == (ORDER_CREATE, DELIVERY_CREATE)
    assert len(SOD_ACTIONS) == 2


def test_all_exports_every_declared_permission_constant_and_public_names():
    assert "SalesAccessMixin" in perm_module.__all__
    assert "SalesSessionAuthentication" in perm_module.__all__
    assert "PERMISSIONS" in perm_module.__all__
    assert "SOD_ACTIONS" in perm_module.__all__
    for value in PERMISSIONS:
        # every action constant string must be reachable via __all__'s name list
        assert value in perm_module.__all__ or any(
            getattr(perm_module, name, None) == value for name in perm_module.__all__
        )
    assert "ENTITLEMENT" in perm_module.__all__


# ---------------------------------------------------------------------------
# SalesSessionAuthentication
# ---------------------------------------------------------------------------


def test_authenticate_header_is_exactly_session_regardless_of_request():
    auth = SalesSessionAuthentication()
    assert auth.authenticate_header(request=object()) == "Session"
    assert auth.authenticate_header(None) == "Session"
    assert auth.authenticate_header("anything") == "Session"


# ---------------------------------------------------------------------------
# SalesAccessMixin — class-level wiring
# ---------------------------------------------------------------------------


def test_mixin_declares_fail_closed_defaults():
    assert SalesAccessMixin.authentication_classes == (SalesSessionAuthentication,)
    assert SalesAccessMixin.permission_classes == (IsAuthenticated, RequiresAccess)
    assert SalesAccessMixin.required_entitlement == ENTITLEMENT
    assert SalesAccessMixin.action_permissions == {}


# ---------------------------------------------------------------------------
# get_permissions() — runtime decision logic
# ---------------------------------------------------------------------------


def _make_view(mixin_cls, *, action, user, implemented_actions=()):
    """Build a view instance with the given action and no other handlers,
    except methods named in ``implemented_actions`` (so the "does this view
    actually implement this handler" callable-check can be exercised both
    ways)."""

    attrs = {name: (lambda self: None) for name in implemented_actions}
    View = type("View", (mixin_cls,), attrs)

    view = View()
    view.action = action
    view.request = SimpleNamespace(user=user)
    return view


def test_get_permissions_returns_isauthenticated_and_requiresaccess_for_implemented_action(monkeypatch):
    tenant_id = uuid4()
    monkeypatch.setattr(
        "src.modules.sales_management.permissions.get_user_tenant_id",
        lambda user: str(tenant_id),
    )
    view = _make_view(
        SalesAccessMixin,
        action="list",
        user=SimpleNamespace(is_authenticated=True),
        implemented_actions=("list",),
    )

    result = view.get_permissions()

    assert len(result) == 2
    assert isinstance(result[0], IsAuthenticated)
    assert isinstance(result[1], RequiresAccess)
    for perm in result:
        assert isinstance(perm, BasePermission)


def test_get_permissions_maps_known_action_to_its_permission_string(monkeypatch):
    monkeypatch.setattr(
        "src.modules.sales_management.permissions.get_user_tenant_id",
        lambda user: None,
    )

    class CustomerMixin(SalesAccessMixin):
        action_permissions = {"create": CUSTOMER_CREATE}

        def create(self):
            return None

    view = CustomerMixin()
    view.action = "create"
    view.request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))

    view.get_permissions()

    assert view.required_permission == CUSTOMER_CREATE
    assert view.quota_resource == "sales.api.requests"
    assert view.quota_cost == 1


def test_get_permissions_unmapped_but_implemented_action_yields_none_permission_fail_closed(monkeypatch):
    """An implemented action absent from action_permissions resolves to None,
    not a default allow — and quota_resource must follow it to None."""
    monkeypatch.setattr(
        "src.modules.sales_management.permissions.get_user_tenant_id",
        lambda user: None,
    )
    view = _make_view(
        SalesAccessMixin,
        action="list",
        user=SimpleNamespace(is_authenticated=True),
        implemented_actions=("list",),
    )

    view.get_permissions()

    assert view.required_permission is None
    assert view.quota_resource is None
    assert view.quota_cost == 1


def test_get_permissions_unimplemented_action_short_circuits_to_isauthenticated_only(monkeypatch):
    """DRF's router can assign an action name the ViewSet never implements
    (e.g. `update` for PUT on a narrow ViewSet). That must yield exactly
    [IsAuthenticated()] without ever consulting action_permissions, so a
    protocol 405 isn't masked as a 403."""
    monkeypatch.setattr(
        "src.modules.sales_management.permissions.get_user_tenant_id",
        lambda user: None,
    )

    class NarrowMixin(SalesAccessMixin):
        action_permissions = {"update": CUSTOMER_UPDATE}
        # deliberately does NOT implement `update`

    view = NarrowMixin()
    view.action = "update"
    view.request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))

    result = view.get_permissions()

    assert len(result) == 1
    assert isinstance(result[0], IsAuthenticated)
    assert view.required_permission is None
    assert view.quota_resource is None
    assert view.quota_cost == 0


def test_get_permissions_empty_action_name_skips_unimplemented_short_circuit(monkeypatch):
    """When no action is set at all, action_name stringifies to "" which is
    falsy, so the "not callable" branch must be skipped entirely (an empty
    string is never a callable attribute name worth checking) and the normal
    resolution path runs."""
    monkeypatch.setattr(
        "src.modules.sales_management.permissions.get_user_tenant_id",
        lambda user: None,
    )

    class Bare(SalesAccessMixin):
        pass

    view = Bare()
    # No `action` attribute set — exercises getattr(self, "action", "") default.
    view.request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))

    result = view.get_permissions()

    assert len(result) == 2
    assert isinstance(result[0], IsAuthenticated)
    assert isinstance(result[1], RequiresAccess)
    assert view.required_permission is None
    assert view.quota_resource is None
    assert view.quota_cost == 1


def test_get_permissions_valid_tenant_is_parsed_to_uuid_on_request(monkeypatch):
    tenant_id = uuid4()
    monkeypatch.setattr(
        "src.modules.sales_management.permissions.get_user_tenant_id",
        lambda user: str(tenant_id),
    )
    view = _make_view(
        SalesAccessMixin,
        action="list",
        user=SimpleNamespace(is_authenticated=True),
        implemented_actions=("list",),
    )

    view.get_permissions()

    assert view.request.tenant_id == tenant_id
    assert isinstance(view.request.tenant_id, UUID)


def test_get_permissions_uuid_tenant_object_is_preserved(monkeypatch):
    """get_user_tenant_id may itself return a UUID instance (not a str);
    str(raw_tenant) must still round-trip to the same UUID."""
    tenant_id = uuid4()
    monkeypatch.setattr(
        "src.modules.sales_management.permissions.get_user_tenant_id",
        lambda user: tenant_id,
    )
    view = _make_view(
        SalesAccessMixin,
        action="list",
        user=SimpleNamespace(is_authenticated=True),
        implemented_actions=("list",),
    )

    view.get_permissions()

    assert view.request.tenant_id == tenant_id


def test_get_permissions_missing_tenant_sets_none_without_raising(monkeypatch):
    monkeypatch.setattr(
        "src.modules.sales_management.permissions.get_user_tenant_id",
        lambda user: None,
    )
    view = _make_view(
        SalesAccessMixin,
        action="list",
        user=SimpleNamespace(is_authenticated=True),
        implemented_actions=("list",),
    )

    # Must not raise — fail-closed behavior is enforced by RequiresAccess
    # downstream, not by blowing up here.
    view.get_permissions()

    assert view.request.tenant_id is None


def test_get_permissions_malformed_tenant_string_sets_none_without_raising(monkeypatch):
    monkeypatch.setattr(
        "src.modules.sales_management.permissions.get_user_tenant_id",
        lambda user: "not-a-valid-uuid",
    )
    view = _make_view(
        SalesAccessMixin,
        action="list",
        user=SimpleNamespace(is_authenticated=True),
        implemented_actions=("list",),
    )

    view.get_permissions()

    assert view.request.tenant_id is None


def test_get_permissions_empty_string_tenant_treated_as_falsy_none(monkeypatch):
    monkeypatch.setattr(
        "src.modules.sales_management.permissions.get_user_tenant_id",
        lambda user: "",
    )
    view = _make_view(
        SalesAccessMixin,
        action="list",
        user=SimpleNamespace(is_authenticated=True),
        implemented_actions=("list",),
    )

    view.get_permissions()

    assert view.request.tenant_id is None


def test_get_permissions_no_user_attribute_on_request_is_handled(monkeypatch):
    """getattr(self.request, "user", None) must degrade to None rather than
    raising AttributeError when the request has no user at all."""
    monkeypatch.setattr(
        "src.modules.sales_management.permissions.get_user_tenant_id",
        lambda user: None,
    )
    view = _make_view(
        SalesAccessMixin,
        action="list",
        user=None,
        implemented_actions=("list",),
    )
    view.request = SimpleNamespace()  # no `user` attribute at all

    result = view.get_permissions()

    assert view.request.tenant_id is None
    assert len(result) == 2


def test_get_permissions_quota_cost_is_always_one_for_implemented_actions(monkeypatch):
    monkeypatch.setattr(
        "src.modules.sales_management.permissions.get_user_tenant_id",
        lambda user: None,
    )
    view = _make_view(
        SalesAccessMixin,
        action="list",
        user=SimpleNamespace(is_authenticated=True),
        implemented_actions=("list",),
    )

    view.get_permissions()

    assert view.quota_cost == 1
