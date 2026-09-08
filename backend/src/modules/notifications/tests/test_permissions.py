"""Direct unit tests for src/modules/notifications/permissions.py.

Covers the RBAC contract this module enforces independent of any single
ViewSet: the PERMISSIONS registry, the READ_ACTIONS classification, every
action-to-permission mapping table, the fail-closed identity/permission
resolution in NotificationActionAccessMixin.get_permissions(), and the
StrictSessionAuthentication challenge header.
"""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from rest_framework.permissions import BasePermission, IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.modules.notifications.permissions import (
    CONFIGURATION_ACTION_PERMISSIONS,
    DELIVERY_ACTION_PERMISSIONS,
    ENDPOINT_ACTION_PERMISSIONS,
    HEALTH_ACTION_PERMISSIONS,
    INBOX_ACTION_PERMISSIONS,
    PERMISSIONS,
    PREFERENCE_ACTION_PERMISSIONS,
    READ_ACTIONS,
    TEMPLATE_ACTION_PERMISSIONS,
    ConfigurationAccessMixin,
    DeliveryAccessMixin,
    EndpointAccessMixin,
    InboxAccessMixin,
    NotificationActionAccessMixin,
    PreferenceAccessMixin,
    StrictSessionAuthentication,
    TemplateAccessMixin,
)


# ---------------------------------------------------------------------------
# Registry contracts
# ---------------------------------------------------------------------------


def test_permissions_registry_contains_every_declared_action_permission():
    all_mapped = set()
    for table in (
        INBOX_ACTION_PERMISSIONS,
        TEMPLATE_ACTION_PERMISSIONS,
        DELIVERY_ACTION_PERMISSIONS,
        PREFERENCE_ACTION_PERMISSIONS,
        ENDPOINT_ACTION_PERMISSIONS,
        CONFIGURATION_ACTION_PERMISSIONS,
        HEALTH_ACTION_PERMISSIONS,
    ):
        all_mapped.update(table.values())

    assert all_mapped == set(PERMISSIONS)
    assert len(PERMISSIONS) == len(set(PERMISSIONS)), "PERMISSIONS must not contain duplicates"


def test_read_actions_classification_is_exact():
    assert READ_ACTIONS == frozenset(
        {
            "list",
            "retrieve",
            "unread_count",
            "versions",
            "attempts",
            "history",
            "export_document",
            "live",
            "ready",
        }
    )
    # Write-shaped actions must never be misclassified as reads.
    for write_action in ("create", "partial_update", "destroy", "bulk", "urgent", "retry", "cancel", "rollback"):
        assert write_action not in READ_ACTIONS


def test_inbox_action_permissions_exact_mapping():
    assert INBOX_ACTION_PERMISSIONS == {
        "list": "notifications.inbox:read",
        "retrieve": "notifications.inbox:read",
        "unread_count": "notifications.inbox:read",
        "mark_read": "notifications.inbox:update",
        "mark_unread": "notifications.inbox:update",
        "archive": "notifications.inbox:update",
        "mark_all_read": "notifications.inbox:update",
    }


def test_template_action_permissions_exact_mapping():
    assert TEMPLATE_ACTION_PERMISSIONS == {
        "list": "notifications.template:read",
        "retrieve": "notifications.template:read",
        "create": "notifications.template:create",
        "partial_update": "notifications.template:update",
        "destroy": "notifications.template:archive",
        "versions": "notifications.template:read",
        "create_version": "notifications.template:update",
        "preview": "notifications.template:read",
        "activate": "notifications.template:activate",
        "restore": "notifications.template:update",
        "rollback": "notifications.template:activate",
    }


