"""
Security & Access Control Model Tests
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from src.modules.tenant_management.models import Tenant

from ..models import (
    FieldSecurity,
    Permission,
    PermissionSet,
    Role,
    RolePermission,
    RowSecurityRule,
    SecurityAuditLog,
    SecurityProfile,
    UserPermissionSet,
    UserRole,
)

User = get_user_model()


@pytest.mark.django_db
class TestRole:
    """Test Role model."""

    def test_create_role(self):
        """Test: Create role with valid data."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        role = Role.objects.create(
            name="Sales Manager",
            code="sales_manager",
            tenant_id=tenant.id,
            description="Manages sales team",
            role_type=Role.RoleType.FUNCTIONAL,
        )
        assert role.name == "Sales Manager"
        assert role.code == "sales_manager"
        assert role.tenant_id == tenant.id
        assert role.role_type == Role.RoleType.FUNCTIONAL
        assert role.is_active is True

    def test_role_code_uniqueness_per_tenant(self):
        """Test: Role code must be unique per tenant."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        Role.objects.create(name="Role 1", code="test_role", tenant_id=tenant.id)
        # Same code, same tenant - should fail
        with pytest.raises(Exception):  # IntegrityError
            Role.objects.create(name="Role 2", code="test_role", tenant_id=tenant.id)

    def test_role_code_unique_across_tenants(self):
        """Test: Same role code allowed for different tenants."""
        tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")
        Role.objects.create(name="Role A", code="same_code", tenant_id=tenant_a.id)
        # Same code, different tenant - should succeed
        role_b = Role.objects.create(name="Role B", code="same_code", tenant_id=tenant_b.id)
        assert role_b.code == "same_code"

    def test_role_hierarchy(self):
        """Test: Role hierarchy with parent_role_id."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        parent_role = Role.objects.create(name="Parent Role", code="parent", tenant_id=tenant.id)
        child_role = Role.objects.create(
            name="Child Role",
            code="child",
            tenant_id=tenant.id,
            parent_role_id=parent_role.id,
        )
        assert child_role.parent_role_id == parent_role.id

    def test_system_role_cannot_be_deleted(self):
        """Test: System roles have is_system=True."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        role = Role.objects.create(name="System Role", code="system_role", tenant_id=tenant.id, is_system=True)
        assert role.is_system is True


@pytest.mark.django_db
class TestPermission:
    """Test Permission model."""

    def test_create_permission(self):
        """Test: Create permission with valid data."""
        permission = Permission.objects.create(
            module="crm",
            object="customers",
            action="read",
            name="Read Customers",
            description="Read customer records",
        )
        assert permission.module == "crm"
        assert permission.object == "customers"
        assert permission.action == "read"
        assert str(permission) == "crm:customers:read"

    def test_permission_uniqueness(self):
        """Test: Permission (module, object, action) must be unique."""
        Permission.objects.create(module="crm", object="customers", action="read")
        # Same module:object:action - should fail
        with pytest.raises(Exception):  # IntegrityError
            Permission.objects.create(module="crm", object="customers", action="read")

    def test_permission_string_format(self):
        """Test: Permission string format is module:object:action."""
        permission = Permission.objects.create(module="accounting", object="invoices", action="create")
        assert str(permission) == "accounting:invoices:create"


@pytest.mark.django_db
class TestRolePermission:
    """Test RolePermission model."""

    def test_assign_permission_to_role(self):
        """Test: Assign permission to role."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        role = Role.objects.create(name="Test Role", code="test_role", tenant_id=tenant.id)
        permission = Permission.objects.create(module="crm", object="customers", action="read")
        role_permission = RolePermission.objects.create(role=role, permission=permission, is_granted=True)
        assert role_permission.role == role
        assert role_permission.permission == permission
        assert role_permission.is_granted is True

    def test_explicit_deny(self):
        """Test: Explicit deny (is_granted=False)."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        role = Role.objects.create(name="Test Role", code="test_role", tenant_id=tenant.id)
        permission = Permission.objects.create(module="crm", object="customers", action="delete")
        role_permission = RolePermission.objects.create(
            role=role, permission=permission, is_granted=False  # Explicit deny
        )
        assert role_permission.is_granted is False


@pytest.mark.django_db
class TestUserRole:
    """Test UserRole model."""

    def test_assign_role_to_user(self):
        """Test: Assign role to user."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        role = Role.objects.create(name="Test Role", code="test_role", tenant_id=tenant.id)
        user_role = UserRole.objects.create(user=user, role=role, assigned_by=user.id)
        assert user_role.user == user
        assert user_role.role == role
        assert user_role.is_active is True

    def test_temporal_role_assignment(self):
        """Test: Temporal role assignment with expiration."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        role = Role.objects.create(name="Temporary Role", code="temp_role", tenant_id=tenant.id)
        valid_until = timezone.now() + timedelta(days=30)
        user_role = UserRole.objects.create(user=user, role=role, valid_until=valid_until)
        assert user_role.valid_until == valid_until
        assert user_role.is_active is True

    def test_expired_role_assignment(self):
        """Test: Expired role assignment is inactive."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        role = Role.objects.create(name="Expired Role", code="expired_role", tenant_id=tenant.id)
        valid_until = timezone.now() - timedelta(days=1)  # Expired
        user_role = UserRole.objects.create(user=user, role=role, valid_until=valid_until)
        assert user_role.is_active is False


