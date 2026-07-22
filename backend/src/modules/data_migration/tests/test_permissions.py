"""Fail-closed authorization metadata tests for data migration v2."""

from types import SimpleNamespace
from uuid import uuid4

from src.core.access.permissions import RequiresAccess
from src.modules.data_migration.permissions import (
    CONNECTION_ACTION_PERMISSIONS,
    CORE_ENTITLEMENT,
    JOB_ACTION_PERMISSIONS,
    MAPPING_ACTION_PERMISSIONS,
    PERMISSIONS,
    ROLLBACK_ACTION_PERMISSIONS,
    RULE_ACTION_PERMISSIONS,
    RUN_ACTION_PERMISSIONS,
    ActionAccessMixin,
    is_platform_operator,
)


def test_permission_catalog_is_exact_and_has_no_generic_resource_shortcut() -> None:
    assert set(PERMISSIONS) == {
        "data_migration.job:read", "data_migration.job:create", "data_migration.job:update",
        "data_migration.job:delete", "data_migration.job:export", "data_migration.job:import",
        "data_migration.mapping:manage", "data_migration.rule:manage", "data_migration.source:preview",
        "data_migration.run:execute", "data_migration.run:cancel", "data_migration.rollback:execute",
        "data_migration.connection:read", "data_migration.connection:manage", "data_migration.connection:test",
    }
    assert not any("resource:" in permission for permission in PERMISSIONS)


def test_every_declared_action_maps_to_catalog_permission() -> None:
    for mapping in (
        JOB_ACTION_PERMISSIONS, MAPPING_ACTION_PERMISSIONS, RULE_ACTION_PERMISSIONS,
        RUN_ACTION_PERMISSIONS, ROLLBACK_ACTION_PERMISSIONS, CONNECTION_ACTION_PERMISSIONS,
    ):
        assert set(mapping.values()) <= set(PERMISSIONS)


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
