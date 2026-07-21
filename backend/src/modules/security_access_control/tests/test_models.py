"""Domain-model invariants for tenant-owned authorization data."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone

from src.modules.security_access_control.models import (
    FieldSecurity,
    ImmutableAuditError,
    Permission,
    PermissionSet,
    PermissionSetPermission,
    Role,
    RolePermission,
    RowSecurityRule,
    SecurityAuditLog,
    SecurityProfile,
    SecurityProfileAssignment,
    UserPermissionSet,
    UserRole,
)

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db


@pytest.fixture
def actor_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def role(tenant_a, actor_id) -> Role:
    return Role.objects.create(
        tenant_id=tenant_a.id,
        name="Finance Analyst",
        code="finance_analyst",
        role_type=Role.RoleType.FUNCTIONAL,
        created_by=actor_id,
        updated_by=actor_id,
    )


@pytest.fixture
def permission() -> Permission:
    return Permission.objects.create(
        module="finance", resource="journals", action="read", name="Read journals"
    )


def test_permission_catalog_defaults_code_enums_uniqueness_and_string(permission: Permission) -> None:
    assert permission.risk_level == Permission.RiskLevel.MEDIUM
    assert permission.code == "finance.journals:read"
    assert str(permission) == permission.code
    assert set(Permission.RiskLevel.values) == {"low", "medium", "high", "critical"}
    with pytest.raises(IntegrityError), transaction.atomic():
        Permission.objects.create(
            module="finance", resource="journals", action="read", name="Duplicate"
        )


def test_role_defaults_string_soft_delete_uniqueness_and_relationship_validation(
    tenant_a, tenant_b, role: Role
) -> None:
    assert str(role) == "Finance Analyst (finance_analyst)"
    assert role.is_active and not role.is_system and not role.is_deleted
    assert role.hierarchy_level == 0 and role.deleted_at is None
    assert set(Role.RoleType.values) == {"system", "functional", "custom", "temporary"}
    with pytest.raises(IntegrityError), transaction.atomic():
        Role.objects.create(tenant_id=tenant_a.id, name="Duplicate", code=role.code)
    other = Role.objects.create(tenant_id=tenant_b.id, name="Same code", code=role.code)
    child = Role(tenant_id=tenant_a.id, name="Child", code="child", parent_role=other)
    with pytest.raises(ValidationError, match="Parent role"):
        child.full_clean()
    child.parent_role = role
    child.hierarchy_level = 1
    child.full_clean()


def test_role_cycle_self_parent_and_depth_are_rejected(tenant_a) -> None:
    root = Role.objects.create(tenant_id=tenant_a.id, name="Root", code="root")
    root.parent_role = root
    with pytest.raises(ValidationError, match="cycle"):
        root.full_clean()
    parent = Role.objects.create(tenant_id=tenant_a.id, name="L0", code="level_0")
    for number in range(1, 17):
        parent = Role.objects.create(
            tenant_id=tenant_a.id,
            name=f"L{number}",
            code=f"level_{number}",
            parent_role=parent,
            hierarchy_level=number,
        )
    too_deep = Role(
        tenant_id=tenant_a.id,
        name="Too deep",
        code="too_deep",
        parent_role=parent,
        hierarchy_level=17,
    )
    with pytest.raises(ValidationError, match="16 levels"):
        too_deep.full_clean()


def test_explicit_role_decision_defaults_string_uniqueness_and_tenant_match(
    tenant_a, tenant_b, role: Role, permission: Permission
) -> None:
    decision = RolePermission.objects.create(
        tenant_id=tenant_a.id, role=role, permission=permission
    )
    assert decision.is_granted is True and "allow" in str(decision)
    with pytest.raises(IntegrityError), transaction.atomic():
        RolePermission.objects.create(
            tenant_id=tenant_a.id, role=role, permission=permission, is_granted=False
        )
    cross = RolePermission(tenant_id=tenant_b.id, role=role, permission=permission)
    with pytest.raises(ValidationError, match="Role must belong"):
        cross.full_clean()


def test_user_role_temporal_states_constraints_reason_and_tenant_match(
    tenant_a, tenant_b, tenant_a_user, role: Role, actor_id
) -> None:
    assignment = UserRole.objects.create(
        tenant_id=tenant_a.id,
        user=tenant_a_user,
        role=role,
        assigned_by=actor_id,
        reason="Quarter-end duties",
    )
    assert assignment.is_active and str(tenant_a_user.id) in str(assignment)
    assignment.revoked_at = timezone.now()
    assert not assignment.is_active
    invalid = UserRole(
        tenant_id=tenant_b.id,
        user=tenant_a_user,
        role=role,
        assigned_by=actor_id,
        reason="",
        valid_until=timezone.now() - timedelta(seconds=1),
    )
    with pytest.raises(ValidationError):
        invalid.full_clean()


def test_permission_set_membership_and_grant_defaults_constraints(
    tenant_a, tenant_b, tenant_a_user, permission: Permission, actor_id
) -> None:
    permission_set = PermissionSet.objects.create(
        tenant_id=tenant_a.id,
        name="Quarter close",
        default_duration_days=14,
        created_by=actor_id,
        updated_by=actor_id,
    )
    assert str(permission_set) == "Quarter close"
    assert permission_set.is_active and not permission_set.is_deleted
    membership = PermissionSetPermission.objects.create(
        tenant_id=tenant_a.id,
        permission_set=permission_set,
        permission=permission,
        added_by=actor_id,
    )
    assert membership.removed_at is None
    with pytest.raises(ValidationError, match="Permission set must belong"):
        PermissionSetPermission(
            tenant_id=tenant_b.id,
            permission_set=permission_set,
            permission=permission,
            added_by=actor_id,
        ).full_clean()
    grant = UserPermissionSet.objects.create(
        tenant_id=tenant_a.id,
        user=tenant_a_user,
        permission_set=permission_set,
        expires_at=timezone.now() + timedelta(days=14),
        granted_by=actor_id,
        reason="Approved close access",
    )
    assert grant.is_active
    grant.revoked_at = timezone.now()
    assert not grant.is_active
    with pytest.raises(ValidationError):
        PermissionSet(tenant_id=tenant_a.id, name="Invalid", default_duration_days=366).full_clean()


def test_field_rule_enums_mask_validation_uniqueness_and_string(tenant_a, role: Role) -> None:
    rule = FieldSecurity.objects.create(
        tenant_id=tenant_a.id,
        module="finance",
        resource="employees",
        field="tax_id",
        role=role,
        visibility=FieldSecurity.Visibility.MASKED,
        edit_control=FieldSecurity.EditControl.READ_ONLY,
        mask_pattern="***-**-####",
    )
    assert "finance.employees.tax_id" in str(rule)
    assert set(FieldSecurity.Visibility.values) == {"visible", "hidden", "masked", "redacted"}
    assert set(FieldSecurity.EditControl.values) == {"read_only", "editable", "required"}
    invalid = FieldSecurity(
        tenant_id=tenant_a.id,
        module="finance",
        resource="employees",
        field="salary",
        role=role,
        visibility="masked",
        mask_pattern="",
    )
    with pytest.raises(ValidationError, match="mask pattern"):
        invalid.full_clean()


def test_row_rule_safe_predicate_defaults_reject_raw_lookup_and_string(tenant_a, role: Role) -> None:
    predicate = {"op": "eq", "field": "owner_id", "value": {"subject": "id"}}
    rule = RowSecurityRule(
        tenant_id=tenant_a.id,
        module="finance",
        resource="journals",
        role=role,
        filter_criteria=predicate,
    )
    rule.full_clean()
    rule.save()
    assert rule.priority == 0 and rule.version == 1 and rule.is_active
    assert "finance.journals" in str(rule)
    for unsafe in (
        "owner_id = current_user",
        {"op": "raw_sql", "value": "TRUE"},
        {"op": "eq", "field": "owner_id__in", "value": "x"},
        {"op": "and", "args": []},
    ):
        rule.filter_criteria = unsafe
        with pytest.raises(ValidationError):
            rule.full_clean()


def test_security_profile_defaults_enums_policy_validation_and_assignment(
    tenant_a, tenant_a_user, role: Role, actor_id
) -> None:
    profile = SecurityProfile(
        tenant_id=tenant_a.id,
        name="Restricted",
        profile_type=SecurityProfile.ProfileType.RESTRICTED,
        ip_whitelist=["10.0.0.0/8"],
        blocked_countries=["KP"],
    )
    profile.full_clean()
    profile.save()
    assert str(profile) == "Restricted (restricted)"
    assert profile.session_timeout_minutes == 60 and profile.max_concurrent_sessions == 5
    assert profile.download_allowed and not profile.login_notification
    assert set(SecurityProfile.MFARequired.values) == {
        "always",
        "conditional",
        "sensitive_actions",
        "never",
    }
    assignment = SecurityProfileAssignment(
        tenant_id=tenant_a.id,
        security_profile=profile,
        user=tenant_a_user,
        assigned_by=actor_id,
        reason="Direct restriction",
    )
    assignment.full_clean()
    assignment.save()
    assert assignment.is_active
    assignment.role = role
    with pytest.raises(ValidationError, match="Exactly one"):
        assignment.full_clean()


def test_audit_is_append_only_redaction_fields_and_all_orm_mutations_fail(tenant_a, actor_id) -> None:
    audit = SecurityAuditLog.objects.create(
        tenant_id=tenant_a.id,
        action="security.role.changed",
        actor_id=actor_id,
        resource_type="role",
        reason_codes=["CONFIGURATION_CHANGED"],
        details={"operation": "create"},
        correlation_id="corr-model-test",
    )
    assert "security.role.changed" in str(audit)
    audit.details = {"changed": True}
    with pytest.raises(ImmutableAuditError):
        audit.save()
    with pytest.raises(ImmutableAuditError):
        audit.delete()
    with pytest.raises(ImmutableAuditError):
        SecurityAuditLog.objects.filter(pk=audit.pk).update(action="tampered")
    with pytest.raises(ImmutableAuditError):
        SecurityAuditLog.objects.filter(pk=audit.pk).delete()


@pytest.mark.postgresql
def test_audit_database_trigger_rejects_raw_update_and_delete(tenant_a, actor_id) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Database-trigger enforcement runs in PostgreSQL 17 gate")
    audit = SecurityAuditLog.objects.create(
        tenant_id=tenant_a.id,
        action="security.evidence",
        actor_id=actor_id,
        resource_type="test",
        correlation_id="corr-db-trigger",
    )
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("UPDATE security_audit_logs SET action = 'tampered' WHERE id = %s", [str(audit.id)])
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("DELETE FROM security_audit_logs WHERE id = %s", [str(audit.id)])
