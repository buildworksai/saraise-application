"""
Security & Access Control API Tests
"""

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from src.core.user_models import UserProfile
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


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def tenant_user(db):
    """Create a test user with tenant."""
    tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": str(tenant.id), "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = str(tenant.id)
            profile.tenant_role = "tenant_admin"
            profile.save()
    # Force reload user to ensure profile is accessible
    user = User.objects.select_related("profile").get(pk=user.pk)
    return user


@pytest.fixture
def authenticated_client(api_client, tenant_user):
    """Create authenticated API client."""
    api_client.force_authenticate(user=tenant_user)
    return api_client


@pytest.fixture
def user_no_tenant(db):
    """Create a test user without a tenant profile."""
    return User.objects.create_user(
        username="no-tenant-user",
        email="no-tenant@example.com",
        password="testpass123",
    )


@pytest.fixture
def client_no_tenant(api_client, user_no_tenant):
    """Authenticated client without tenant context."""
    api_client.force_authenticate(user=user_no_tenant)
    return api_client


@pytest.mark.django_db
class TestRoleViewSet:
    """Test cases for Roles API."""

    def test_create_role_success(self, authenticated_client, tenant_user):
        """Test: Create role with valid data."""
        data = {
            "name": "Sales Manager",
            "code": "sales_manager",
            "description": "Manages sales team",
            "role_type": "functional",
        }
        response = authenticated_client.post("/api/v1/security-access-control/roles/", data, format="json")
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Response status: {response.status_code}")
            print(f"Response data: {response.data}")
        assert (
            response.status_code == status.HTTP_201_CREATED
        ), f"Expected 201, got {response.status_code}: {response.data}"
        assert response.data["name"] == "Sales Manager"
        assert response.data["code"] == "sales_manager"
        assert response.data["tenant_id"] == str(tenant_user.profile.tenant_id)

    def test_create_role_validation_error(self, authenticated_client):
        """Test: Validation error for short code."""
        data = {"name": "Test", "code": "a"}  # Code too short
        response = authenticated_client.post("/api/v1/security-access-control/roles/", data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_roles_filtered_by_tenant(self, authenticated_client, tenant_user):
        """Test: List returns only tenant's roles."""
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        # Create role for current tenant
        Role.objects.create(name="Tenant Role", code="tenant_role", tenant_id=tenant_id)
        # Create role for other tenant (should not appear)
        other_tenant = Tenant.objects.create(name="Other Tenant", slug="other-tenant")
        Role.objects.create(name="Other Role", code="other_role", tenant_id=other_tenant.id)
        response = authenticated_client.get("/api/v1/security-access-control/roles/")
        assert response.status_code == status.HTTP_200_OK
        names = [r["name"] for r in response.data]
        assert "Tenant Role" in names
        assert "Other Role" not in names

    def test_filter_roles_by_type(self, authenticated_client, tenant_user):
        """Test: Filter roles by role_type."""
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        Role.objects.create(
            name="System Role",
            code="system_role",
            tenant_id=tenant_id,
            role_type=Role.RoleType.SYSTEM,
        )
        Role.objects.create(
            name="Custom Role",
            code="custom_role",
            tenant_id=tenant_id,
            role_type=Role.RoleType.CUSTOM,
        )
        response = authenticated_client.get("/api/v1/security-access-control/roles/?role_type=system")
        assert response.status_code == status.HTTP_200_OK
        names = [r["name"] for r in response.data]
        assert "System Role" in names
        assert "Custom Role" not in names

    def test_cannot_delete_system_role(self, authenticated_client, tenant_user):
        """Test: Cannot delete system role."""
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        role = Role.objects.create(name="System Role", code="system_role", tenant_id=tenant_id, is_system=True)
        response = authenticated_client.delete(f"/api/v1/security-access-control/roles/{role.id}/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_assign_permission_to_role(self, authenticated_client, tenant_user):
        """Test: Assign permission to role."""
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        role = Role.objects.create(name="Test Role", code="test_role", tenant_id=tenant_id)
        permission = Permission.objects.create(module="crm", object="customers", action="read")
        response = authenticated_client.post(
            f"/api/v1/security-access-control/roles/{role.id}/assign_permission/",
            {"permission_id": str(permission.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_granted"] is True

    def test_revoke_permission_from_role(self, authenticated_client, tenant_user):
        """Test: Revoke permission from role."""
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        role = Role.objects.create(name="Test Role", code="test_role_revoke", tenant_id=tenant_id)
        permission = Permission.objects.create(module="crm", object="customers", action="read")
        authenticated_client.post(
            f"/api/v1/security-access-control/roles/{role.id}/assign_permission/",
            {"permission_id": str(permission.id)},
            format="json",
        )
        response = authenticated_client.post(
            f"/api/v1/security-access-control/roles/{role.id}/revoke_permission/",
            {"permission_id": str(permission.id)},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "Permission revoked"

    def test_assign_permission_missing_id(self, authenticated_client, tenant_user):
        """Test: Assign permission requires permission_id."""
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        role = Role.objects.create(name="Test Role", code="test_role_missing", tenant_id=tenant_id)
        response = authenticated_client.post(
            f"/api/v1/security-access-control/roles/{role.id}/assign_permission/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_assign_permission_not_found(self, authenticated_client, tenant_user):
        """Test: Assign permission returns 404 when permission not found."""
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        role = Role.objects.create(name="Test Role", code="test_role_notfound", tenant_id=tenant_id)
        response = authenticated_client.post(
            f"/api/v1/security-access-control/roles/{role.id}/assign_permission/",
            {"permission_id": str(uuid.uuid4())},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_role(self, authenticated_client, tenant_user):
        """Test: Update role."""
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        role = Role.objects.create(name="Role Update", code="role_update", tenant_id=tenant_id)
        response = authenticated_client.patch(
            f"/api/v1/security-access-control/roles/{role.id}/",
            {"description": "Updated"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["description"] == "Updated"

    def test_delete_role(self, authenticated_client, tenant_user):
        """Test: Delete non-system role."""
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        role = Role.objects.create(name="Role Delete", code="role_delete", tenant_id=tenant_id)
        response = authenticated_client.delete(f"/api/v1/security-access-control/roles/{role.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_create_role_without_tenant(self, client_no_tenant):
        """Test: Create role without tenant fails."""
        data = {"name": "No Tenant", "code": "no_tenant"}
        response = client_no_tenant.post("/api/v1/security-access-control/roles/", data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_roles_no_tenant(self, client_no_tenant):
        """Test: List roles returns empty for users without tenant."""
        response = client_no_tenant.get("/api/v1/security-access-control/roles/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_list_roles_invalid_tenant(self, authenticated_client, monkeypatch):
        """Test: Invalid tenant ID returns empty role list."""
        monkeypatch.setattr(
            "src.modules.security_access_control.api.get_user_tenant_id",
            lambda _user: "not-a-uuid",
        )
        response = authenticated_client.get("/api/v1/security-access-control/roles/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_filter_roles_by_is_active(self, authenticated_client, tenant_user):
        """Test: Filter roles by is_active query param."""
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        Role.objects.create(name="Active Role", code="active_role", tenant_id=tenant_id, is_active=True)
        Role.objects.create(
            name="Inactive Role",
            code="inactive_role",
            tenant_id=tenant_id,
            is_active=False,
        )
        response = authenticated_client.get("/api/v1/security-access-control/roles/?is_active=true")
        assert response.status_code == status.HTTP_200_OK
        names = [r["name"] for r in response.data]
        assert "Active Role" in names
        assert "Inactive Role" not in names

    def test_get_role_not_found(self, authenticated_client):
        """Test: Role detail not found returns 404."""
        response = authenticated_client.get(f"/api/v1/security-access-control/roles/{uuid.uuid4()}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_assign_permission_updates_existing(self, authenticated_client, tenant_user):
        """Test: Assign permission updates existing RolePermission."""
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        role = Role.objects.create(name="Update RolePerm", code="update_roleperm", tenant_id=tenant_id)
        permission = Permission.objects.create(module="crm", object="customers", action="read")
        RolePermission.objects.create(role=role, permission=permission, is_granted=True)
        response = authenticated_client.post(
            f"/api/v1/security-access-control/roles/{role.id}/assign_permission/",
            {"permission_id": str(permission.id), "is_granted": False},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_granted"] is False


@pytest.mark.django_db
class TestPermissionViewSet:
    """Test cases for Permissions API."""

    def test_list_permissions(self, authenticated_client):
        """Test: List permissions."""
        Permission.objects.create(module="crm", object="customers", action="read")
        Permission.objects.create(module="crm", object="customers", action="create")
        response = authenticated_client.get("/api/v1/security-access-control/permissions/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 2

    def test_filter_permissions_by_module(self, authenticated_client):
        """Test: Filter permissions by module."""
        Permission.objects.create(module="crm", object="customers", action="read")
        Permission.objects.create(module="accounting", object="invoices", action="read")
        response = authenticated_client.get("/api/v1/security-access-control/permissions/?module=crm")
        assert response.status_code == status.HTTP_200_OK
        modules = [p["module"] for p in response.data]
        assert all(m == "crm" for m in modules)


@pytest.mark.django_db
class TestUserRoleViewSet:
    """Test cases for User-Role assignments API."""

    def test_assign_role_to_user(self, authenticated_client, tenant_user):
        """Test: Assign role to user."""
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        role = Role.objects.create(name="Test Role", code="test_role", tenant_id=tenant_id)
        data = {"user": str(tenant_user.id), "role_id": str(role.id)}
        response = authenticated_client.post("/api/v1/security-access-control/user-roles/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["role"]["id"] == str(role.id)

    def test_list_user_roles_filtered(self, authenticated_client, tenant_user):
        """Test: List user roles filtered by user and role."""
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        role = Role.objects.create(name="Filter Role", code="filter_role", tenant_id=tenant_id)
        UserRole.objects.create(user=tenant_user, role=role)
        response = authenticated_client.get(
            f"/api/v1/security-access-control/user-roles/?user_id={tenant_user.id}&role_id={role.id}"
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_list_user_roles_no_tenant(self, client_no_tenant):
        """Test: List user roles returns empty without tenant."""
        response = client_no_tenant.get("/api/v1/security-access-control/user-roles/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []


@pytest.mark.django_db
class TestPermissionSetViewSet:
    """Test cases for Permission Sets API."""

    def test_create_permission_set(self, authenticated_client, tenant_user):
        """Test: Create permission set."""
        perm1 = Permission.objects.create(module="crm", object="customers", action="read")
        perm2 = Permission.objects.create(module="crm", object="customers", action="update")
        data = {
            "name": "CRM Access",
            "description": "CRM read and update access",
            "permission_ids": [str(perm1.id), str(perm2.id)],
            "default_duration_days": 30,
        }
        response = authenticated_client.post("/api/v1/security-access-control/permission-sets/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "CRM Access"
        assert len(response.data["permission_ids"]) == 2

    def test_update_permission_set(self, authenticated_client, tenant_user):
        """Test: Update permission set."""
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        permission_set = PermissionSet.objects.create(
            name="Old Name",
            tenant_id=tenant_id,
            permission_ids=[],
        )
        response = authenticated_client.patch(
            f"/api/v1/security-access-control/permission-sets/{permission_set.id}/",
            {"name": "New Name"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "New Name"

    def test_list_permission_sets(self, authenticated_client):
        """Test: List permission sets."""
        response = authenticated_client.get("/api/v1/security-access-control/permission-sets/")
        assert response.status_code == status.HTTP_200_OK

    def test_create_permission_set_without_tenant(self, client_no_tenant):
        """Test: Create permission set without tenant fails."""
        response = client_no_tenant.post(
            "/api/v1/security-access-control/permission-sets/",
            {"name": "No Tenant", "permission_ids": []},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestUserPermissionSetViewSet:
    """Test cases for User Permission Set grants API."""

    def test_grant_permission_set(self, authenticated_client, tenant_user):
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        permission_set = PermissionSet.objects.create(
            name="Grant Set",
            tenant_id=tenant_id,
            permission_ids=[],
        )
        expires_at = timezone.now() + timedelta(days=7)
        response = authenticated_client.post(
            "/api/v1/security-access-control/user-permission-sets/",
            {
                "user": str(tenant_user.id),
                "permission_set_id": str(permission_set.id),
                "expires_at": expires_at.isoformat(),
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_list_user_permission_sets_filtered(self, authenticated_client, tenant_user):
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        permission_set = PermissionSet.objects.create(
            name="List Set",
            tenant_id=tenant_id,
            permission_ids=[],
        )
        expires_at = timezone.now() + timedelta(days=7)
        UserPermissionSet.objects.create(
            user=tenant_user,
            permission_set=permission_set,
            expires_at=expires_at,
            reason="test",
        )
        response = authenticated_client.get(
            f"/api/v1/security-access-control/user-permission-sets/?user_id={tenant_user.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_list_user_permission_sets_no_tenant(self, client_no_tenant):
        response = client_no_tenant.get("/api/v1/security-access-control/user-permission-sets/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []


@pytest.mark.django_db
class TestSecurityProfileViewSet:
    """Test cases for Security Profiles API."""

    def test_create_security_profile(self, authenticated_client, tenant_user):
        """Test: Create security profile."""
        data = {
            "name": "High Security Profile",
            "description": "High security settings",
            "profile_type": "high_security",
            "mfa_required": "always",
            "session_timeout_minutes": 5,
            "download_allowed": False,
        }
        response = authenticated_client.post("/api/v1/security-access-control/security-profiles/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "High Security Profile"
        assert response.data["profile_type"] == "high_security"
        assert response.data["download_allowed"] is False

    def test_list_security_profiles_filtered(self, authenticated_client, tenant_user):
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        SecurityProfile.objects.create(
            name="Standard Profile",
            tenant_id=tenant_id,
            profile_type=SecurityProfile.ProfileType.STANDARD,
        )
        SecurityProfile.objects.create(
            name="Restricted Profile",
            tenant_id=tenant_id,
            profile_type=SecurityProfile.ProfileType.RESTRICTED,
        )
        response = authenticated_client.get(
            "/api/v1/security-access-control/security-profiles/?profile_type=restricted"
        )
        assert response.status_code == status.HTTP_200_OK
        names = [p["name"] for p in response.data]
        assert "Restricted Profile" in names
        assert "Standard Profile" not in names

    def test_list_security_profiles_no_tenant(self, client_no_tenant):
        response = client_no_tenant.get("/api/v1/security-access-control/security-profiles/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []


@pytest.mark.django_db
class TestFieldSecurityViewSet:
    """Test cases for Field Security API."""

    def test_create_field_security(self, authenticated_client, tenant_user):
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        role = Role.objects.create(name="Field Role", code="field_role", tenant_id=tenant_id)
        data = {
            "module": "crm",
            "object": "customer",
            "field": "email",
            "role": str(role.id),
            "visibility": "masked",
            "edit_control": "read_only",
        }
        response = authenticated_client.post("/api/v1/security-access-control/field-security/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_list_field_security_filtered(self, authenticated_client, tenant_user):
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        role = Role.objects.create(name="Field Filter Role", code="field_filter_role", tenant_id=tenant_id)
        FieldSecurity.objects.create(
            tenant_id=tenant_id,
            module="crm",
            object="customer",
            field="email",
            role=role,
        )
        response = authenticated_client.get(
            "/api/v1/security-access-control/field-security/?module=crm&object=customer"
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_list_field_security_no_tenant(self, client_no_tenant):
        response = client_no_tenant.get("/api/v1/security-access-control/field-security/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []


@pytest.mark.django_db
class TestRowSecurityRuleViewSet:
    """Test cases for Row Security Rule API."""

    def test_create_row_security_rule(self, authenticated_client, tenant_user):
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        role = Role.objects.create(name="Row Role", code="row_role", tenant_id=tenant_id)
        data = {
            "module": "crm",
            "object": "customer",
            "role": str(role.id),
            "rule_type": "ownership",
            "filter_criteria": "owner_id = user_id",
            "priority": 10,
        }
        response = authenticated_client.post("/api/v1/security-access-control/row-security-rules/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_list_row_security_rules_filtered(self, authenticated_client, tenant_user):
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        role = Role.objects.create(name="Row Filter Role", code="row_filter_role", tenant_id=tenant_id)
        RowSecurityRule.objects.create(
            tenant_id=tenant_id,
            module="crm",
            object="customer",
            role=role,
            rule_type=RowSecurityRule.RuleType.OWNERSHIP,
            filter_criteria="owner_id = user_id",
            priority=5,
        )
        response = authenticated_client.get(
            "/api/v1/security-access-control/row-security-rules/?module=crm&object=customer"
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_list_row_security_rules_no_tenant(self, client_no_tenant):
        response = client_no_tenant.get("/api/v1/security-access-control/row-security-rules/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []


@pytest.mark.django_db
class TestSecurityAuditLogViewSet:
    """Test cases for Security Audit Logs API."""

    def test_list_audit_logs(self, authenticated_client, tenant_user):
        """Test: List audit logs for the authenticated tenant."""
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        SecurityAuditLog.objects.create(
            tenant_id=tenant_id,
            action="security.role.created",
            actor_type=SecurityAuditLog.ActorType.USER,
            actor_id=tenant_user.id,
            resource_type="Role",
            decision=SecurityAuditLog.Decision.ALLOW,
        )
        response = authenticated_client.get("/api/v1/security-access-control/audit-logs/")
        assert response.status_code == status.HTTP_200_OK
        # Response might be paginated
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) >= 1
        assert data[0]["action"] == "security.role.created"

    def test_filter_audit_logs(self, authenticated_client, tenant_user):
        tenant_id = uuid.UUID(tenant_user.profile.tenant_id)
        SecurityAuditLog.objects.create(
            tenant_id=tenant_id,
            action="security.role.deleted",
            actor_type=SecurityAuditLog.ActorType.USER,
            actor_id=tenant_user.id,
            resource_type="Role",
            decision=SecurityAuditLog.Decision.DENY,
        )
        response = authenticated_client.get("/api/v1/security-access-control/audit-logs/?action=deleted&decision=deny")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) >= 1

    def test_list_audit_logs_no_tenant(self, client_no_tenant):
        response = client_no_tenant.get("/api/v1/security-access-control/audit-logs/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []
