"""Unit tests for ActionAccessMixin fail-closed access declarations.

These tests exercise ``get_permissions`` directly against a minimal fake view,
independent of any concrete ViewSet, so every branch of the tenant-id
coercion, action->permission lookup, and quota-cost resolution is pinned.
"""

from __future__ import annotations

import uuid

import pytest
from rest_framework.permissions import BasePermission, IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.authentication import RelaxedCsrfSessionAuthentication
from src.modules.api_management.permissions import (
    CONFIG_EXPORT,
    CONFIG_IMPORT,
    CONFIG_READ,
    CONFIG_ROLLBACK,
    CONFIG_UPDATE,
    HEALTH_READ,
    PERMISSIONS,
    RESOURCE_ACTIVATE,
    RESOURCE_CREATE,
    RESOURCE_DEACTIVATE,
    RESOURCE_DELETE,
    RESOURCE_READ,
    RESOURCE_RESTORE,
    RESOURCE_ROLLBACK,
    RESOURCE_UPDATE,
    SOD_ACTIONS,
    ActionAccessMixin,
)
from src.modules.api_management.services import PLATFORM_HARD_CEILINGS


class _FakeRequest:
    """Minimal stand-in for a DRF request object."""

    def __init__(self, user):
        self.user = user


class _FakeUser:
    def __init__(self, tenant_id):
        self._tenant_id = tenant_id

    @property
    def profile(self):
        return self


class _FakeView(ActionAccessMixin):
    def __init__(self, request, action="list", action_permissions=None):
        self.request = request
        self.action = action
        if action_permissions is not None:
            self.action_permissions = action_permissions


def _user_with_tenant(tenant_id):
    """Build a fake user whose profile.tenant_id resolves via get_user_tenant_id."""

    user = _FakeUser(tenant_id)
    user.profile.tenant_id = tenant_id
    return user


@pytest.mark.django_db
class TestActionAccessMixinClassDefaults:
    def test_authentication_classes_is_relaxed_csrf_session(self):
        assert ActionAccessMixin.authentication_classes == (RelaxedCsrfSessionAuthentication,)

    def test_permission_classes_is_isauthenticated_and_requiresaccess_in_order(self):
        assert ActionAccessMixin.permission_classes == (IsAuthenticated, RequiresAccess)

    def test_default_action_permissions_is_empty_dict(self):
        assert ActionAccessMixin.action_permissions == {}


@pytest.mark.django_db
class TestGetPermissionsTenantCoercion:
    def test_valid_tenant_id_string_is_coerced_to_uuid(self):
        tenant_uuid = uuid.uuid4()
        user = _user_with_tenant(str(tenant_uuid))
        view = _FakeView(_FakeRequest(user), action="list", action_permissions={"list": RESOURCE_READ})

        view.get_permissions()

        assert view.request.tenant_id == tenant_uuid
        assert isinstance(view.request.tenant_id, uuid.UUID)

    def test_invalid_tenant_id_string_denies_by_setting_none(self):
        user = _user_with_tenant("not-a-uuid")
        view = _FakeView(_FakeRequest(user), action="list", action_permissions={"list": RESOURCE_READ})

        view.get_permissions()

        assert view.request.tenant_id is None

    def test_none_tenant_id_short_circuits_to_none_without_uuid_call(self):
        user = _user_with_tenant(None)
        view = _FakeView(_FakeRequest(user), action="list", action_permissions={"list": RESOURCE_READ})

        view.get_permissions()

        assert view.request.tenant_id is None

    def test_missing_user_denies_by_setting_none(self):
        view = _FakeView(_FakeRequest(None), action="list", action_permissions={"list": RESOURCE_READ})

        view.get_permissions()

        assert view.request.tenant_id is None

    def test_empty_string_tenant_id_is_falsy_and_short_circuits(self):
        user = _user_with_tenant("")
        view = _FakeView(_FakeRequest(user), action="list", action_permissions={"list": RESOURCE_READ})

        view.get_permissions()

        assert view.request.tenant_id is None


@pytest.mark.django_db
class TestGetPermissionsActionMapping:
    def test_mapped_action_sets_required_permission_and_entitlement(self):
        tenant_uuid = uuid.uuid4()
        user = _user_with_tenant(str(tenant_uuid))
        view = _FakeView(_FakeRequest(user), action="create", action_permissions={"create": RESOURCE_CREATE})

        view.get_permissions()

        assert view.required_permission == RESOURCE_CREATE
        assert view.required_entitlement == RESOURCE_CREATE

    def test_unmapped_action_denies_by_setting_permission_none(self):
        tenant_uuid = uuid.uuid4()
        user = _user_with_tenant(str(tenant_uuid))
        view = _FakeView(
            _FakeRequest(user), action="destroy_everything", action_permissions={"create": RESOURCE_CREATE}
        )

        view.get_permissions()

        assert view.required_permission is None
        assert view.required_entitlement is None

    def test_missing_action_attribute_defaults_to_empty_string_lookup(self):
        tenant_uuid = uuid.uuid4()
        user = _user_with_tenant(str(tenant_uuid))
        view = _FakeView(_FakeRequest(user), action_permissions={"": "should-not-normally-match"})
        del view.action

        view.get_permissions()

        # action defaults to "" via getattr(self, "action", "") fallback
        assert view.required_permission == "should-not-normally-match"

    def test_quota_resource_uses_exact_dotted_prefix_and_action_when_permitted(self):
        tenant_uuid = uuid.uuid4()
        user = _user_with_tenant(str(tenant_uuid))
        view = _FakeView(_FakeRequest(user), action="rollback", action_permissions={"rollback": RESOURCE_ROLLBACK})

        view.get_permissions()

        assert view.quota_resource == "api_management.rollback"

    def test_quota_resource_is_none_when_action_is_unmapped(self):
        tenant_uuid = uuid.uuid4()
        user = _user_with_tenant(str(tenant_uuid))
        view = _FakeView(_FakeRequest(user), action="unmapped", action_permissions={})

        view.get_permissions()

        assert view.quota_resource is None

    def test_quota_resource_uses_unknown_literal_when_action_attribute_absent(self):
        tenant_uuid = uuid.uuid4()
        user = _user_with_tenant(str(tenant_uuid))
        view = _FakeView(_FakeRequest(user), action_permissions={"": RESOURCE_READ})
        del view.action

        view.get_permissions()

        assert view.quota_resource == "api_management.unknown"


