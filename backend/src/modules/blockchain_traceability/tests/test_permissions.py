"""Unit tests for the fail-closed access declarations in permissions.py."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from src.modules.blockchain_traceability import permissions as permissions_module
from src.modules.blockchain_traceability.permissions import (
    ANCHOR_VERIFY,
    ASSET_READ,
    COMPLIANCE_CREATE,
    COMPLIANCE_FINALIZE,
    CONFIG_ROLLBACK,
    CONFIG_UPDATE,
    CREDENTIAL_ISSUE,
    CREDENTIAL_REVOKE,
    NETWORK_MANAGE,
    PERMISSIONS,
    SOD_ACTIONS,
    ActionAccessMixin,
    SessionAuthentication401,
)


class _PermissionsBase:
    """Stand-in for DRF's APIView.get_permissions, capturing what it returns."""

    permission_classes: tuple = ()

    def get_permissions(self):  # noqa: D401 - trivial stub
        return ["sentinel-permission"]


class _View(ActionAccessMixin, _PermissionsBase):
    """Minimal concrete view combining the mixin with a real get_permissions."""


def _make_request(*, user=None, method: str = "get"):
    return SimpleNamespace(user=user, method=method)


class TestSessionAuthentication401:
    def test_authenticate_header_returns_session_regardless_of_request(self):
        auth = SessionAuthentication401()
        assert auth.authenticate_header(None) == "Session"

    def test_authenticate_header_ignores_request_contents(self):
        auth = SessionAuthentication401()
        sentinel_request = SimpleNamespace(some="thing")
        assert auth.authenticate_header(sentinel_request) == "Session"


class TestActionAccessMixinTenantCoercion:
    def test_valid_tenant_id_is_coerced_to_uuid(self, monkeypatch):
        tenant_uuid = uuid4()
        monkeypatch.setattr(
            permissions_module, "get_user_tenant_id", lambda user: str(tenant_uuid)
        )
        view = _View()
        view.action = "retrieve"
        view.http_method_names = ("get",)
        view.request = _make_request(method="get")

        view.get_permissions()

        assert view.request.tenant_id == tenant_uuid
        assert isinstance(view.request.tenant_id, UUID)

    def test_none_tenant_id_leaves_request_tenant_id_none(self, monkeypatch):
        monkeypatch.setattr(permissions_module, "get_user_tenant_id", lambda user: None)
        view = _View()
        view.action = "retrieve"
        view.http_method_names = ("get",)
        view.request = _make_request(method="get")

        view.get_permissions()

        assert view.request.tenant_id is None

    def test_invalid_tenant_id_fails_closed_to_none(self, monkeypatch):
        # Truthy but not a valid UUID string -> UUID() raises ValueError.
        monkeypatch.setattr(
            permissions_module, "get_user_tenant_id", lambda user: "not-a-uuid"
        )
        view = _View()
        view.action = "retrieve"
        view.http_method_names = ("get",)
        view.request = _make_request(method="get")

        view.get_permissions()

        assert view.request.tenant_id is None

    def test_non_string_truthy_tenant_id_that_fails_uuid_parsing_fails_closed(
        self, monkeypatch
    ):
        # Truthy int whose str() is not a valid UUID -> ValueError caught.
        monkeypatch.setattr(permissions_module, "get_user_tenant_id", lambda user: 12345)
        view = _View()
        view.action = "retrieve"
        view.http_method_names = ("get",)
        view.request = _make_request(method="get")

        view.get_permissions()

        assert view.request.tenant_id is None


