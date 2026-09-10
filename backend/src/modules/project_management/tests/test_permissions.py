"""Unit tests for ActionAccessMixin / SessionAuthentication401.

Covers every branch of ``permissions.py``: tenant coercion (valid, missing,
invalid UUID), action resolution (view action vs. request method, case
folding), action_permissions/action_quotas lookups (hit and miss), the
archived-permission override on the ``list`` action (and only that action,
and only on truthy include_archived values), the v1-compat authentication
shortcut vs. the v2 RequiresAccess path, and the ``IsProjectUser`` alias.
"""

from types import SimpleNamespace
from uuid import UUID

import pytest
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.modules.project_management import permissions as permissions_module
from src.modules.project_management.permissions import ActionAccessMixin, IsProjectUser, SessionAuthentication401


def _request(*, user=None, method="GET", path="/api/v2/project-management/projects/", query_params=None):
    return SimpleNamespace(
        user=user,
        method=method,
        path=path,
        query_params=query_params if query_params is not None else {},
    )


class _View(ActionAccessMixin):
    """Minimal concrete view exercising the mixin in isolation."""

    def __init__(self, request, action=None, **overrides):
        self.request = request
        if action is not None:
            self.action = action
        for key, value in overrides.items():
            setattr(self, key, value)


class TestSessionAuthentication401:
    def test_authenticate_header_is_exactly_session(self):
        auth = SessionAuthentication401()
        assert auth.authenticate_header(object()) == "Session"

    def test_authenticate_header_return_type_is_str(self):
        auth = SessionAuthentication401()
        result = auth.authenticate_header(object())
        assert isinstance(result, str)
        assert result != ""


class TestIsProjectUserAlias:
    def test_is_project_user_is_requires_access(self):
        assert IsProjectUser is RequiresAccess


class TestActionAccessMixinClassDefaults:
    def test_defaults(self):
        assert ActionAccessMixin.action_permissions == {}
        assert ActionAccessMixin.action_quotas == {}
        assert ActionAccessMixin.archived_permission is None
        assert ActionAccessMixin.entitlement == "project_management.core"
        assert ActionAccessMixin.authentication_classes == (SessionAuthentication401,)
        assert ActionAccessMixin.permission_classes == (IsAuthenticated, RequiresAccess)


@pytest.fixture(autouse=True)
def _no_tenant_by_default(monkeypatch):
    """Default get_user_tenant_id to None; individual tests override."""

    monkeypatch.setattr(permissions_module, "get_user_tenant_id", lambda user: None)


class TestTenantCoercion:
    def test_no_tenant_sets_tenant_id_none(self):
        view = _View(_request(user=None))
        view.get_permissions()
        assert view.request.tenant_id is None

    def test_valid_uuid_string_tenant_is_coerced(self, monkeypatch):
        tenant = "11111111-1111-1111-1111-111111111111"
        monkeypatch.setattr(permissions_module, "get_user_tenant_id", lambda user: tenant)
        view = _View(_request(user=object()))
        view.get_permissions()
        assert view.request.tenant_id == UUID(tenant)

    def test_uuid_instance_tenant_is_coerced(self, monkeypatch):
        tenant = UUID("22222222-2222-2222-2222-222222222222")
        monkeypatch.setattr(permissions_module, "get_user_tenant_id", lambda user: tenant)
        view = _View(_request(user=object()))
        view.get_permissions()
        assert view.request.tenant_id == tenant

    def test_invalid_tenant_string_falls_back_to_none(self, monkeypatch):
        monkeypatch.setattr(permissions_module, "get_user_tenant_id", lambda user: "not-a-uuid")
        view = _View(_request(user=object()))
        view.get_permissions()
        assert view.request.tenant_id is None

    def test_empty_string_tenant_treated_as_falsy_none(self, monkeypatch):
        monkeypatch.setattr(permissions_module, "get_user_tenant_id", lambda user: "")
        view = _View(_request(user=object()))
        view.get_permissions()
        assert view.request.tenant_id is None

    def test_missing_request_user_attribute_defaults_to_none(self, monkeypatch):
        captured = {}

        def fake(user):
            captured["user"] = user
            return None

        monkeypatch.setattr(permissions_module, "get_user_tenant_id", fake)
        request = SimpleNamespace(method="GET", path="/api/v2/x/", query_params={})
        view = _View(request)
        view.get_permissions()
        assert captured["user"] is None


