"""Fail-closed authorization metadata tests for data migration v2."""

from types import SimpleNamespace
from uuid import UUID, uuid4

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.modules.data_migration.permissions import (
    CONFIGURATION_ACTION_PERMISSIONS,
    CONFIGURATION_MANAGE,
    CONFIGURATION_READ,
    CONNECTION_ACTION_PERMISSIONS,
    CORE_ENTITLEMENT,
    JOB_ACTION_PERMISSIONS,
    JOB_READ,
    JOB_UPDATE,
    MAPPING_ACTION_PERMISSIONS,
    PERMISSIONS,
    ROLLBACK_ACTION_PERMISSIONS,
    RULE_ACTION_PERMISSIONS,
    RUN_ACTION_PERMISSIONS,
    ActionAccessMixin,
    SessionAuthentication401,
    is_platform_operator,
)


def test_permission_catalog_is_exact_and_has_no_generic_resource_shortcut() -> None:
    assert set(PERMISSIONS) == {
        "data_migration.job:read",
        "data_migration.job:create",
        "data_migration.job:update",
        "data_migration.job:delete",
        "data_migration.job:export",
        "data_migration.job:import",
        "data_migration.mapping:manage",
        "data_migration.rule:manage",
        "data_migration.source:preview",
        "data_migration.run:execute",
        "data_migration.run:cancel",
        "data_migration.rollback:execute",
        "data_migration.connection:read",
        "data_migration.connection:manage",
        "data_migration.connection:test",
    }
    assert not any("resource:" in permission for permission in PERMISSIONS)


def test_every_declared_action_maps_to_catalog_permission() -> None:
    for mapping in (
        JOB_ACTION_PERMISSIONS,
        MAPPING_ACTION_PERMISSIONS,
        RULE_ACTION_PERMISSIONS,
        RUN_ACTION_PERMISSIONS,
        ROLLBACK_ACTION_PERMISSIONS,
        CONNECTION_ACTION_PERMISSIONS,
    ):
        assert set(mapping.values()) <= set(PERMISSIONS)


def test_configuration_action_permissions_alias_job_catalog_exactly() -> None:
    assert CONFIGURATION_READ == JOB_READ
    assert CONFIGURATION_MANAGE == JOB_UPDATE
    assert CONFIGURATION_ACTION_PERMISSIONS == {
        "retrieve_configuration": CONFIGURATION_READ,
        "update_configuration": CONFIGURATION_MANAGE,
        "preview_configuration": CONFIGURATION_MANAGE,
        "configuration_versions": CONFIGURATION_READ,
        "restore_configuration": CONFIGURATION_MANAGE,
        "import_configuration": CONFIGURATION_MANAGE,
        "export_configuration": CONFIGURATION_READ,
    }


def test_job_action_permissions_pin_exact_mapping() -> None:
    assert JOB_ACTION_PERMISSIONS == {
        "list": "data_migration.job:read",
        "retrieve": "data_migration.job:read",
        "create": "data_migration.job:create",
        "partial_update": "data_migration.job:update",
        "destroy": "data_migration.job:delete",
        "validate_definition": "data_migration.job:update",
        "archive": "data_migration.job:update",
        "restore": "data_migration.job:update",
        "attach_source": "data_migration.job:update",
        "inspect": "data_migration.source:preview",
        "preview": "data_migration.source:preview",
        "export_definition": "data_migration.job:export",
        "import_definition": "data_migration.job:import",
        "versions": "data_migration.job:read",
        "restore_version": "data_migration.job:update",
        "mappings": "data_migration.job:read",
        "create_mapping": "data_migration.mapping:manage",
        "suggest_mappings": "data_migration.mapping:manage",
        "apply_mappings": "data_migration.mapping:manage",
        "validation_rules": "data_migration.job:read",
        "create_validation_rule": "data_migration.rule:manage",
        "runs": "data_migration.job:read",
        "request_run": "data_migration.run:execute",
        "request_dry_run": "data_migration.run:execute",
    }


