"""Forward/reverse migration oracles for the security authorization schema."""

from __future__ import annotations

import importlib
import inspect
import json
import uuid

import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = pytest.mark.django_db(transaction=True)

LEGACY = ("security_access_control", "0001_initial")
TENANT_FIELDS = ("security_access_control", "0002_add_tenant_and_audit_fields")
NORMALIZED = ("security_access_control", "0003_normalize_permission_sets")
SAFE_PREDICATES = ("security_access_control", "0004_safe_row_rule_predicates")
LATEST = ("security_access_control", "0006_enforce_audit_immutability")


def migrate(target: tuple[str, str]):
    executor = MigrationExecutor(connection)
    executor.migrate([target])
    return executor.loader.project_state([target]).apps


def user_model(apps):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".", 1)
    return apps.get_model(app_label, model_name)


def create_legacy_fixture(apps) -> dict[str, object]:
    User = user_model(apps)
    Role = apps.get_model("security_access_control", "Role")
    Permission = apps.get_model("security_access_control", "Permission")
    RolePermission = apps.get_model("security_access_control", "RolePermission")
    UserRole = apps.get_model("security_access_control", "UserRole")
    PermissionSet = apps.get_model("security_access_control", "PermissionSet")
    UserPermissionSet = apps.get_model("security_access_control", "UserPermissionSet")
    RowSecurityRule = apps.get_model("security_access_control", "RowSecurityRule")
    SecurityAuditLog = apps.get_model("security_access_control", "SecurityAuditLog")
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    user = User.objects.create(username=f"migration-{uuid.uuid4().hex}")
    role = Role.objects.create(tenant_id=tenant_id, name="Legacy analyst", code="legacy_analyst")
    permission = Permission.objects.create(module="sales", object="orders", action="read", name="Read orders")
    RolePermission.objects.create(role_id=role.id, permission_id=permission.id, is_granted=True)
    UserRole.objects.create(user_id=user.pk, role_id=role.id, assigned_by=actor_id, reason="Legacy assignment")
    permission_set = PermissionSet.objects.create(
        tenant_id=tenant_id,
        name="Legacy close",
        permission_ids=[str(permission.id)],
        default_duration_days=7,
        created_by=actor_id,
    )
    grant = UserPermissionSet.objects.create(
        user_id=user.pk,
        permission_set_id=permission_set.id,
        expires_at=timezone.now() + timezone.timedelta(days=7),
        granted_by=actor_id,
        reason="Legacy grant",
    )
    predicate = {"op": "eq", "field": "owner_id", "value": {"subject": "id"}}
    row_rule = RowSecurityRule.objects.create(
        tenant_id=tenant_id,
        module="sales",
        object="orders",
        role_id=role.id,
        rule_type="criteria",
        filter_criteria=json.dumps(predicate, sort_keys=True),
    )
    audit = SecurityAuditLog.objects.create(
        tenant_id=tenant_id,
        action="security.legacy.imported",
        actor_id=actor_id,
        resource_type="role",
        resource_id=role.id,
        reason_codes=["legacy_migration_fixture"],
        details={"safe": True},
    )
    return {
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "user_id": user.pk,
        "role_id": role.id,
        "permission_id": permission.id,
        "permission_set_id": permission_set.id,
        "grant_id": grant.id,
        "row_rule_id": row_rule.id,
        "audit_id": audit.id,
        "predicate": predicate,
    }


def test_forward_reverse_forward_preserves_normalized_security_data() -> None:
    legacy_apps = migrate(LEGACY)
    fixture = create_legacy_fixture(legacy_apps)

    latest_apps = migrate(LATEST)
    Permission = latest_apps.get_model("security_access_control", "Permission")
    Membership = latest_apps.get_model("security_access_control", "PermissionSetPermission")
    UserGrant = latest_apps.get_model("security_access_control", "UserPermissionSet")
    RowRule = latest_apps.get_model("security_access_control", "RowSecurityRule")
    Audit = latest_apps.get_model("security_access_control", "SecurityAuditLog")
    permission = Permission.objects.get(pk=fixture["permission_id"])
    membership = Membership.objects.get(permission_set_id=fixture["permission_set_id"])
    assert permission.resource == "orders" and permission.risk_level == "medium"
    assert membership.tenant_id == fixture["tenant_id"]
    assert membership.permission_id == fixture["permission_id"]
    assert UserGrant.objects.get(pk=fixture["grant_id"]).tenant_id == fixture["tenant_id"]
    assert RowRule.objects.get(pk=fixture["row_rule_id"]).filter_criteria == fixture["predicate"]
    audit = Audit.objects.get(pk=fixture["audit_id"])
    assert audit.tenant_id == fixture["tenant_id"]
    assert audit.correlation_id == f"legacy-migration:{fixture['audit_id']}"

    reversed_apps = migrate(LEGACY)
    LegacyPermission = reversed_apps.get_model("security_access_control", "Permission")
    LegacyPermissionSet = reversed_apps.get_model("security_access_control", "PermissionSet")
    LegacyRowRule = reversed_apps.get_model("security_access_control", "RowSecurityRule")
    assert LegacyPermission.objects.get(pk=fixture["permission_id"]).object == "orders"
    assert LegacyPermissionSet.objects.get(pk=fixture["permission_set_id"]).permission_ids == [
        str(fixture["permission_id"])
    ]
    assert json.loads(LegacyRowRule.objects.get(pk=fixture["row_rule_id"]).filter_criteria) == fixture["predicate"]

    latest_apps = migrate(LATEST)
    Membership = latest_apps.get_model("security_access_control", "PermissionSetPermission")
    RowRule = latest_apps.get_model("security_access_control", "RowSecurityRule")
    assert Membership.objects.filter(permission_set_id=fixture["permission_set_id"]).count() == 1
    assert RowRule.objects.get(pk=fixture["row_rule_id"]).filter_criteria == fixture["predicate"]


