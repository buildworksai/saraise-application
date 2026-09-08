"""Tests for accounting_finance deny-by-default authorization primitives."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.modules.accounting_finance.permissions import (
    PERMISSIONS,
    AccountingAccessMixin,
    IsAccountingUser,
    SessionAuthentication401,
)


class TestPermissionsRegistry:
    def test_permissions_is_nonempty_tuple(self) -> None:
        assert isinstance(PERMISSIONS, tuple)
        assert len(PERMISSIONS) == 32

    def test_permissions_are_unique(self) -> None:
        assert len(set(PERMISSIONS)) == len(PERMISSIONS)

    def test_every_permission_has_resource_and_action(self) -> None:
        for perm in PERMISSIONS:
            assert perm.startswith("accounting.")
            resource, _, action = perm.partition(":")
            assert resource
            assert action

    def test_permissions_contains_expected_entries(self) -> None:
        expected = {
            "accounting.account:create",
            "accounting.account:read",
            "accounting.account:update",
            "accounting.account:delete",
            "accounting.posting_period:create",
            "accounting.posting_period:read",
            "accounting.posting_period:update",
            "accounting.posting_period:close",
            "accounting.posting_period:lock",
            "accounting.journal_entry:create",
            "accounting.journal_entry:read",
            "accounting.journal_entry:update",
            "accounting.journal_entry:delete",
            "accounting.journal_entry:post",
            "accounting.journal_entry:reverse",
            "accounting.journal_entry:import",
            "accounting.ap_invoice:create",
            "accounting.ap_invoice:read",
            "accounting.ap_invoice:update",
            "accounting.ap_invoice:delete",
            "accounting.ap_invoice:approve",
            "accounting.ap_invoice:post",
            "accounting.ar_invoice:create",
            "accounting.ar_invoice:read",
            "accounting.ar_invoice:update",
            "accounting.ar_invoice:delete",
            "accounting.ar_invoice:post",
            "accounting.payment:create",
            "accounting.payment:read",
            "accounting.payment:update",
            "accounting.payment:void",
            "accounting.report:read",
        }
        assert set(PERMISSIONS) == expected

    def test_report_read_present_but_no_report_write_actions(self) -> None:
        report_perms = [p for p in PERMISSIONS if p.startswith("accounting.report:")]
        assert report_perms == ["accounting.report:read"]

    def test_payment_has_no_delete_only_void(self) -> None:
        payment_perms = {p for p in PERMISSIONS if p.startswith("accounting.payment:")}
        assert "accounting.payment:delete" not in payment_perms
        assert "accounting.payment:void" in payment_perms

    def test_ar_invoice_has_no_approve_action(self) -> None:
        ar_perms = {p for p in PERMISSIONS if p.startswith("accounting.ar_invoice:")}
        assert "accounting.ar_invoice:approve" not in ar_perms
        assert "accounting.ar_invoice:post" in ar_perms


class TestSessionAuthentication401:
    def test_is_session_authentication_subclass(self) -> None:
        from rest_framework.authentication import SessionAuthentication

        assert issubclass(SessionAuthentication401, SessionAuthentication)

    def test_authenticate_header_returns_session_challenge(self) -> None:
        auth = SessionAuthentication401()
        assert auth.authenticate_header(request=object()) == "Session"

    def test_authenticate_header_ignores_request_argument(self) -> None:
        auth = SessionAuthentication401()
        # Passing very different request-like objects must not change the result.
        assert auth.authenticate_header(SimpleNamespace(user=None)) == "Session"
        assert auth.authenticate_header(None) == "Session"


class TestIsAccountingUser:
    def test_is_authenticated_subclass(self) -> None:
        assert issubclass(IsAccountingUser, IsAuthenticated)


def _make_view(*, user=None, action="", action_permissions=None, action_quotas=None):
    view = AccountingAccessMixin()
    view.request = SimpleNamespace(user=user)
    view.action = action
    if action_permissions is not None:
        view.action_permissions = action_permissions
    if action_quotas is not None:
        view.action_quotas = action_quotas
    return view


class TestAccountingAccessMixinGetPermissions:
    def test_class_level_defaults(self) -> None:
        assert AccountingAccessMixin.authentication_classes == (SessionAuthentication401,)
        assert AccountingAccessMixin.permission_classes == (IsAuthenticated, RequiresAccess)
        assert AccountingAccessMixin.action_permissions == {}
        assert AccountingAccessMixin.action_quotas == {}
        assert AccountingAccessMixin.entitlement == "accounting_finance"

    def test_returns_two_permission_instances_of_correct_types(self) -> None:
        view = _make_view(user=None)
        perms = view.get_permissions()
        assert isinstance(perms, list)
        assert len(perms) == 2
        assert isinstance(perms[0], IsAuthenticated)
        assert isinstance(perms[1], RequiresAccess)

    def test_no_user_attribute_defaults_tenant_to_none(self) -> None:
        # request has no `user` attribute at all -> getattr default kicks in.
        view = AccountingAccessMixin()
        view.request = SimpleNamespace()
        view.action = "list"
        view.get_permissions()
        assert view.request.tenant_id is None

    def test_user_with_no_profile_sets_tenant_none(self) -> None:
        user = SimpleNamespace()  # no `.profile` attribute -> AttributeError path
        view = _make_view(user=user)
        view.get_permissions()
        assert view.request.tenant_id is None

    def test_valid_tenant_uuid_string_is_parsed(self) -> None:
        tenant_uuid = UUID("12345678-1234-5678-1234-567812345678")
        user = SimpleNamespace(profile=SimpleNamespace(tenant_id=str(tenant_uuid)))
        view = _make_view(user=user)
        view.get_permissions()
        assert view.request.tenant_id == tenant_uuid
        assert isinstance(view.request.tenant_id, UUID)

    def test_valid_tenant_uuid_object_is_parsed(self) -> None:
        tenant_uuid = UUID("87654321-4321-8765-4321-876543218765")
        user = SimpleNamespace(profile=SimpleNamespace(tenant_id=tenant_uuid))
        view = _make_view(user=user)
        view.get_permissions()
        assert view.request.tenant_id == tenant_uuid

    def test_invalid_tenant_string_falls_back_to_none(self) -> None:
        user = SimpleNamespace(profile=SimpleNamespace(tenant_id="not-a-uuid"))
        view = _make_view(user=user)
        view.get_permissions()
        assert view.request.tenant_id is None

    def test_empty_string_tenant_is_falsy_and_stays_none(self) -> None:
        # Empty string is falsy, so `UUID(str(tenant)) if tenant else None` takes
        # the None branch rather than raising inside the try (which would also
        # resolve to None, but this exercises the truthy/falsy branch directly).
        user = SimpleNamespace(profile=SimpleNamespace(tenant_id=""))
        view = _make_view(user=user)
        view.get_permissions()
        assert view.request.tenant_id is None

    def test_none_tenant_sets_none(self) -> None:
        user = SimpleNamespace(profile=SimpleNamespace(tenant_id=None))
        view = _make_view(user=user)
        view.get_permissions()
        assert view.request.tenant_id is None

    def test_required_permission_resolved_from_action_permissions(self) -> None:
        user = SimpleNamespace(profile=SimpleNamespace(tenant_id=None))
        view = _make_view(
            user=user,
            action="create",
            action_permissions={"create": "accounting.account:create"},
        )
        view.get_permissions()
        assert view.required_permission == "accounting.account:create"

    def test_required_permission_none_for_unmapped_action(self) -> None:
        user = SimpleNamespace(profile=SimpleNamespace(tenant_id=None))
        view = _make_view(
            user=user,
            action="destroy",
            action_permissions={"create": "accounting.account:create"},
        )
        view.get_permissions()
        assert view.required_permission is None

    def test_action_defaults_to_empty_string_when_missing(self) -> None:
        # No `action` attribute set on the view at all (getattr default "").
        view = AccountingAccessMixin()
        view.request = SimpleNamespace(user=None)
        view.get_permissions()
        assert view.required_permission is None  # class-level action_permissions is {}

    def test_action_defaults_map_empty_string_when_registered(self) -> None:
        # Confirms the literal default value used by getattr(self, "action", "")
        # is the empty string, not None or some other sentinel.
        view = AccountingAccessMixin()
        view.request = SimpleNamespace(user=None)
        view.action_permissions = {"": "empty-action-permission"}
        view.get_permissions()
        assert view.required_permission == "empty-action-permission"

    def test_action_is_stringified(self) -> None:
        user = SimpleNamespace(profile=SimpleNamespace(tenant_id=None))
        view = _make_view(
            user=user,
            action=None,
            action_permissions={"None": "matched-string-none"},
        )
        view.get_permissions()
        # str(None) == "None" must be used as the lookup key.
        assert view.required_permission == "matched-string-none"

    def test_required_entitlement_matches_instance_entitlement(self) -> None:
        user = SimpleNamespace(profile=SimpleNamespace(tenant_id=None))
        view = _make_view(user=user, action="list")
        view.entitlement = "custom_entitlement"
        view.get_permissions()
        assert view.required_entitlement == "custom_entitlement"

    def test_required_entitlement_defaults_to_accounting_finance(self) -> None:
        user = SimpleNamespace(profile=SimpleNamespace(tenant_id=None))
        view = _make_view(user=user, action="list")
        view.get_permissions()
        assert view.required_entitlement == "accounting_finance"

    def test_quota_resource_resolved_from_action_quotas(self) -> None:
        user = SimpleNamespace(profile=SimpleNamespace(tenant_id=None))
        view = _make_view(
            user=user,
            action="post",
            action_quotas={"post": "journal_entry_posts"},
        )
        view.get_permissions()
        assert view.quota_resource == "journal_entry_posts"

    def test_quota_resource_none_for_read_actions_by_default(self) -> None:
        user = SimpleNamespace(profile=SimpleNamespace(tenant_id=None))
        view = _make_view(user=user, action="list")
        view.get_permissions()
        assert view.quota_resource is None

    def test_quota_cost_is_always_one(self) -> None:
        user = SimpleNamespace(profile=SimpleNamespace(tenant_id=None))
        view = _make_view(
            user=user,
            action="post",
            action_quotas={"post": "journal_entry_posts"},
        )
        view.get_permissions()
        assert view.quota_cost == 1

    def test_type_error_on_tenant_conversion_is_caught(self) -> None:
        # A tenant value that is truthy but raises TypeError inside UUID(str(...))
        # is not realistically producible via str(), but a non-hex truthy string
        # exercises the ValueError branch of the except clause explicitly.
        user = SimpleNamespace(profile=SimpleNamespace(tenant_id="zzzz-not-hex"))
        view = _make_view(user=user)
        view.get_permissions()
        assert view.request.tenant_id is None


@pytest.mark.parametrize(
    "action,expected_permission",
    [
        ("create", "accounting.account:create"),
        ("update", "accounting.account:update"),
        ("destroy", None),
    ],
)
def test_get_permissions_action_mapping_parametrized(action, expected_permission) -> None:
    user = SimpleNamespace(profile=SimpleNamespace(tenant_id=None))
    view = _make_view(
        user=user,
        action=action,
        action_permissions={
            "create": "accounting.account:create",
            "update": "accounting.account:update",
        },
    )
    view.get_permissions()
    assert view.required_permission == expected_permission


def test_module_all_exports() -> None:
    from src.modules.accounting_finance import permissions as perms_module

    assert set(perms_module.__all__) == {
        "AccountingAccessMixin",
        "IsAccountingUser",
        "PERMISSIONS",
        "SessionAuthentication401",
    }