def test_mapping_rule_run_rollback_connection_action_permissions_pin_exact_mapping() -> None:
    assert MAPPING_ACTION_PERMISSIONS == {
        "retrieve": "data_migration.job:read",
        "partial_update": "data_migration.mapping:manage",
        "destroy": "data_migration.mapping:manage",
    }
    assert RULE_ACTION_PERMISSIONS == {
        "retrieve": "data_migration.job:read",
        "partial_update": "data_migration.rule:manage",
        "destroy": "data_migration.rule:manage",
    }
    assert RUN_ACTION_PERMISSIONS == {
        "retrieve": "data_migration.job:read",
        "issues": "data_migration.job:read",
        "export_issues": "data_migration.job:read",
        "cancel": "data_migration.run:cancel",
        "rollback": "data_migration.rollback:execute",
    }
    assert ROLLBACK_ACTION_PERMISSIONS == {"retrieve": "data_migration.job:read"}
    assert CONNECTION_ACTION_PERMISSIONS == {
        "list": "data_migration.connection:read",
        "retrieve": "data_migration.connection:read",
        "create": "data_migration.connection:manage",
        "partial_update": "data_migration.connection:manage",
        "deactivate": "data_migration.connection:manage",
        "rotate_credential": "data_migration.connection:manage",
        "test_connection": "data_migration.connection:test",
    }


def test_session_authentication_401_always_challenges_with_session_header() -> None:
    auth = SessionAuthentication401()
    assert auth.authenticate_header(request=object()) == "Session"
    assert auth.authenticate_header(request=None) == "Session"


def test_undeclared_action_denies_by_leaving_access_metadata_empty() -> None:
    boundary = ActionAccessMixin()
    boundary.action = "unexpected"
    boundary.request = SimpleNamespace(
        method="POST",
        user=SimpleNamespace(is_authenticated=True, profile=SimpleNamespace(tenant_id=uuid4())),
    )
    permissions = boundary.get_permissions()
    assert isinstance(permissions[-1], RequiresAccess)
    assert boundary.required_permission is None
    assert boundary.required_entitlement is None


def test_known_action_binds_core_entitlement_and_authenticated_tenant() -> None:
    tenant = uuid4()
    boundary = ActionAccessMixin()
    boundary.action_permissions = {"create": "data_migration.job:create"}
    boundary.action = "create"
    boundary.request = SimpleNamespace(
        method="POST",
        user=SimpleNamespace(is_authenticated=True, profile=SimpleNamespace(tenant_id=tenant)),
    )
    boundary.get_permissions()
    assert boundary.required_permission == "data_migration.job:create"
    assert boundary.required_entitlement == CORE_ENTITLEMENT
    assert boundary.request.tenant_id == tenant


def test_operator_detection_is_additional_and_never_tenant_admin_shortcut() -> None:
    assert not is_platform_operator(SimpleNamespace(is_authenticated=True, roles=("tenant_admin",), is_superuser=False))
    assert is_platform_operator(SimpleNamespace(is_authenticated=True, roles=("system_admin",), is_superuser=False))
    assert not is_platform_operator(SimpleNamespace(is_authenticated=False))


def test_operator_detection_denies_falsy_or_missing_user() -> None:
    assert not is_platform_operator(None)
    assert not is_platform_operator(False)


def test_operator_detection_grants_superuser_without_role_or_group() -> None:
    assert is_platform_operator(SimpleNamespace(is_authenticated=True, is_superuser=True, roles=()))


def test_operator_detection_grants_platform_owner_and_platform_operator_roles(monkeypatch) -> None:
    from src.modules.data_migration import permissions as permissions_module

    for role in ("platform_owner", "platform_operator"):
        monkeypatch.setattr(permissions_module, "get_user_platform_role", lambda user, role=role: role)
        user = SimpleNamespace(is_authenticated=True, is_superuser=False, roles=())
        assert is_platform_operator(user)

    monkeypatch.setattr(permissions_module, "get_user_platform_role", lambda user: "tenant_owner")
    denied_user = SimpleNamespace(is_authenticated=True, is_superuser=False, roles=())
    assert not is_platform_operator(denied_user)