def test_delivery_action_permissions_exact_mapping():
    assert DELIVERY_ACTION_PERMISSIONS == {
        "list": "notifications.delivery:read",
        "retrieve": "notifications.delivery:read",
        "attempts": "notifications.delivery:read",
        "create": "notifications.delivery:dispatch",
        "preview": "notifications.delivery:dispatch",
        "bulk": "notifications.delivery:dispatch_bulk",
        "urgent": "notifications.delivery:dispatch_urgent",
        "retry": "notifications.delivery:retry",
        "cancel": "notifications.delivery:cancel",
    }


def test_preference_action_permissions_exact_mapping():
    assert PREFERENCE_ACTION_PERMISSIONS == {
        "retrieve": "notifications.preference:read",
        "list": "notifications.preference:read",
        "update": "notifications.preference:update",
        "reset": "notifications.preference:update",
    }


def test_endpoint_action_permissions_exact_mapping():
    assert ENDPOINT_ACTION_PERMISSIONS == {
        "list": "notifications.endpoint:read",
        "retrieve": "notifications.endpoint:read",
        "create": "notifications.endpoint:create",
        "partial_update": "notifications.endpoint:update",
        "destroy": "notifications.endpoint:delete",
        "verify": "notifications.endpoint:verify",
        "rotate_secret_ref": "notifications.endpoint:update",
    }


def test_configuration_action_permissions_exact_mapping():
    assert CONFIGURATION_ACTION_PERMISSIONS == {
        "retrieve": "notifications.configuration:read",
        "partial_update": "notifications.configuration:update",
        "simulate": "notifications.configuration:update",
        "history": "notifications.configuration:read",
        "rollback": "notifications.configuration:rollback",
        "import_document": "notifications.configuration:import",
        "export_document": "notifications.configuration:export",
    }


def test_health_action_permissions_exact_mapping():
    assert HEALTH_ACTION_PERMISSIONS == {"ready": "notifications.health:read"}


# ---------------------------------------------------------------------------
# StrictSessionAuthentication
# ---------------------------------------------------------------------------


def test_strict_session_authentication_challenge_header_is_exactly_session():
    auth = StrictSessionAuthentication()
    assert auth.authenticate_header(request=object()) == "Session"
    # Must be robust to any request object, including None.
    assert auth.authenticate_header(None) == "Session"


# ---------------------------------------------------------------------------
# NotificationActionAccessMixin.get_permissions — class-level wiring
# ---------------------------------------------------------------------------


def test_mixin_base_declares_fail_closed_defaults():
    assert NotificationActionAccessMixin.authentication_classes == (StrictSessionAuthentication,)
    assert NotificationActionAccessMixin.permission_classes == (IsAuthenticated, RequiresAccess)
    assert NotificationActionAccessMixin.action_permissions == {}
    assert NotificationActionAccessMixin.action_entitlements == {}
    assert NotificationActionAccessMixin.action_quotas == {}
    assert NotificationActionAccessMixin.action_quota_costs == {}


@pytest.mark.parametrize(
    ("mixin_cls", "expected_table"),
    [
        (InboxAccessMixin, INBOX_ACTION_PERMISSIONS),
        (TemplateAccessMixin, TEMPLATE_ACTION_PERMISSIONS),
        (DeliveryAccessMixin, DELIVERY_ACTION_PERMISSIONS),
        (PreferenceAccessMixin, PREFERENCE_ACTION_PERMISSIONS),
        (EndpointAccessMixin, ENDPOINT_ACTION_PERMISSIONS),
        (ConfigurationAccessMixin, CONFIGURATION_ACTION_PERMISSIONS),
    ],
)
def test_each_mixin_binds_its_own_action_permission_table(mixin_cls, expected_table):
    assert mixin_cls.action_permissions == expected_table


def test_delivery_mixin_declares_entitlements_and_quotas():
    assert DeliveryAccessMixin.action_entitlements == {
        "create": "notifications.delivery",
        "preview": "notifications.delivery",
        "bulk": "notifications.delivery",
        "urgent": "notifications.delivery",
        "retry": "notifications.delivery",
        "cancel": "notifications.delivery",
    }
    assert DeliveryAccessMixin.action_quotas == {
        "bulk": "notifications.delivery.dispatch_bulk",
        "urgent": "notifications.delivery.dispatch_urgent",
    }