class TestActionResolution:
    def test_action_from_view_action_attribute_is_lowercased(self):
        view = _View(_request(method="POST"), action="Retrieve")
        view.action_permissions = {"retrieve": "perm.x"}
        view.get_permissions()
        assert view.required_permission == "perm.x"

    def test_action_attribute_takes_precedence_over_request_method(self):
        view = _View(_request(method="DELETE"), action="list")
        view.action_permissions = {"list": "perm.list", "delete": "perm.delete"}
        view.get_permissions()
        assert view.required_permission == "perm.list"

    def test_action_falls_back_to_request_method_when_no_action(self):
        view = _View(_request(method="DELETE"))
        view.action_permissions = {"delete": "perm.delete"}
        view.get_permissions()
        assert view.required_permission == "perm.delete"

    def test_action_none_and_method_missing_resolves_to_empty_string(self):
        request = SimpleNamespace(user=None, query_params={}, path="/api/v2/x/")
        view = _View(request)
        view.action_permissions = {"": "perm.empty"}
        view.get_permissions()
        assert view.required_permission == "perm.empty"

    def test_action_attribute_none_falls_back_to_method(self):
        view = _View(_request(method="PATCH"), action=None)
        view.action_permissions = {"patch": "perm.patch"}
        view.get_permissions()
        assert view.required_permission == "perm.patch"


class TestActionPermissionsAndQuotas:
    def test_permission_lookup_miss_yields_none(self):
        view = _View(_request(method="GET"), action="unmapped")
        view.action_permissions = {"list": "perm.list"}
        view.get_permissions()
        assert view.required_permission is None

    def test_permission_lookup_hit_returns_exact_value(self):
        view = _View(_request(method="GET"), action="create")
        view.action_permissions = {"create": "perm.create"}
        view.get_permissions()
        assert view.required_permission == "perm.create"

    def test_quota_lookup_hit_returns_exact_value(self):
        view = _View(_request(method="GET"), action="create")
        view.action_quotas = {"create": "quota.create"}
        view.get_permissions()
        assert view.quota_resource == "quota.create"

    def test_quota_lookup_miss_yields_none(self):
        view = _View(_request(method="GET"), action="retrieve")
        view.action_quotas = {"create": "quota.create"}
        view.get_permissions()
        assert view.quota_resource is None

    def test_quota_cost_is_exactly_one(self):
        view = _View(_request(method="GET"), action="create")
        view.get_permissions()
        assert view.quota_cost == 1
        assert view.quota_cost is not None

    def test_required_entitlement_defaults_to_class_entitlement(self):
        view = _View(_request(method="GET"), action="list")
        view.get_permissions()
        assert view.required_entitlement == "project_management.core"

    def test_required_entitlement_uses_overridden_entitlement(self):
        view = _View(_request(method="GET"), action="list", entitlement="custom.ent")
        view.get_permissions()
        assert view.required_entitlement == "custom.ent"


