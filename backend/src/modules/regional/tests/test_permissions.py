"""
Tests for Regional permission classes.

Exercises every branch of RegionalPolicyPermission.has_permission():
- unauthenticated / missing user
- missing / raising profile
- tenant_id UUID coercion (valid, invalid, missing, None)
- resource vs configuration action-permission mapping
- the `current` action's GET-vs-write split under the configuration scope
- unmapped action -> fail closed
- privileged role / superuser short-circuit
- user.has_perm() delegation for the non-privileged path
- module-level constant registries (PERMISSIONS, SOD_ACTIONS)
- class-level mapping dict contents
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.modules.regional.permissions import (
    PERMISSIONS,
    SOD_ACTIONS,
    RegionalPolicyPermission,
)


def make_profile(tenant_id=None, tenant_role=""):
    return SimpleNamespace(tenant_id=tenant_id, tenant_role=tenant_role)


def make_user(*, authenticated=True, profile=None, is_superuser=False, has_perm_return=False):
    calls = []

    def has_perm(perm):
        calls.append(perm)
        return has_perm_return

    user = SimpleNamespace(
        is_authenticated=authenticated,
        is_superuser=is_superuser,
        has_perm=has_perm,
    )
    user._has_perm_calls = calls
    if profile is not None:
        user.profile = profile
    return user


def make_request(user=None, method="GET"):
    return SimpleNamespace(user=user, method=method)


def make_view(action="", permission_scope=""):
    return SimpleNamespace(action=action, permission_scope=permission_scope)


@pytest.fixture
def permission():
    return RegionalPolicyPermission()


class TestModuleConstants:
    def test_permissions_registry_exact_membership(self):
        assert PERMISSIONS == [
            "regional.resource:create",
            "regional.resource:read",
            "regional.resource:update",
            "regional.resource:delete",
            "regional.resource:activate",
            "regional.resource:deactivate",
            "regional.configuration:read",
            "regional.configuration:write",
            "regional.configuration:rollback",
            "regional.configuration:import",
            "regional.configuration:export",
        ]

    def test_sod_actions_exact_membership(self):
        assert SOD_ACTIONS == [
            "regional.resource:create",
            "regional.resource:delete",
        ]


class TestClassLevelMappings:
    def test_resource_action_permissions_exact(self):
        assert RegionalPolicyPermission.resource_action_permissions == {
            "list": "regional.resource:read",
            "retrieve": "regional.resource:read",
            "create": "regional.resource:create",
            "update": "regional.resource:update",
            "partial_update": "regional.resource:update",
            "destroy": "regional.resource:delete",
            "restore": "regional.resource:update",
            "activate": "regional.resource:activate",
            "deactivate": "regional.resource:deactivate",
        }

    def test_configuration_action_permissions_exact(self):
        assert RegionalPolicyPermission.configuration_action_permissions == {
            "list": "regional.configuration:read",
            "current": "regional.configuration:read",
            "preview": "regional.configuration:write",
            "history": "regional.configuration:read",
            "rollback": "regional.configuration:rollback",
            "import_document": "regional.configuration:import",
            "export_document": "regional.configuration:export",
        }

    def test_message_text(self):
        assert RegionalPolicyPermission.message == "The required Regional permission was not granted."


class TestUnauthenticated:
    def test_user_none_denied(self, permission):
        request = make_request(user=None)
        assert permission.has_permission(request, make_view()) is False

    def test_user_missing_attribute_denied(self, permission):
        request = SimpleNamespace()
        assert permission.has_permission(request, make_view()) is False

    def test_user_not_authenticated_denied(self, permission):
        user = make_user(authenticated=False, profile=make_profile(tenant_id=str(uuid4())))
        request = make_request(user=user)
        assert permission.has_permission(request, make_view()) is False


class TestProfileResolution:
    def test_missing_profile_attribute_denied(self, permission):
        user = SimpleNamespace(is_authenticated=True)  # no .profile at all
        request = make_request(user=user)
        assert permission.has_permission(request, make_view()) is False

    def test_profile_raises_object_does_not_exist_denied(self, permission):
        from django.core.exceptions import ObjectDoesNotExist

        class RaisingUser:
            is_authenticated = True

            @property
            def profile(self):
                raise ObjectDoesNotExist("no profile")

        request = make_request(user=RaisingUser())
        assert permission.has_permission(request, make_view()) is False


class TestTenantIdCoercion:
    def test_valid_uuid_string_proceeds(self, permission):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="tenant_admin")
        user = make_user(profile=profile)
        request = make_request(user=user)
        view = make_view(action="list")
        assert permission.has_permission(request, view) is True

    def test_invalid_uuid_string_denied(self, permission):
        profile = make_profile(tenant_id="not-a-uuid", tenant_role="tenant_admin")
        user = make_user(profile=profile)
        request = make_request(user=user)
        view = make_view(action="list")
        assert permission.has_permission(request, view) is False

    def test_none_tenant_id_denied(self, permission):
        profile = make_profile(tenant_id=None, tenant_role="tenant_admin")
        user = make_user(profile=profile)
        request = make_request(user=user)
        view = make_view(action="list")
        assert permission.has_permission(request, view) is False

    def test_missing_tenant_id_attribute_denied(self, permission):
        profile = SimpleNamespace(tenant_role="tenant_admin")  # no tenant_id
        user = make_user(profile=profile)
        request = make_request(user=user)
        view = make_view(action="list")
        assert permission.has_permission(request, view) is False

    def test_empty_string_tenant_id_denied(self, permission):
        profile = make_profile(tenant_id="", tenant_role="tenant_admin")
        user = make_user(profile=profile)
        request = make_request(user=user)
        view = make_view(action="list")
        assert permission.has_permission(request, view) is False


class TestActionMapping:
    def test_resource_scope_used_by_default(self, permission):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="tenant_admin")
        user = make_user(profile=profile)
        request = make_request(user=user)
        # scope not "configuration" -> resource mapping; "current" isn't in it -> None -> denied
        view = make_view(action="current", permission_scope="")
        assert permission.has_permission(request, view) is False

    def test_resource_scope_explicit(self, permission):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="tenant_admin")
        user = make_user(profile=profile)
        request = make_request(user=user)
        view = make_view(action="create", permission_scope="resource")
        assert permission.has_permission(request, view) is True

    def test_configuration_scope_used(self, permission):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="tenant_admin")
        user = make_user(profile=profile)
        request = make_request(user=user)
        view = make_view(action="rollback", permission_scope="configuration")
        assert permission.has_permission(request, view) is True

    @pytest.mark.parametrize(
        "action,expected_permission",
        [
            ("list", "regional.resource:read"),
            ("retrieve", "regional.resource:read"),
            ("create", "regional.resource:create"),
            ("update", "regional.resource:update"),
            ("partial_update", "regional.resource:update"),
            ("destroy", "regional.resource:delete"),
            ("restore", "regional.resource:update"),
            ("activate", "regional.resource:activate"),
            ("deactivate", "regional.resource:deactivate"),
        ],
    )
    def test_every_resource_action_maps_and_delegates_to_has_perm(
        self, permission, action, expected_permission
    ):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="")
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user)
        view = make_view(action=action, permission_scope="resource")
        assert permission.has_permission(request, view) is True
        assert user._has_perm_calls == [expected_permission]

    @pytest.mark.parametrize(
        "action,expected_permission",
        [
            ("list", "regional.configuration:read"),
            ("history", "regional.configuration:read"),
            ("preview", "regional.configuration:write"),
            ("rollback", "regional.configuration:rollback"),
            ("import_document", "regional.configuration:import"),
            ("export_document", "regional.configuration:export"),
        ]
        ,
    )
    def test_every_configuration_action_maps_and_delegates_to_has_perm(
        self, permission, action, expected_permission
    ):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="")
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user)
        view = make_view(action=action, permission_scope="configuration")
        assert permission.has_permission(request, view) is True
        assert user._has_perm_calls == [expected_permission]

    def test_unmapped_action_fails_closed(self, permission):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="tenant_admin")
        user = make_user(profile=profile)
        request = make_request(user=user)
        view = make_view(action="totally_unknown_action", permission_scope="resource")
        assert permission.has_permission(request, view) is False

    def test_unmapped_configuration_action_fails_closed(self, permission):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="tenant_admin")
        user = make_user(profile=profile)
        request = make_request(user=user)
        view = make_view(action="totally_unknown_action", permission_scope="configuration")
        assert permission.has_permission(request, view) is False


class TestCurrentActionGetVsWriteSplit:
    def test_current_get_under_configuration_scope_uses_read_permission(self, permission):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="")
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user, method="GET")
        view = make_view(action="current", permission_scope="configuration")
        assert permission.has_permission(request, view) is True
        assert user._has_perm_calls == ["regional.configuration:read"]

    def test_current_lowercase_get_method_is_normalized_uppercase(self, permission):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="")
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user, method="get")
        view = make_view(action="current", permission_scope="configuration")
        assert permission.has_permission(request, view) is True
        assert user._has_perm_calls == ["regional.configuration:read"]

    def test_current_post_under_configuration_scope_uses_write_permission(self, permission):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="")
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user, method="POST")
        view = make_view(action="current", permission_scope="configuration")
        assert permission.has_permission(request, view) is True
        assert user._has_perm_calls == ["regional.configuration:write"]

    def test_current_put_under_configuration_scope_uses_write_permission(self, permission):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="")
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user, method="PUT")
        view = make_view(action="current", permission_scope="configuration")
        assert permission.has_permission(request, view) is True
        assert user._has_perm_calls == ["regional.configuration:write"]

    def test_current_missing_method_defaults_to_get(self, permission):
        """getattr(request, 'method', 'GET') default path."""
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="")
        user = make_user(profile=profile, has_perm_return=True)
        request = SimpleNamespace(user=user)  # no .method at all
        view = make_view(action="current", permission_scope="configuration")
        assert permission.has_permission(request, view) is True
        assert user._has_perm_calls == ["regional.configuration:read"]

    def test_current_under_resource_scope_is_unaffected_by_write_carveout(self, permission):
        """The GET/write carve-out only applies when permission_scope == 'configuration'."""
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="tenant_admin")
        user = make_user(profile=profile)
        request = make_request(user=user, method="POST")
        view = make_view(action="current", permission_scope="resource")
        # "current" is not in resource_action_permissions -> denied regardless of method
        assert permission.has_permission(request, view) is False


class TestPrivilegedRoleShortCircuit:
    @pytest.mark.parametrize("role", ["tenant_admin", "system_admin", "super_admin"])
    def test_privileged_roles_bypass_has_perm(self, permission, role):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role=role)
        user = make_user(profile=profile, has_perm_return=False)
        request = make_request(user=user)
        view = make_view(action="create", permission_scope="resource")
        assert permission.has_permission(request, view) is True
        # has_perm must never be called for privileged roles
        assert user._has_perm_calls == []

    def test_superuser_bypasses_has_perm_regardless_of_role(self, permission):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="")
        user = make_user(profile=profile, is_superuser=True, has_perm_return=False)
        request = make_request(user=user)
        view = make_view(action="create", permission_scope="resource")
        assert permission.has_permission(request, view) is True
        assert user._has_perm_calls == []

    def test_non_privileged_role_not_superuser_delegates_to_has_perm(self, permission):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="viewer")
        user = make_user(profile=profile, is_superuser=False, has_perm_return=False)
        request = make_request(user=user)
        view = make_view(action="create", permission_scope="resource")
        assert permission.has_permission(request, view) is False
        assert user._has_perm_calls == ["regional.resource:create"]

    def test_similar_but_not_exact_role_string_does_not_bypass(self, permission):
        """Proves exact-membership check, not substring/prefix matching."""
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="tenant_admin_readonly")
        user = make_user(profile=profile, is_superuser=False, has_perm_return=False)
        request = make_request(user=user)
        view = make_view(action="create", permission_scope="resource")
        assert permission.has_permission(request, view) is False
        assert user._has_perm_calls == ["regional.resource:create"]

    def test_missing_tenant_role_attribute_treated_as_empty_string(self, permission):
        profile = SimpleNamespace(tenant_id=str(uuid4()))  # no tenant_role
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user)
        view = make_view(action="create", permission_scope="resource")
        assert permission.has_permission(request, view) is True
        assert user._has_perm_calls == ["regional.resource:create"]

    def test_has_perm_true_grants_access_for_non_privileged_role(self, permission):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="viewer")
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user)
        view = make_view(action="retrieve", permission_scope="resource")
        assert permission.has_permission(request, view) is True

    def test_return_value_is_exact_bool_from_has_perm(self, permission):
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="viewer")
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user)
        view = make_view(action="retrieve", permission_scope="resource")
        result = permission.has_permission(request, view)
        assert result is True
        assert type(result) is bool


def _uninterned(value: str) -> str:
    """Build a string at runtime that is value-equal but NOT the same interned
    object as a same-spelled literal elsewhere (e.g. in permissions.py or in
    this test module). CPython auto-interns identifier-shaped string literals
    at compile time, so two modules using the literal "configuration" get the
    SAME object and `is` comparisons falsely pass. Building the string via a
    runtime join defeats that, letting tests distinguish `==` from `is`.
    """
    return "".join(ch for ch in value)


class TestMutationHardeningEqVsIsAndOrdering:
    """Kills survivors from `==` -> `<=`/`>=`/`is` mutation of the three
    string-equality comparisons on lines 70 (mapping selection), 75 (scope
    check inside the current/write carve-out) and 76 (action check inside
    that same carve-out).
    """

    def test_scope_less_than_configuration_lexically_falls_back_to_resource_mapping(
        self, permission
    ):
        """Kills `scope == 'configuration'` -> `scope <= 'configuration'` on
        line 75. A scope that sorts before "configuration" must NOT satisfy
        the write carve-out, even though `<=` would wrongly accept it."""
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="")
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user, method="POST")
        view = make_view(action="current", permission_scope="aaa")
        # scope != "configuration" -> resource mapping -> "current" unmapped -> deny
        assert permission.has_permission(request, view) is False

    def test_action_less_than_current_lexically_does_not_trigger_write_carveout(
        self, permission
    ):
        """Kills `action == 'current'` -> `action <= 'current'` on line 76."""
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="")
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user, method="POST")
        view = make_view(action="aaa", permission_scope="configuration")
        # action != "current" -> falls to mapping.get("aaa") -> unmapped -> deny
        assert permission.has_permission(request, view) is False

    def test_action_greater_than_current_lexically_does_not_trigger_write_carveout(
        self, permission
    ):
        """Kills `action == 'current'` -> `action >= 'current'` on line 76."""
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="")
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user, method="POST")
        view = make_view(action="current_extra", permission_scope="configuration")
        # "current_extra" != "current" -> falls to mapping.get(...) -> unmapped -> deny
        assert permission.has_permission(request, view) is False

    def test_mapping_selection_uses_value_equality_not_identity(self, permission):
        """Kills `scope == 'configuration'` -> `scope is 'configuration'` on
        line 70. A runtime-built, non-interned scope string that is
        value-equal to "configuration" must still select the configuration
        mapping."""
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="")
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user)
        scope = _uninterned("configuration")
        assert scope is not "configuration"  # noqa: F632 - deliberately proving non-identity
        view = make_view(action="list", permission_scope=scope)
        assert permission.has_permission(request, view) is True
        assert user._has_perm_calls == ["regional.configuration:read"]

    def test_action_current_check_uses_value_equality_not_identity(self, permission):
        """Kills `action == 'current'` -> `action is 'current'` on line 76.
        A runtime-built, non-interned action string equal to "current" must
        still trigger the write carve-out under POST."""
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="")
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user, method="POST")
        action = _uninterned("current")
        assert action is not "current"  # noqa: F632 - deliberately proving non-identity
        view = make_view(action=action, permission_scope="configuration")
        assert permission.has_permission(request, view) is True
        assert user._has_perm_calls == ["regional.configuration:write"]


    def test_write_carveout_scope_check_uses_value_equality_not_identity(self, permission):
        """Kills `scope == 'configuration'` -> `scope is 'configuration'` on
        line 75 specifically (the first clause of the write carve-out `if`).
        A runtime-built, non-interned scope string equal to "configuration"
        must still trigger the write carve-out under POST + action=current."""
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="")
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user, method="POST")
        scope = _uninterned("configuration")
        assert scope is not "configuration"  # noqa: F632 - deliberately proving non-identity
        view = make_view(action="current", permission_scope=scope)
        assert permission.has_permission(request, view) is True
        assert user._has_perm_calls == ["regional.configuration:write"]

    def test_method_lexically_before_get_is_still_treated_as_non_get(self, permission):
        """Kills `method.upper() != 'GET'` -> `method.upper() > 'GET'` on
        line 77. "DELETE" sorts before "GET" lexically, so `> "GET"` is
        False even though the method plainly is not GET; the write
        carve-out must still fire."""
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="")
        user = make_user(profile=profile, has_perm_return=True)
        request = make_request(user=user, method="DELETE")
        view = make_view(action="current", permission_scope="configuration")
        assert permission.has_permission(request, view) is True
        assert user._has_perm_calls == ["regional.configuration:write"]


class TestMutationHardeningSuperuserDefault:
    def test_missing_is_superuser_attribute_defaults_to_false_not_true(self, permission):
        """Kills `getattr(user, 'is_superuser', False)` -> default `True` on
        line 85. A user object entirely lacking `is_superuser` must NOT be
        treated as a superuser."""
        profile = make_profile(tenant_id=str(uuid4()), tenant_role="viewer")

        def has_perm(_perm):
            return False

        user = SimpleNamespace(is_authenticated=True, profile=profile, has_perm=has_perm)
        assert not hasattr(user, "is_superuser")
        request = make_request(user=user)
        view = make_view(action="create", permission_scope="resource")
        assert permission.has_permission(request, view) is False


class TestIsInstance:
    def test_is_instance_of_base_permission(self):
        from rest_framework.permissions import BasePermission

        assert isinstance(RegionalPolicyPermission(), BasePermission)