def test_operator_detection_grants_super_admin_role_alongside_system_admin() -> None:
    assert is_platform_operator(SimpleNamespace(is_authenticated=True, is_superuser=False, roles=("super_admin",)))


def test_operator_detection_defaults_missing_roles_attribute_to_empty_set() -> None:
    assert not is_platform_operator(SimpleNamespace(is_authenticated=True, is_superuser=False))


def test_get_permissions_accepts_tenant_id_already_typed_as_uuid() -> None:
    tenant = uuid4()
    boundary = ActionAccessMixin()
    boundary.action_permissions = {"retrieve": "data_migration.job:read"}
    boundary.action = "retrieve"
    boundary.request = SimpleNamespace(
        method="GET",
        user=SimpleNamespace(is_authenticated=True, profile=SimpleNamespace(tenant_id=tenant)),
    )
    boundary.get_permissions()
    assert boundary.request.tenant_id == tenant
    assert isinstance(boundary.request.tenant_id, UUID)


def test_get_permissions_coerces_string_tenant_id_to_uuid() -> None:
    tenant = uuid4()
    boundary = ActionAccessMixin()
    boundary.action = "retrieve"
    boundary.request = SimpleNamespace(
        method="GET",
        user=SimpleNamespace(is_authenticated=True, profile=SimpleNamespace(tenant_id=str(tenant))),
    )
    boundary.get_permissions()
    assert boundary.request.tenant_id == tenant


def test_get_permissions_denies_tenant_id_on_malformed_string() -> None:
    boundary = ActionAccessMixin()
    boundary.action = "retrieve"
    boundary.request = SimpleNamespace(
        method="GET",
        user=SimpleNamespace(is_authenticated=True, profile=SimpleNamespace(tenant_id="not-a-uuid")),
    )
    boundary.get_permissions()
    assert boundary.request.tenant_id is None


def test_get_permissions_leaves_tenant_id_none_when_user_has_no_profile() -> None:
    boundary = ActionAccessMixin()
    boundary.action = "retrieve"
    boundary.request = SimpleNamespace(method="GET", user=SimpleNamespace(is_authenticated=True))
    boundary.get_permissions()
    assert boundary.request.tenant_id is None


def test_get_permissions_prefers_method_permissions_over_action_permissions() -> None:
    boundary = ActionAccessMixin()
    boundary.action_permissions = {"custom": "data_migration.job:read"}
    boundary.method_permissions = {"custom": {"POST": "data_migration.job:create"}}
    boundary.action = "custom"
    boundary.request = SimpleNamespace(
        method="POST",
        user=SimpleNamespace(is_authenticated=True, profile=SimpleNamespace(tenant_id=uuid4())),
    )
    boundary.get_permissions()
    assert boundary.required_permission == "data_migration.job:create"


def test_get_permissions_falls_back_to_action_permissions_when_method_unmatched() -> None:
    boundary = ActionAccessMixin()
    boundary.action_permissions = {"custom": "data_migration.job:read"}
    boundary.method_permissions = {"custom": {"POST": "data_migration.job:create"}}
    boundary.action = "custom"
    boundary.request = SimpleNamespace(
        method="get",
        user=SimpleNamespace(is_authenticated=True, profile=SimpleNamespace(tenant_id=uuid4())),
    )
    boundary.get_permissions()
    assert boundary.required_permission == "data_migration.job:read"


def test_get_permissions_binds_quota_resource_from_action_quotas() -> None:
    boundary = ActionAccessMixin()
    boundary.action_permissions = {"request_run": "data_migration.run:execute"}
    boundary.action_quotas = {"request_run": "data_migration.job.run"}
    boundary.action = "request_run"
    boundary.request = SimpleNamespace(
        method="POST",
        user=SimpleNamespace(is_authenticated=True, profile=SimpleNamespace(tenant_id=uuid4())),
    )
    boundary.get_permissions()
    assert boundary.quota_resource == "data_migration.job.run"