class TestActionAccessMixinPermissionResolution:
    def setup_method(self):
        # get_user_tenant_id must be importable/callable; default to None tenant
        # for tests that don't care about tenant coercion.
        pass

    def _view_with_tenant(self, monkeypatch, tenant_id=None):
        monkeypatch.setattr(
            permissions_module, "get_user_tenant_id", lambda user: tenant_id
        )
        return _View()

    def test_known_action_resolves_declared_permission(self, monkeypatch):
        view = self._view_with_tenant(monkeypatch)
        view.action = "retrieve"
        view.action_permissions = {"retrieve": ASSET_READ}
        view.http_method_names = ("get",)
        view.request = _make_request(method="get")

        view.get_permissions()

        assert view.required_permission == ASSET_READ
        assert view.required_entitlement == ASSET_READ

    def test_unmapped_action_with_disallowed_method_falls_back_to_unsupported(
        self, monkeypatch
    ):
        view = self._view_with_tenant(monkeypatch)
        view.action = "destroy"
        view.action_permissions = {}
        view.unsupported_method_permission = "blockchain_traceability.asset:delete"
        view.http_method_names = ("get", "post")
        view.request = _make_request(method="delete")

        view.get_permissions()

        assert view.required_permission == "blockchain_traceability.asset:delete"

    def test_unmapped_action_with_allowed_method_leaves_permission_none(
        self, monkeypatch
    ):
        view = self._view_with_tenant(monkeypatch)
        view.action = "custom_action"
        view.action_permissions = {}
        view.unsupported_method_permission = "should-not-be-used"
        view.http_method_names = ("get", "post")
        view.request = _make_request(method="get")

        view.get_permissions()

        assert view.required_permission is None

    def test_mapped_action_skips_unsupported_fallback_even_if_method_disallowed(
        self, monkeypatch
    ):
        view = self._view_with_tenant(monkeypatch)
        view.action = "retrieve"
        view.action_permissions = {"retrieve": ASSET_READ}
        view.unsupported_method_permission = "should-not-be-used"
        view.http_method_names = ("post",)
        view.request = _make_request(method="get")

        view.get_permissions()

        assert view.required_permission == ASSET_READ

    def test_missing_http_method_names_defaults_to_empty_and_triggers_fallback(
        self, monkeypatch
    ):
        view = self._view_with_tenant(monkeypatch)
        view.action = ""
        view.action_permissions = {}
        view.unsupported_method_permission = "fallback-permission"
        view.request = _make_request(method="get")
        assert not hasattr(view, "http_method_names")

        view.get_permissions()

        assert view.required_permission == "fallback-permission"

    def test_missing_action_attribute_defaults_to_empty_string(self, monkeypatch):
        view = self._view_with_tenant(monkeypatch)
        view.action_permissions = {}
        view.http_method_names = ("get",)
        view.request = _make_request(method="get")
        assert not hasattr(view, "action")

        view.get_permissions()

        # Empty-string action is not in the dict, method is allowed -> None.
        assert view.required_permission is None

    def test_get_permissions_delegates_to_super_and_returns_result(self, monkeypatch):
        view = self._view_with_tenant(monkeypatch)
        view.action = "list"
        view.action_permissions = {}
        view.http_method_names = ("get",)
        view.request = _make_request(method="get")

        result = view.get_permissions()

        assert result == ["sentinel-permission"]


class TestActionAccessMixinQuotaResolution:
    def _view_with_tenant(self, monkeypatch, tenant_id=None):
        monkeypatch.setattr(
            permissions_module, "get_user_tenant_id", lambda user: tenant_id
        )
        return _View()

    @pytest.mark.parametrize("read_action", ["list", "retrieve", "history"])
    def test_default_read_actions_use_read_quota(self, monkeypatch, read_action):
        view = self._view_with_tenant(monkeypatch)
        view.action = read_action
        view.action_permissions = {}
        view.action_quotas = {}
        view.http_method_names = ("get",)
        view.request = _make_request(method="get")

        view.get_permissions()

        assert view.quota_resource == "blockchain_traceability.api_reads"
        assert view.quota_cost == 1

    def test_non_read_action_uses_write_quota(self, monkeypatch):
        view = self._view_with_tenant(monkeypatch)
        view.action = "create"
        view.action_permissions = {}
        view.action_quotas = {}
        view.http_method_names = ("post",)
        view.request = _make_request(method="post")

        view.get_permissions()

        assert view.quota_resource == "blockchain_traceability.api_writes"
        assert view.quota_cost == 1

    def test_explicit_action_quota_overrides_read_write_default(self, monkeypatch):
        view = self._view_with_tenant(monkeypatch)
        view.action = "retrieve"
        view.action_permissions = {}
        view.action_quotas = {"retrieve": "blockchain_traceability.custom_quota"}
        view.http_method_names = ("get",)
        view.request = _make_request(method="get")

        view.get_permissions()

        assert view.quota_resource == "blockchain_traceability.custom_quota"

    def test_default_read_actions_frozenset_membership(self):
        assert ActionAccessMixin.read_actions == frozenset({"list", "retrieve", "history"})
        assert "create" not in ActionAccessMixin.read_actions
        assert "update" not in ActionAccessMixin.read_actions
        assert "destroy" not in ActionAccessMixin.read_actions


class TestModuleLevelConstants:
    def test_permissions_tuple_has_exact_expected_membership(self):
        assert len(PERMISSIONS) == 32
        assert len(set(PERMISSIONS)) == len(PERMISSIONS)
        assert all(name.startswith("blockchain_traceability.") for name in PERMISSIONS)

    def test_sod_actions_pairs_are_exact(self):
        assert SOD_ACTIONS == (
            (NETWORK_MANAGE, ANCHOR_VERIFY),
            (CREDENTIAL_ISSUE, CREDENTIAL_REVOKE),
            (COMPLIANCE_CREATE, COMPLIANCE_FINALIZE),
            (CONFIG_UPDATE, CONFIG_ROLLBACK),
        )

    def test_sod_actions_members_are_within_permissions(self):
        for left, right in SOD_ACTIONS:
            assert left in PERMISSIONS
            assert right in PERMISSIONS

    def test_action_access_mixin_default_class_attributes(self):
        assert ActionAccessMixin.action_permissions == {}
        assert ActionAccessMixin.action_quotas == {}
        assert ActionAccessMixin.unsupported_method_permission is None