@pytest.mark.django_db
class TestPermissionSet:
    """Test PermissionSet model."""

    def test_create_permission_set(self):
        """Test: Create permission set."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        perm1 = Permission.objects.create(module="crm", object="customers", action="read")
        perm2 = Permission.objects.create(module="crm", object="customers", action="update")
        permission_set = PermissionSet.objects.create(
            name="CRM Access",
            tenant_id=tenant.id,
            permission_ids=[str(perm1.id), str(perm2.id)],
            default_duration_days=30,
        )
        assert permission_set.name == "CRM Access"
        assert len(permission_set.permission_ids) == 2
        assert permission_set.default_duration_days == 30


@pytest.mark.django_db
class TestUserPermissionSet:
    """Test UserPermissionSet model."""

    def test_grant_permission_set_to_user(self):
        """Test: Grant permission set to user."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        permission_set = PermissionSet.objects.create(name="Test Set", tenant_id=tenant.id, permission_ids=[])
        expires_at = timezone.now() + timedelta(days=7)
        user_permission_set = UserPermissionSet.objects.create(
            user=user, permission_set=permission_set, expires_at=expires_at
        )
        assert user_permission_set.user == user
        assert user_permission_set.permission_set == permission_set
        assert user_permission_set.is_active is True

    def test_expired_permission_set_grant(self):
        """Test: Expired permission set grant is inactive."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        permission_set = PermissionSet.objects.create(name="Expired Set", tenant_id=tenant.id, permission_ids=[])
        expires_at = timezone.now() - timedelta(days=1)  # Expired
        user_permission_set = UserPermissionSet.objects.create(
            user=user, permission_set=permission_set, expires_at=expires_at
        )
        assert user_permission_set.is_active is False


@pytest.mark.django_db
class TestFieldSecurity:
    """Test FieldSecurity model."""

    def test_create_field_security_rule(self):
        """Test: Create field-level security rule."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        role = Role.objects.create(name="Test Role", code="test_role", tenant_id=tenant.id)
        field_security = FieldSecurity.objects.create(
            tenant_id=tenant.id,
            module="crm",
            object="customers",
            field="credit_card",
            role=role,
            visibility=FieldSecurity.Visibility.MASKED,
            edit_control=FieldSecurity.EditControl.READ_ONLY,
            mask_pattern="**** **** **** XXXX",
        )
        assert field_security.module == "crm"
        assert field_security.object == "customers"
        assert field_security.field == "credit_card"
        assert field_security.visibility == FieldSecurity.Visibility.MASKED
        assert field_security.edit_control == FieldSecurity.EditControl.READ_ONLY


@pytest.mark.django_db
class TestRowSecurityRule:
    """Test RowSecurityRule model."""

    def test_create_row_security_rule(self):
        """Test: Create row-level security rule."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        role = Role.objects.create(name="Test Role", code="test_role", tenant_id=tenant.id)
        row_rule = RowSecurityRule.objects.create(
            tenant_id=tenant.id,
            module="crm",
            object="opportunities",
            role=role,
            rule_type=RowSecurityRule.RuleType.OWNERSHIP,
            filter_criteria="owner_id = :current_user_id",
            priority=10,
        )
        assert row_rule.module == "crm"
        assert row_rule.object == "opportunities"
        assert row_rule.rule_type == RowSecurityRule.RuleType.OWNERSHIP
        assert row_rule.priority == 10


@pytest.mark.django_db
class TestSecurityProfile:
    """Test SecurityProfile model."""

    def test_create_security_profile(self):
        """Test: Create security profile."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        profile = SecurityProfile.objects.create(
            name="High Security Profile",
            tenant_id=tenant.id,
            profile_type=SecurityProfile.ProfileType.HIGH_SECURITY,
            mfa_required=SecurityProfile.MFARequired.ALWAYS,
            session_timeout_minutes=5,
            download_allowed=False,
        )
        assert profile.name == "High Security Profile"
        assert profile.profile_type == SecurityProfile.ProfileType.HIGH_SECURITY
        assert profile.mfa_required == SecurityProfile.MFARequired.ALWAYS
        assert profile.download_allowed is False


@pytest.mark.django_db
class TestSecurityAuditLog:
    """Test SecurityAuditLog model."""

    def test_create_audit_log(self):
        """Test: Create audit log entry."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        audit_log = SecurityAuditLog.objects.create(
            tenant_id=tenant.id,
            action="security.role.created",
            actor_type=SecurityAuditLog.ActorType.USER,
            actor_id=user.id,
            resource_type="Role",
            decision=SecurityAuditLog.Decision.ALLOW,
            reason_codes=["role_created"],
            details={"role_name": "Test Role"},
        )
        assert audit_log.action == "security.role.created"
        assert audit_log.decision == SecurityAuditLog.Decision.ALLOW
        assert audit_log.tenant_id == tenant.id

    def test_audit_log_immutable(self):
        """Test: Audit logs cannot be updated."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        audit_log = SecurityAuditLog.objects.create(
            tenant_id=tenant.id,
            action="test.action",
            actor_type=SecurityAuditLog.ActorType.USER,
            actor_id=user.id,
            resource_type="TestResource",
        )
        # Try to update - should fail
        with pytest.raises(ValueError, match="immutable"):
            audit_log.action = "updated.action"
            audit_log.save()

    def test_audit_log_cannot_be_deleted(self):
        """Test: Audit logs cannot be deleted."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        audit_log = SecurityAuditLog.objects.create(
            tenant_id=tenant.id,
            action="test.action",
            actor_type=SecurityAuditLog.ActorType.USER,
            actor_id=user.id,
            resource_type="TestResource",
        )
        # Try to delete - should fail
        with pytest.raises(ValueError, match="immutable"):
            audit_log.delete()