def test_get_permissions_leaves_quota_resource_none_for_unlisted_action() -> None:
    boundary = ActionAccessMixin()
    boundary.action_permissions = {"list": "data_migration.job:read"}
    boundary.action = "list"
    boundary.request = SimpleNamespace(
        method="GET",
        user=SimpleNamespace(is_authenticated=True, profile=SimpleNamespace(tenant_id=uuid4())),
    )
    boundary.get_permissions()
    assert boundary.quota_resource is None


def test_get_permissions_defaults_action_to_empty_string_when_unset() -> None:
    boundary = ActionAccessMixin()
    boundary.request = SimpleNamespace(
        method="GET",
        user=SimpleNamespace(is_authenticated=True, profile=SimpleNamespace(tenant_id=uuid4())),
    )
    boundary.get_permissions()
    assert boundary.required_permission is None
    assert boundary.quota_resource is None


def test_default_quota_cost_is_one() -> None:
    assert ActionAccessMixin.quota_cost == 1


def test_mixin_declares_exact_default_class_level_policy_metadata() -> None:
    assert ActionAccessMixin.authentication_classes == (SessionAuthentication401,)
    assert ActionAccessMixin.authentication_classes != (SessionAuthentication,)
    assert ActionAccessMixin.permission_classes == (IsAuthenticated, RequiresAccess)
    assert ActionAccessMixin.action_permissions == {}
    assert ActionAccessMixin.method_permissions == {}
    assert ActionAccessMixin.action_quotas == {}


def test_get_permissions_matches_method_permissions_via_uppercased_method() -> None:
    boundary = ActionAccessMixin()
    boundary.method_permissions = {"custom": {"POST": "data_migration.job:create"}}
    boundary.action = "custom"
    boundary.request = SimpleNamespace(
        method="post",
        user=SimpleNamespace(is_authenticated=True, profile=SimpleNamespace(tenant_id=uuid4())),
    )
    boundary.get_permissions()
    assert boundary.required_permission == "data_migration.job:create"


def test_get_permissions_returns_isauthenticated_and_requiresaccess_instances() -> None:
    boundary = ActionAccessMixin()
    boundary.action = "retrieve"
    boundary.request = SimpleNamespace(
        method="GET",
        user=SimpleNamespace(is_authenticated=True, profile=SimpleNamespace(tenant_id=uuid4())),
    )
    permissions = boundary.get_permissions()
    assert len(permissions) == 2
    assert isinstance(permissions[0], IsAuthenticated)
    assert isinstance(permissions[1], RequiresAccess)


def test_operator_detection_denies_user_missing_is_authenticated_attribute_even_if_superuser() -> None:
    # Fail-closed: a missing `is_authenticated` attribute must default to "not
    # authenticated" and short-circuit deny, even when another grant condition
    # (superuser) would otherwise pass. This distinguishes the real getattr
    # default (False) from a flipped default (True).
    assert not is_platform_operator(SimpleNamespace(is_superuser=True, roles=()))


def test_operator_detection_denies_explicitly_unauthenticated_user_even_if_superuser() -> None:
    # Same fail-closed guarantee with `is_authenticated` explicitly False
    # rather than absent — this is what distinguishes the short-circuit `or`
    # from a mutated `and`.
    assert not is_platform_operator(SimpleNamespace(is_authenticated=False, is_superuser=True, roles=()))


def test_operator_detection_denies_missing_is_superuser_attribute_with_no_other_grant() -> None:
    # Fail-closed: a missing `is_superuser` attribute must default to False,
    # not True, when no other grant condition (role, group) applies.
    assert not is_platform_operator(SimpleNamespace(is_authenticated=True, roles=()))


def test_operator_detection_denies_explicitly_none_roles() -> None:
    assert not is_platform_operator(SimpleNamespace(is_authenticated=True, is_superuser=False, roles=None))