@pytest.mark.parametrize("legacy_value", ["not-a-list", ["not-a-uuid"], [123]])
def test_permission_normalization_stops_on_malformed_legacy_data(legacy_value: object) -> None:
    apps = migrate(TENANT_FIELDS)
    PermissionSet = apps.get_model("security_access_control", "PermissionSet")
    PermissionSet.objects.create(tenant_id=uuid.uuid4(), name="Malformed", permission_ids=legacy_value)
    with pytest.raises(RuntimeError, match="PermissionSet"):
        migrate(NORMALIZED)


def test_permission_normalization_stops_on_unknown_and_duplicate_ids() -> None:
    for value in ([str(uuid.uuid4())], None):
        apps = migrate(TENANT_FIELDS)
        Permission = apps.get_model("security_access_control", "Permission")
        PermissionSet = apps.get_model("security_access_control", "PermissionSet")
        if value is None:
            permission = Permission.objects.create(module="m", resource="r", action="a")
            value = [str(permission.id), str(permission.id)]
        PermissionSet.objects.create(tenant_id=uuid.uuid4(), name=f"Invalid-{uuid.uuid4()}", permission_ids=value)
        with pytest.raises(RuntimeError, match="unknown|duplicate"):
            migrate(NORMALIZED)


@pytest.mark.parametrize(
    "unsafe",
    [
        "owner_id = current_user",
        '{"op":"raw_sql","value":"TRUE"}',
        '{"op":"eq","field":"owner_id__in","value":"${subject.id}"}',
        '{"op":"and","args":[]}',
    ],
)
def test_row_predicate_migration_stops_and_reports_unsafe_record(unsafe: str) -> None:
    apps = migrate(NORMALIZED)
    Role = apps.get_model("security_access_control", "Role")
    RowRule = apps.get_model("security_access_control", "RowSecurityRule")
    tenant_id = uuid.uuid4()
    role = Role.objects.create(tenant_id=tenant_id, name="Unsafe", code=f"unsafe_{uuid.uuid4().hex}")
    rule = RowRule.objects.create(
        tenant_id=tenant_id,
        module="sales",
        resource="orders",
        role_id=role.id,
        filter_criteria=unsafe,
    )
    with pytest.raises(RuntimeError, match=str(rule.id)):
        migrate(SAFE_PREDICATES)


def test_tenant_backfill_aborts_for_null_audit_and_cross_tenant_relationship() -> None:
    apps = migrate(LEGACY)
    Audit = apps.get_model("security_access_control", "SecurityAuditLog")
    Audit.objects.create(
        tenant_id=None,
        action="unattributed",
        actor_id=uuid.uuid4(),
        resource_type="unknown",
    )
    with pytest.raises(RuntimeError, match="tenant-null"):
        migrate(TENANT_FIELDS)

    apps = migrate(LEGACY)
    Role = apps.get_model("security_access_control", "Role")
    FieldRule = apps.get_model("security_access_control", "FieldSecurity")
    role = Role.objects.create(tenant_id=uuid.uuid4(), name="Foreign", code="foreign")
    rule = FieldRule.objects.create(
        tenant_id=uuid.uuid4(), module="sales", object="orders", field="total", role_id=role.id
    )
    with pytest.raises(RuntimeError, match=str(rule.id)):
        migrate(TENANT_FIELDS)


def test_migration_contract_is_reversible_concurrent_and_covers_every_tenant_table() -> None:
    m2 = importlib.import_module(
        "src.modules.security_access_control.migrations.0002_add_tenant_and_audit_fields"
    )
    m3 = importlib.import_module("src.modules.security_access_control.migrations.0003_normalize_permission_sets")
    m4 = importlib.import_module("src.modules.security_access_control.migrations.0004_safe_row_rule_predicates")
    m5 = importlib.import_module("src.modules.security_access_control.migrations.0005_constraints_indexes_rls")
    m6 = importlib.import_module("src.modules.security_access_control.migrations.0006_enforce_audit_immutability")
    assert m5.Migration.atomic is False
    assert len(m5.TENANT_TABLES) == 11 and "security_permissions" not in m5.TENANT_TABLES
    assert "CONCURRENTLY" in inspect.getsource(m5.create_concurrent_indexes)
    assert len(m5.COMPOSITE_FOREIGN_KEYS) == 9
    assert all(operation.reverse_code is not None for operation in [m2.Migration.operations[-5], m3.Migration.operations[-1], m4.Migration.operations[-2], m6.Migration.operations[-1]])
    assert json.dumps(sorted(m5.TENANT_TABLES))