# ---------------------------------------------------------------------------
# get_permissions() — runtime decision logic
# ---------------------------------------------------------------------------


def _make_view(mixin_cls, *, action, user, request_extra=None):
    class View(mixin_cls):
        pass

    view = View()
    view.action = action
    request = SimpleNamespace(user=user)
    if request_extra:
        for key, value in request_extra.items():
            setattr(request, key, value)
    view.request = request
    return view


def test_get_permissions_returns_isauthenticated_and_requiresaccess_instances(monkeypatch):
    tenant_id = uuid4()
    monkeypatch.setattr(
        "src.modules.notifications.permissions.get_user_tenant_id",
        lambda user: str(tenant_id),
    )
    view = _make_view(InboxAccessMixin, action="list", user=SimpleNamespace(is_authenticated=True))

    result = view.get_permissions()

    assert len(result) == 2
    assert isinstance(result[0], IsAuthenticated)
    assert isinstance(result[1], RequiresAccess)
    for perm in result:
        assert isinstance(perm, BasePermission)


def test_get_permissions_maps_known_action_to_its_permission_string(monkeypatch):
    monkeypatch.setattr(
        "src.modules.notifications.permissions.get_user_tenant_id",
        lambda user: None,
    )
    view = _make_view(InboxAccessMixin, action="mark_read", user=SimpleNamespace(is_authenticated=True))

    view.get_permissions()

    assert view.required_permission == "notifications.inbox:update"


def test_get_permissions_unmapped_action_yields_none_permission_fail_closed(monkeypatch):
    """An action absent from the table must resolve to None, not a default allow."""
    monkeypatch.setattr(
        "src.modules.notifications.permissions.get_user_tenant_id",
        lambda user: None,
    )
    view = _make_view(InboxAccessMixin, action="totally_unknown_action", user=SimpleNamespace(is_authenticated=True))

    view.get_permissions()

    assert view.required_permission is None
    # With no explicit entitlement mapping, entitlement mirrors permission (also None).
    assert view.required_entitlement is None


def test_get_permissions_entitlement_defaults_to_permission_when_unmapped(monkeypatch):
    monkeypatch.setattr(
        "src.modules.notifications.permissions.get_user_tenant_id",
        lambda user: None,
    )
    view = _make_view(InboxAccessMixin, action="list", user=SimpleNamespace(is_authenticated=True))

    view.get_permissions()

    # InboxAccessMixin declares no action_entitlements, so entitlement must
    # fall back to exactly the resolved permission string.
    assert view.required_entitlement == "notifications.inbox:read"
    assert view.required_entitlement == view.required_permission


def test_get_permissions_entitlement_uses_explicit_mapping_when_present(monkeypatch):
    monkeypatch.setattr(
        "src.modules.notifications.permissions.get_user_tenant_id",
        lambda user: None,
    )
    view = _make_view(DeliveryAccessMixin, action="bulk", user=SimpleNamespace(is_authenticated=True))

    view.get_permissions()

    assert view.required_permission == "notifications.delivery:dispatch_bulk"
    # Distinct from permission: proves the entitlement table, not the
    # permission fallback, drove this value.
    assert view.required_entitlement == "notifications.delivery"
    assert view.required_entitlement != view.required_permission


@pytest.mark.parametrize("read_action", sorted(READ_ACTIONS))
def test_get_permissions_read_action_uses_read_quota_resource(monkeypatch, read_action):
    monkeypatch.setattr(
        "src.modules.notifications.permissions.get_user_tenant_id",
        lambda user: None,
    )
    view = _make_view(InboxAccessMixin, action=read_action, user=SimpleNamespace(is_authenticated=True))

    view.get_permissions()

    assert view.quota_resource == "notifications.api_reads"