class TestArchivedPermissionOverride:
    def test_list_action_with_include_archived_true_overrides_permission(self):
        view = _View(
            _request(method="GET", query_params={"include_archived": "true"}),
            action="list",
        )
        view.action_permissions = {"list": "perm.list"}
        view.archived_permission = "perm.archived"
        view.get_permissions()
        assert view.required_permission == "perm.archived"

    def test_list_action_with_include_archived_one_overrides_permission(self):
        view = _View(
            _request(method="GET", query_params={"include_archived": "1"}),
            action="list",
        )
        view.action_permissions = {"list": "perm.list"}
        view.archived_permission = "perm.archived"
        view.get_permissions()
        assert view.required_permission == "perm.archived"

    def test_list_action_include_archived_case_insensitive(self):
        view = _View(
            _request(method="GET", query_params={"include_archived": "TRUE"}),
            action="list",
        )
        view.action_permissions = {"list": "perm.list"}
        view.archived_permission = "perm.archived"
        view.get_permissions()
        assert view.required_permission == "perm.archived"

    def test_list_action_with_include_archived_false_does_not_override(self):
        view = _View(
            _request(method="GET", query_params={"include_archived": "false"}),
            action="list",
        )
        view.action_permissions = {"list": "perm.list"}
        view.archived_permission = "perm.archived"
        view.get_permissions()
        assert view.required_permission == "perm.list"

    def test_list_action_with_include_archived_arbitrary_string_does_not_override(self):
        view = _View(
            _request(method="GET", query_params={"include_archived": "yes"}),
            action="list",
        )
        view.action_permissions = {"list": "perm.list"}
        view.archived_permission = "perm.archived"
        view.get_permissions()
        assert view.required_permission == "perm.list"

    def test_list_action_without_include_archived_does_not_override(self):
        view = _View(_request(method="GET", query_params={}), action="list")
        view.action_permissions = {"list": "perm.list"}
        view.archived_permission = "perm.archived"
        view.get_permissions()
        assert view.required_permission == "perm.list"

    def test_non_list_action_ignores_include_archived_true(self):
        view = _View(
            _request(method="GET", query_params={"include_archived": "true"}),
            action="retrieve",
        )
        view.action_permissions = {"retrieve": "perm.retrieve"}
        view.archived_permission = "perm.archived"
        view.get_permissions()
        assert view.required_permission == "perm.retrieve"

    def test_list_action_include_archived_true_with_no_archived_permission_set_yields_none(self):
        view = _View(
            _request(method="GET", query_params={"include_archived": "true"}),
            action="list",
        )
        view.action_permissions = {"list": "perm.list"}
        # archived_permission left at default (None)
        view.get_permissions()
        assert view.required_permission is None


class TestV1CompatPathShortcut:
    def test_v1_path_returns_only_is_authenticated(self):
        view = _View(_request(method="GET", path="/api/v1/project-management/projects/"), action="list")
        result = view.get_permissions()
        assert len(result) == 1
        assert isinstance(result[0], IsAuthenticated)

    def test_v2_path_returns_is_authenticated_and_requires_access(self):
        view = _View(_request(method="GET", path="/api/v2/project-management/projects/"), action="list")
        result = view.get_permissions()
        assert len(result) == 2
        assert isinstance(result[0], IsAuthenticated)
        assert isinstance(result[1], RequiresAccess)

    def test_unrelated_path_returns_is_authenticated_and_requires_access(self):
        view = _View(_request(method="GET", path="/api/v2/other-module/thing/"), action="list")
        result = view.get_permissions()
        assert len(result) == 2
        assert isinstance(result[0], IsAuthenticated)
        assert isinstance(result[1], RequiresAccess)

    def test_path_missing_entirely_defaults_to_empty_string_and_full_pipeline(self):
        request = SimpleNamespace(user=None, method="GET", query_params={})
        view = _View(request, action="list")
        result = view.get_permissions()
        assert len(result) == 2

    def test_v1_prefix_must_match_from_start_not_substring(self):
        # A path that merely *contains* the v1 prefix elsewhere must NOT
        # trigger the compatibility shortcut -- startswith is anchored.
        view = _View(
            _request(method="GET", path="/api/v2/wrapper/api/v1/project-management/projects/"),
            action="list",
        )
        result = view.get_permissions()
        assert len(result) == 2
        assert isinstance(result[1], RequiresAccess)

    def test_v1_exact_prefix_boundary(self):
        view = _View(_request(method="GET", path="/api/v1/project-management/"), action="list")
        result = view.get_permissions()
        assert len(result) == 1

    def test_v1_prefix_without_trailing_segment_does_not_match(self):
        # Missing the trailing slash after "project-management" so the
        # startswith check must fail.
        view = _View(_request(method="GET", path="/api/v1/project-management"), action="list")
        result = view.get_permissions()
        assert len(result) == 2
