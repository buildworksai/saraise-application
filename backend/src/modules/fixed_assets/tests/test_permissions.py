"""Unit tests for the fail-closed authorization primitives.

Exercises ``ActionAccessMixin.get_permissions`` directly (independent of the
DRF request cycle exercised in ``test_api.py``) plus the module-level
constants and ``SessionAuthentication401``.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.modules.fixed_assets.permissions import (
    PERMISSIONS,
    READ_ACTIONS,
    ActionAccessMixin,
    SessionAuthentication401,
)


def _view(*, action: str = "list", request: object | None = None) -> ActionAccessMixin:
    """Build a bare ``ActionAccessMixin`` instance for direct testing."""

    view = ActionAccessMixin()
    view.action = action
    view.request = request if request is not None else SimpleNamespace(user=None)
    return view


def _request_with_tenant(tenant_id: object) -> SimpleNamespace:
    profile = SimpleNamespace(tenant_id=tenant_id)
    user = SimpleNamespace(profile=profile)
    return SimpleNamespace(user=user)


class TestSessionAuthentication401:
    def test_is_session_authentication_subclass(self) -> None:
        assert issubclass(SessionAuthentication401, SessionAuthentication)

    def test_authenticate_header_returns_session(self) -> None:
        auth = SessionAuthentication401()
        assert auth.authenticate_header(object()) == "Session"

    def test_authenticate_header_ignores_none_request(self) -> None:
        auth = SessionAuthentication401()
        assert auth.authenticate_header(None) == "Session"

    def test_authenticate_header_ignores_request_content(self) -> None:
        auth = SessionAuthentication401()
        # Different inputs must never change the returned challenge scheme.
        assert auth.authenticate_header(SimpleNamespace(anything="x")) == "Session"


class TestModuleConstants:
    def test_permissions_is_exact_tuple(self) -> None:
        assert PERMISSIONS == (
            "fixed_asset.category:read",
            "fixed_asset.category:create",
            "fixed_asset.category:update",
            "fixed_asset.category:delete",
            "fixed_asset.asset:read",
            "fixed_asset.asset:create",
            "fixed_asset.asset:update",
            "fixed_asset.asset:delete",
            "fixed_asset.asset:capitalize",
            "fixed_asset.asset:transfer",
            "fixed_asset.asset:impair",
            "fixed_asset.asset:dispose",
            "fixed_asset.depreciation:read",
            "fixed_asset.depreciation:calculate",
            "fixed_asset.depreciation:post",
            "fixed_asset.transaction:read",
        )

    def test_permissions_length(self) -> None:
        assert len(PERMISSIONS) == 16

    def test_permissions_has_no_duplicates(self) -> None:
        assert len(set(PERMISSIONS)) == len(PERMISSIONS)

    def test_read_actions_is_exact_frozenset(self) -> None:
        assert READ_ACTIONS == frozenset({"list", "retrieve", "transactions", "dashboard"})

    def test_read_actions_length(self) -> None:
        assert len(READ_ACTIONS) == 4

    def test_read_actions_excludes_mutating_verbs(self) -> None:
        for verb in ("create", "update", "partial_update", "destroy", "capitalize", "transfer"):
            assert verb not in READ_ACTIONS


class TestActionAccessMixinClassDefaults:
    def test_authentication_classes_default(self) -> None:
        assert ActionAccessMixin.authentication_classes == (SessionAuthentication401,)

    def test_permission_classes_default(self) -> None:
        assert ActionAccessMixin.permission_classes == (IsAuthenticated, RequiresAccess)

    def test_action_permissions_default_empty(self) -> None:
        assert ActionAccessMixin.action_permissions == {}

    def test_action_quotas_default_empty(self) -> None:
        assert ActionAccessMixin.action_quotas == {}

    def test_entitlement_default(self) -> None:
        assert ActionAccessMixin.entitlement == "fixed_assets.core"


class TestGetPermissionsTenantCoercion:
    def test_valid_uuid_string_tenant_is_coerced(self) -> None:
        tenant = uuid4()
        view = _view(request=_request_with_tenant(str(tenant)))
        view.get_permissions()
        assert view.request.tenant_id == tenant
        assert isinstance(view.request.tenant_id, UUID)

    def test_uuid_object_tenant_round_trips(self) -> None:
        tenant = uuid4()
        view = _view(request=_request_with_tenant(tenant))
        view.get_permissions()
        assert view.request.tenant_id == tenant

    def test_invalid_uuid_string_tenant_is_none(self) -> None:
        view = _view(request=_request_with_tenant("not-a-uuid"))
        view.get_permissions()
        assert view.request.tenant_id is None

    def test_empty_string_tenant_is_none(self) -> None:
        view = _view(request=_request_with_tenant(""))
        view.get_permissions()
        assert view.request.tenant_id is None

    def test_none_tenant_is_none(self) -> None:
        view = _view(request=_request_with_tenant(None))
        view.get_permissions()
        assert view.request.tenant_id is None

    def test_missing_profile_yields_none_tenant(self) -> None:
        # get_user_tenant_id swallows AttributeError for a user with no profile.
        user = SimpleNamespace()
        view = _view(request=SimpleNamespace(user=user))
        view.get_permissions()
        assert view.request.tenant_id is None

    def test_missing_user_yields_none_tenant(self) -> None:
        view = _view(request=SimpleNamespace(user=None))
        view.get_permissions()
        assert view.request.tenant_id is None

    def test_non_uuid_numeric_tenant_is_none(self) -> None:
        # An int that cannot form a UUID string must fail closed, not raise.
        view = _view(request=_request_with_tenant(12345))
        view.get_permissions()
        assert view.request.tenant_id is None


class TestGetPermissionsActionResolution:
    def test_unmapped_action_fails_closed(self) -> None:
        view = _view(action="destroy", request=_request_with_tenant(uuid4()))
        view.action_permissions = {"list": "fixed_asset.asset:read"}
        view.get_permissions()
        assert view.required_permission is None

    def test_mapped_action_resolves_permission(self) -> None:
        view = _view(action="list", request=_request_with_tenant(uuid4()))
        view.action_permissions = {"list": "fixed_asset.asset:read"}
        view.get_permissions()
        assert view.required_permission == "fixed_asset.asset:read"

    def test_missing_action_attribute_defaults_to_empty_string(self) -> None:
        view = ActionAccessMixin()
        view.request = _request_with_tenant(uuid4())
        # No `.action` attribute set at all — getattr(..., "") must apply.
        view.action_permissions = {"": "should-not-match-real-actions"}
        view.get_permissions()
        assert view.required_permission == "should-not-match-real-actions"

    def test_required_entitlement_matches_class_entitlement(self) -> None:
        view = _view(action="list", request=_request_with_tenant(uuid4()))
        view.entitlement = "custom.entitlement"
        view.get_permissions()
        assert view.required_entitlement == "custom.entitlement"

    def test_required_entitlement_default(self) -> None:
        view = _view(action="list", request=_request_with_tenant(uuid4()))
        view.get_permissions()
        assert view.required_entitlement == "fixed_assets.core"

    def test_quota_cost_is_always_one(self) -> None:
        view = _view(action="capitalize", request=_request_with_tenant(uuid4()))
        view.action_quotas = {"capitalize": "fixed_asset.asset:capitalize"}
        view.get_permissions()
        assert view.quota_cost == 1

    def test_unmapped_action_has_no_quota_resource(self) -> None:
        view = _view(action="list", request=_request_with_tenant(uuid4()))
        view.action_quotas = {"capitalize": "fixed_asset.asset:capitalize"}
        view.get_permissions()
        assert view.quota_resource is None

    def test_mapped_action_resolves_quota_resource(self) -> None:
        view = _view(action="capitalize", request=_request_with_tenant(uuid4()))
        view.action_quotas = {"capitalize": "fixed_asset.asset:capitalize"}
        view.get_permissions()
        assert view.quota_resource == "fixed_asset.asset:capitalize"

    def test_read_action_never_carries_quota_by_construction(self) -> None:
        # Read actions are simply absent from action_quotas on real subclasses;
        # verify that absence alone is sufficient to suppress quota consumption.
        view = _view(action="retrieve", request=_request_with_tenant(uuid4()))
        view.action_quotas = {}
        view.get_permissions()
        assert view.quota_resource is None


class TestGetPermissionsReturnValue:
    def test_returns_two_permission_instances(self) -> None:
        view = _view(request=_request_with_tenant(uuid4()))
        result = view.get_permissions()
        assert len(result) == 2

    def test_returns_is_authenticated_instance(self) -> None:
        view = _view(request=_request_with_tenant(uuid4()))
        result = view.get_permissions()
        assert isinstance(result[0], IsAuthenticated)

    def test_returns_requires_access_instance(self) -> None:
        view = _view(request=_request_with_tenant(uuid4()))
        result = view.get_permissions()
        assert isinstance(result[1], RequiresAccess)

    def test_returns_new_instances_each_call(self) -> None:
        view = _view(request=_request_with_tenant(uuid4()))
        first = view.get_permissions()
        second = view.get_permissions()
        assert first[0] is not second[0]
        assert first[1] is not second[1]