def test_get_permissions_write_action_uses_write_quota_resource(monkeypatch):
    monkeypatch.setattr(
        "src.modules.notifications.permissions.get_user_tenant_id",
        lambda user: None,
    )
    view = _make_view(InboxAccessMixin, action="mark_read", user=SimpleNamespace(is_authenticated=True))

    view.get_permissions()

    assert view.quota_resource == "notifications.api_writes"


def test_get_permissions_explicit_quota_resource_overrides_read_write_default(monkeypatch):
    monkeypatch.setattr(
        "src.modules.notifications.permissions.get_user_tenant_id",
        lambda user: None,
    )
    view = _make_view(DeliveryAccessMixin, action="urgent", user=SimpleNamespace(is_authenticated=True))

    view.get_permissions()

    # "urgent" is not in READ_ACTIONS, so the default would be api_writes;
    # the explicit action_quotas entry must win instead.
    assert view.quota_resource == "notifications.delivery.dispatch_urgent"


def test_get_permissions_quota_cost_defaults_to_one(monkeypatch):
    monkeypatch.setattr(
        "src.modules.notifications.permissions.get_user_tenant_id",
        lambda user: None,
    )
    view = _make_view(InboxAccessMixin, action="list", user=SimpleNamespace(is_authenticated=True))

    view.get_permissions()

    assert view.quota_cost == 1


def test_get_permissions_quota_cost_uses_explicit_override():
    class CostlyMixin(InboxAccessMixin):
        action_quota_costs = {"list": 7}

    view = _make_view(CostlyMixin, action="list", user=SimpleNamespace(is_authenticated=True))

    view.get_permissions()

    assert view.quota_cost == 7


def test_get_permissions_valid_tenant_is_parsed_to_uuid_on_request(monkeypatch):
    tenant_id = uuid4()
    monkeypatch.setattr(
        "src.modules.notifications.permissions.get_user_tenant_id",
        lambda user: str(tenant_id),
    )
    view = _make_view(InboxAccessMixin, action="list", user=SimpleNamespace(is_authenticated=True))

    view.get_permissions()

    assert view.request.tenant_id == tenant_id
    assert isinstance(view.request.tenant_id, UUID)


def test_get_permissions_missing_tenant_sets_none_without_raising(monkeypatch):
    monkeypatch.setattr(
        "src.modules.notifications.permissions.get_user_tenant_id",
        lambda user: None,
    )
    view = _make_view(InboxAccessMixin, action="list", user=SimpleNamespace(is_authenticated=True))

    # Must not raise — fail-closed behavior is enforced by RequiresAccess
    # downstream, not by blowing up here.
    view.get_permissions()

    assert view.request.tenant_id is None


def test_get_permissions_malformed_tenant_string_sets_none_without_raising(monkeypatch):
    monkeypatch.setattr(
        "src.modules.notifications.permissions.get_user_tenant_id",
        lambda user: "not-a-valid-uuid",
    )
    view = _make_view(InboxAccessMixin, action="list", user=SimpleNamespace(is_authenticated=True))

    view.get_permissions()

    assert view.request.tenant_id is None


def test_get_permissions_empty_string_tenant_treated_as_falsy_none(monkeypatch):
    monkeypatch.setattr(
        "src.modules.notifications.permissions.get_user_tenant_id",
        lambda user: "",
    )
    view = _make_view(InboxAccessMixin, action="list", user=SimpleNamespace(is_authenticated=True))

    view.get_permissions()

    assert view.request.tenant_id is None


def test_get_permissions_stringifies_non_string_action():
    """action may be a DRF-internal sentinel; getattr default must stringify to ''."""

    class Bare(InboxAccessMixin):
        pass

    view = Bare()
    # No `action` attribute set at all — exercises the getattr(..., "") default.
    view.request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))

    view.get_permissions()

    assert view.required_permission is None