@pytest.mark.django_db
class TestGetPermissionsQuotaCost:
    def test_tenant_present_resolves_quota_cost_via_service(self):
        tenant_uuid = uuid.uuid4()
        user = _user_with_tenant(str(tenant_uuid))
        view = _FakeView(_FakeRequest(user), action="list", action_permissions={"list": RESOURCE_READ})

        view.get_permissions()

        # No configuration exists for this fresh tenant, so the service falls
        # back to the DEFAULT_CONFIGURATION's quota_cost (1) -- distinct from
        # the platform hard ceiling fallback (1000) used when tenant_id is
        # None/invalid. Asserting the exact value discriminates the branch.
        assert view.quota_cost == 1
        assert view.quota_cost != PLATFORM_HARD_CEILINGS["quota_cost"]

    def test_tenant_absent_uses_platform_hard_ceiling_quota_cost(self):
        user = _user_with_tenant(None)
        view = _FakeView(_FakeRequest(user), action="list", action_permissions={"list": RESOURCE_READ})

        view.get_permissions()

        assert view.quota_cost == PLATFORM_HARD_CEILINGS["quota_cost"]

    def test_invalid_tenant_id_also_uses_platform_hard_ceiling_quota_cost(self):
        user = _user_with_tenant("garbage-not-a-uuid")
        view = _FakeView(_FakeRequest(user), action="list", action_permissions={"list": RESOURCE_READ})

        view.get_permissions()

        assert view.request.tenant_id is None
        assert view.quota_cost == PLATFORM_HARD_CEILINGS["quota_cost"]


@pytest.mark.django_db
class TestGetPermissionsReturnValue:
    def test_returns_exactly_two_permission_instances(self):
        user = _user_with_tenant(None)
        view = _FakeView(_FakeRequest(user), action="list", action_permissions={"list": RESOURCE_READ})

        result = view.get_permissions()

        assert len(result) == 2
        assert all(isinstance(p, BasePermission) for p in result)

    def test_returns_isauthenticated_then_requiresaccess_in_order(self):
        user = _user_with_tenant(None)
        view = _FakeView(_FakeRequest(user), action="list", action_permissions={"list": RESOURCE_READ})

        result = view.get_permissions()

        assert isinstance(result[0], IsAuthenticated)
        assert not isinstance(result[0], RequiresAccess)
        assert isinstance(result[1], RequiresAccess)


class TestPermissionRegistryExactMembership:
    def test_permissions_tuple_has_exact_expected_members_in_order(self):
        assert PERMISSIONS == (
            RESOURCE_CREATE,
            RESOURCE_READ,
            RESOURCE_UPDATE,
            RESOURCE_DELETE,
            RESOURCE_ACTIVATE,
            RESOURCE_DEACTIVATE,
            RESOURCE_RESTORE,
            RESOURCE_ROLLBACK,
            CONFIG_READ,
            CONFIG_UPDATE,
            CONFIG_ROLLBACK,
            CONFIG_IMPORT,
            CONFIG_EXPORT,
            HEALTH_READ,
        )

    def test_permissions_tuple_length_is_exactly_fourteen(self):
        assert len(PERMISSIONS) == 14

    def test_permission_string_values_are_exact(self):
        assert RESOURCE_CREATE == "api_management.resource:create"
        assert RESOURCE_READ == "api_management.resource:read"
        assert RESOURCE_UPDATE == "api_management.resource:update"
        assert RESOURCE_DELETE == "api_management.resource:delete"
        assert RESOURCE_ACTIVATE == "api_management.resource:activate"
        assert RESOURCE_DEACTIVATE == "api_management.resource:deactivate"
        assert RESOURCE_RESTORE == "api_management.resource:restore"
        assert RESOURCE_ROLLBACK == "api_management.resource:rollback"
        assert CONFIG_READ == "api_management.configuration:read"
        assert CONFIG_UPDATE == "api_management.configuration:update"
        assert CONFIG_ROLLBACK == "api_management.configuration:rollback"
        assert CONFIG_IMPORT == "api_management.configuration:import"
        assert CONFIG_EXPORT == "api_management.configuration:export"
        assert HEALTH_READ == "api_management.health:read"

    def test_sod_actions_tuple_has_exact_expected_members_in_order(self):
        assert SOD_ACTIONS == (RESOURCE_CREATE, RESOURCE_DELETE, CONFIG_UPDATE, CONFIG_ROLLBACK)

    def test_sod_actions_length_is_exactly_four(self):
        assert len(SOD_ACTIONS) == 4

    def test_sod_actions_is_subset_of_permissions(self):
        assert set(SOD_ACTIONS).issubset(set(PERMISSIONS))

    def test_module_exports_exact_public_names(self):
        from src.modules.api_management import permissions as permissions_module

        assert permissions_module.__all__ == ["ActionAccessMixin", "PERMISSIONS", "SOD_ACTIONS"]
