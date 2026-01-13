"""
Security & Access Control Service Tests
"""

import pytest
from django.contrib.auth import get_user_model

from src.modules.tenant_management.models import Tenant

from src.modules.security_access_control.models import (
    FieldSecurity,
    Permission,
    PermissionSet,
    Role,
    RolePermission,
    RowSecurityRule,
    SecurityAuditLog,
    SecurityProfile,
    UserRole,
)
from src.modules.security_access_control.services import SecurityAccessControlService

User = get_user_model()


@pytest.mark.django_db
class TestSecurityAccessControlService:
    """Test SecurityAccessControlService business logic."""

    def test_create_role(self):
        """Test: Create role using service."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        role = SecurityAccessControlService.create_role(
            name="Test Role",
            code="test_role",
            tenant_id=tenant.id,
            description="Test description",
            role_type=Role.RoleType.CUSTOM,
        )
        assert role.name == "Test Role"
        assert role.code == "test_role"
        assert str(role.tenant_id) == str(tenant.id)

    def test_assign_permission_to_role(self):
        """Test: Assign permission to role."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        role = Role.objects.create(name="Test Role", code="test_role", tenant_id=tenant.id)
        permission = Permission.objects.create(module="crm", object="customers", action="read")
        role_permission = SecurityAccessControlService.assign_permission_to_role(
            role_id=role.id, permission_id=permission.id, is_granted=True
        )
        assert role_permission.role == role
        assert role_permission.permission == permission
        assert role_permission.is_granted is True

    def test_assign_role_to_user(self):
        """Test: Assign role to user."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        role = Role.objects.create(name="Test Role", code="test_role", tenant_id=tenant.id)
        user_role = SecurityAccessControlService.assign_role_to_user(
            user_id=user.id,
            role_id=role.id,
            assigned_by=user.id,
            reason="Test assignment",
        )
        assert user_role.user == user
        assert user_role.role == role
        assert user_role.assigned_by == user.id

    def test_create_permission_set(self):
        """Test: Create permission set."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        perm1 = Permission.objects.create(module="crm", object="customers", action="read")
        perm2 = Permission.objects.create(module="crm", object="customers", action="update")
        permission_set = SecurityAccessControlService.create_permission_set(
            name="CRM Access",
            tenant_id=tenant.id,
            permission_ids=[perm1.id, perm2.id],
            default_duration_days=30,
        )
        assert permission_set.name == "CRM Access"
        assert len(permission_set.permission_ids) == 2

    def test_grant_permission_set_to_user(self):
        """Test: Grant permission set to user."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        permission_set = PermissionSet.objects.create(name="Test Set", tenant_id=tenant.id, permission_ids=[])
        user_permission_set = SecurityAccessControlService.grant_permission_set_to_user(
            user_id=user.id,
            permission_set_id=permission_set.id,
            duration_days=7,
            granted_by=user.id,
        )
        assert user_permission_set.user == user
        assert user_permission_set.permission_set == permission_set
        assert user_permission_set.is_active is True

    def test_create_field_security(self):
        """Test: Create field-level security rule."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        role = Role.objects.create(name="Test Role", code="test_role", tenant_id=tenant.id)
        field_security = SecurityAccessControlService.create_field_security(
            module="crm",
            object_name="customers",
            field="credit_card",
            role_id=role.id,
            tenant_id=tenant.id,
            visibility=FieldSecurity.Visibility.MASKED,
            edit_control=FieldSecurity.EditControl.READ_ONLY,
            mask_pattern="**** **** **** XXXX",
        )
        assert field_security.module == "crm"
        assert field_security.object == "customers"
        assert field_security.field == "credit_card"
        assert field_security.visibility == FieldSecurity.Visibility.MASKED

    def test_create_row_security_rule(self):
        """Test: Create row-level security rule."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        role = Role.objects.create(name="Test Role", code="test_role", tenant_id=tenant.id)
        row_rule = SecurityAccessControlService.create_row_security_rule(
            module="crm",
            object_name="opportunities",
            role_id=role.id,
            tenant_id=tenant.id,
            rule_type=RowSecurityRule.RuleType.OWNERSHIP,
            filter_criteria="owner_id = :current_user_id",
            priority=10,
        )
        assert row_rule.module == "crm"
        assert row_rule.object == "opportunities"
        assert row_rule.rule_type == RowSecurityRule.RuleType.OWNERSHIP

    def test_create_security_profile(self):
        """Test: Create security profile."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        profile = SecurityAccessControlService.create_security_profile(
            name="High Security",
            tenant_id=tenant.id,
            profile_type=SecurityProfile.ProfileType.HIGH_SECURITY,
            mfa_required=SecurityProfile.MFARequired.ALWAYS,
            session_timeout_minutes=5,
        )
        assert profile.name == "High Security"
        assert profile.profile_type == SecurityProfile.ProfileType.HIGH_SECURITY

    def test_log_audit_event(self):
        """Test: Log audit event."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        audit_log = SecurityAccessControlService.log_audit_event(
            action="security.role.created",
            actor_id=user.id,
            resource_type="Role",
            tenant_id=tenant.id,
            decision=SecurityAuditLog.Decision.ALLOW,
            reason_codes=["role_created"],
            details={"role_name": "Test Role"},
        )
        assert audit_log.action == "security.role.created"
        assert audit_log.decision == SecurityAuditLog.Decision.ALLOW
        assert str(audit_log.tenant_id) == str(tenant.id)

    def test_get_user_effective_permissions(self):
        """Test: Get effective permissions for user."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        role = Role.objects.create(name="Test Role", code="test_role", tenant_id=tenant.id)
        perm1 = Permission.objects.create(module="crm", object="customers", action="read")
        perm2 = Permission.objects.create(module="crm", object="customers", action="update")
        RolePermission.objects.create(role=role, permission=perm1, is_granted=True)
        RolePermission.objects.create(role=role, permission=perm2, is_granted=True)
        UserRole.objects.create(user=user, role=role)
        permissions = SecurityAccessControlService.get_user_effective_permissions(user_id=user.id, tenant_id=tenant.id)
        assert "crm:customers:read" in permissions
        assert "crm:customers:update" in permissions
