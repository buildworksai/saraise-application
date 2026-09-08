"""Unit tests for src.modules.multi_company.permissions.

Covers tenant-id coercion (valid/invalid/None), fail-closed unmapped
action handling, permission/entitlement/quota resolution, and the
class-level PERMISSIONS/SOD_ACTIONS registries.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.modules.multi_company.permissions import (
    PERMISSIONS,
    SOD_ACTIONS,
    MultiCompanyAccessMixin,
    SessionAuthentication401,
)


class _View(MultiCompanyAccessMixin):
    """Minimal concrete view exercising the mixin in isolation."""


def _make_view(*, action: str = "", user: object = "user-sentinel", tenant_id_raw=None) -> _View:
    view = _View()
    request = SimpleNamespace(user=user)
    view.request = request
    view.action = action
    with patch(
        "src.modules.multi_company.permissions.get_user_tenant_id",
        return_value=tenant_id_raw,
    ):
        view.get_permissions()
    return view


class TestSessionAuthentication401:
    def test_is_subclass_of_session_authentication(self):
        assert issubclass(SessionAuthentication401, SessionAuthentication)

    def test_authenticate_header_returns_session_literal(self):
        auth = SessionAuthentication401()
        assert auth.authenticate_header(request=object()) == "Session"

    def test_authenticate_header_ignores_request_argument(self):
        auth = SessionAuthentication401()
        # Passing wildly different request objects must not change the result.
        assert auth.authenticate_header(request=None) == "Session"
        assert auth.authenticate_header(request=SimpleNamespace(foo="bar")) == "Session"


class TestTenantIdCoercion:
    def test_valid_uuid_string_is_coerced_to_uuid(self):
        raw = str(uuid.uuid4())
        view = _make_view(tenant_id_raw=raw)
        assert view.request.tenant_id == uuid.UUID(raw)
        assert isinstance(view.request.tenant_id, uuid.UUID)

    def test_valid_uuid_object_round_trips(self):
        raw = uuid.uuid4()
        view = _make_view(tenant_id_raw=raw)
        assert view.request.tenant_id == raw

    def test_none_tenant_id_stays_none(self):
        view = _make_view(tenant_id_raw=None)
        assert view.request.tenant_id is None

    def test_empty_string_tenant_id_stays_none(self):
        # Falsy raw_tenant short-circuits the `if raw_tenant else None` branch.
        view = _make_view(tenant_id_raw="")
        assert view.request.tenant_id is None

    def test_invalid_uuid_string_falls_back_to_none(self):
        view = _make_view(tenant_id_raw="not-a-uuid")
        assert view.request.tenant_id is None

    def test_non_uuid_object_without_str_support_falls_back_to_none(self):
        class Unstringable:
            def __str__(self):
                raise TypeError("boom")

        view = _make_view(tenant_id_raw=Unstringable())
        assert view.request.tenant_id is None

    def test_getattr_user_missing_does_not_raise(self):
        # request has no `user` attribute at all -> getattr(..., None) path.
        view = _View()
        request = SimpleNamespace()
        view.request = request
        view.action = "company:read"
        with patch(
            "src.modules.multi_company.permissions.get_user_tenant_id",
            return_value=None,
        ) as mocked:
            view.get_permissions()
        mocked.assert_called_once_with(None)
        assert view.request.tenant_id is None


class TestActionPermissionResolution:
    def test_mapped_action_resolves_required_permission(self):
        view = _View()
        view.action_permissions = {"list": "multi_company.company:read"}
        view.request = SimpleNamespace(user=None)
        view.action = "list"
        with patch(
            "src.modules.multi_company.permissions.get_user_tenant_id",
            return_value=None,
        ):
            view.get_permissions()
        assert view.required_permission == "multi_company.company:read"

    def test_unmapped_action_leaves_required_permission_unset_fail_closed(self):
        view = _View()
        view.action_permissions = {"list": "multi_company.company:read"}
        view.request = SimpleNamespace(user=None)
        view.action = "destroy_everything"
        with patch(
            "src.modules.multi_company.permissions.get_user_tenant_id",
            return_value=None,
        ):
            view.get_permissions()
        assert view.required_permission is None

    def test_empty_action_and_no_permission_action_resolves_empty_string_action(self):
        view = _View()
        view.request = SimpleNamespace(user=None)
        # Neither `action` nor `permission_action` is set on the instance,
        # so getattr falls through both defaults to "".
        with patch(
            "src.modules.multi_company.permissions.get_user_tenant_id",
            return_value=None,
        ):
            view.get_permissions()
        assert view.required_permission is None

    def test_permission_action_used_when_action_absent(self):
        view = _View()
        view.action_permissions = {"custom_op": "multi_company.transaction:dispute"}
        view.permission_action = "custom_op"
        view.request = SimpleNamespace(user=None)
        # No `action` attribute set at all.
        with patch(
            "src.modules.multi_company.permissions.get_user_tenant_id",
            return_value=None,
        ):
            view.get_permissions()
        assert view.required_permission == "multi_company.transaction:dispute"

    def test_action_takes_precedence_over_permission_action(self):
        view = _View()
        view.action_permissions = {
            "primary": "multi_company.company:read",
            "secondary": "multi_company.company:delete",
        }
        view.action = "primary"
        view.permission_action = "secondary"
        view.request = SimpleNamespace(user=None)
        with patch(
            "src.modules.multi_company.permissions.get_user_tenant_id",
            return_value=None,
        ):
            view.get_permissions()
        assert view.required_permission == "multi_company.company:read"


class TestQuotaResolution:
    def test_mapped_action_resolves_quota_resource(self):
        view = _View()
        view.action_quotas = {"create": "transaction_write"}
        view.request = SimpleNamespace(user=None)
        view.action = "create"
        with patch(
            "src.modules.multi_company.permissions.get_user_tenant_id",
            return_value=None,
        ):
            view.get_permissions()
        assert view.quota_resource == "transaction_write"
        assert view.quota_cost == 1

    def test_unmapped_action_leaves_quota_resource_none(self):
        view = _View()
        view.action_quotas = {"create": "transaction_write"}
        view.request = SimpleNamespace(user=None)
        view.action = "read_only_action"
        with patch(
            "src.modules.multi_company.permissions.get_user_tenant_id",
            return_value=None,
        ):
            view.get_permissions()
        assert view.quota_resource is None
        assert view.quota_cost == 1

    def test_quota_cost_is_always_exactly_one(self):
        view = _make_view(action="anything")
        assert view.quota_cost == 1


class TestRequiredEntitlement:
    def test_required_entitlement_is_always_reset_to_module_constant(self):
        view = _View()
        view.required_entitlement = "some.other.value"
        view.request = SimpleNamespace(user=None)
        view.action = "list"
        with patch(
            "src.modules.multi_company.permissions.get_user_tenant_id",
            return_value=None,
        ):
            view.get_permissions()
        assert view.required_entitlement == "module.multi_company"

    def test_class_level_default_required_entitlement(self):
        assert MultiCompanyAccessMixin.required_entitlement == "module.multi_company"


class TestGetPermissionsReturnValue:
    def test_returns_isauthenticated_and_requiresaccess_instances(self):
        view = _make_view(action="list")
        perms = view.get_permissions()
        assert len(perms) == 2
        assert isinstance(perms[0], IsAuthenticated)
        assert isinstance(perms[1], RequiresAccess)

    def test_returns_fresh_instances_on_each_call(self):
        view = _make_view(action="list")
        first = view.get_permissions()
        second = view.get_permissions()
        assert first[0] is not second[0]
        assert first[1] is not second[1]


class TestClassLevelDefaults:
    def test_authentication_classes_is_session_authentication_401(self):
        assert MultiCompanyAccessMixin.authentication_classes == (SessionAuthentication401,)

    def test_permission_classes_default_tuple(self):
        assert MultiCompanyAccessMixin.permission_classes == (IsAuthenticated, RequiresAccess)

    def test_action_permissions_default_empty_dict(self):
        assert MultiCompanyAccessMixin.action_permissions == {}

    def test_action_quotas_default_empty_dict(self):
        assert MultiCompanyAccessMixin.action_quotas == {}

    def test_instance_level_dicts_do_not_mutate_class_defaults(self):
        # Guard against accidental shared mutable default pollution across
        # concrete viewsets that assign to self.action_permissions.
        view = _View()
        view.action_permissions = {"list": "multi_company.company:read"}
        assert MultiCompanyAccessMixin.action_permissions == {}


class TestPermissionsRegistry:
    def test_permissions_is_a_tuple(self):
        assert isinstance(PERMISSIONS, tuple)

    def test_permissions_has_no_duplicates(self):
        assert len(PERMISSIONS) == len(set(PERMISSIONS))

    def test_permissions_exact_membership(self):
        expected = {
            "multi_company.company:read",
            "multi_company.company:create",
            "multi_company.company:update",
            "multi_company.company:deactivate",
            "multi_company.company:delete",
            "multi_company.company:read_sensitive",
            "multi_company.company_access:read",
            "multi_company.company_access:grant",
            "multi_company.company_access:revoke",
            "multi_company.transaction:read",
            "multi_company.transaction:create",
            "multi_company.transaction:update",
            "multi_company.transaction:submit",
            "multi_company.transaction:approve",
            "multi_company.transaction:post",
            "multi_company.transaction:dispute",
            "multi_company.transaction:cancel",
            "multi_company.transaction:reverse",
            "multi_company.consolidation:read",
            "multi_company.consolidation:create",
            "multi_company.consolidation:update",
            "multi_company.consolidation:execute",
            "multi_company.consolidation:approve",
            "multi_company.consolidation:publish",
            "multi_company.elimination:read",
            "multi_company.elimination:create",
            "multi_company.transfer_pricing:read",
            "multi_company.transfer_pricing:create",
            "multi_company.transfer_pricing:update",
            "multi_company.transfer_pricing:delete",
            "multi_company.transfer_pricing:calculate",
            "multi_company.configuration:read",
            "multi_company.configuration:write",
            "multi_company.configuration:activate",
            "multi_company.configuration:rollback",
            "multi_company.configuration:import",
            "multi_company.configuration:export",
            "multi_company.extension:read",
            "multi_company.health:read",
        }
        assert set(PERMISSIONS) == expected
        assert len(PERMISSIONS) == 39

    def test_permissions_first_and_last_entries_pinned(self):
        assert PERMISSIONS[0] == "multi_company.company:read"
        assert PERMISSIONS[-1] == "multi_company.health:read"

    def test_all_permissions_prefixed_with_module_name(self):
        assert all(p.startswith("multi_company.") for p in PERMISSIONS)

    def test_all_permissions_contain_exactly_one_colon(self):
        assert all(p.count(":") == 1 for p in PERMISSIONS)


class TestSodActionsRegistry:
    def test_sod_actions_is_a_tuple(self):
        assert isinstance(SOD_ACTIONS, tuple)

    def test_sod_actions_has_no_duplicates(self):
        assert len(SOD_ACTIONS) == len(set(SOD_ACTIONS))

    def test_sod_actions_exact_membership(self):
        expected = {
            "transaction_creator_vs_approver",
            "transaction_source_approver_vs_target_approver",
            "consolidation_executor_vs_approver",
            "consolidation_executor_vs_publisher",
            "production_configuration_author_vs_activator",
            "company_access_grantor_role_ceiling",
        }
        assert set(SOD_ACTIONS) == expected
        assert len(SOD_ACTIONS) == 6

    def test_sod_actions_first_and_last_entries_pinned(self):
        assert SOD_ACTIONS[0] == "transaction_creator_vs_approver"
        assert SOD_ACTIONS[-1] == "company_access_grantor_role_ceiling"


class TestModuleAll:
    def test_dunder_all_exact_contents(self):
        from src.modules.multi_company import permissions as permissions_module

        assert set(permissions_module.__all__) == {
            "MultiCompanyAccessMixin",
            "PERMISSIONS",
            "SOD_ACTIONS",
            "SessionAuthentication401",
        }
