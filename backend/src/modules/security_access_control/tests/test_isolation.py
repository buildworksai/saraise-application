"""
Security & Access Control Tenant Isolation Tests

CRITICAL: These tests verify tenant isolation.
Users can only access roles, permission sets, and security profiles
belonging to their tenant.
"""

import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.user_models import UserProfile
from src.modules.tenant_management.models import Tenant

from src.modules.security_access_control.models import PermissionSet, Role, SecurityProfile

User = get_user_model()


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def tenant_a_user(db):
    """Create a user for Tenant A."""
    tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
    user = User.objects.create_user(
        username="user_a",
        email="user_a@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": str(tenant_a.id), "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = str(tenant_a.id)
            profile.tenant_role = "tenant_admin"
            profile.save()
    # Force reload user to ensure profile is accessible
    user = User.objects.select_related("profile").get(pk=user.pk)
    return user


@pytest.fixture
def tenant_b_user(db):
    """Create a user for Tenant B."""
    tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")
    user = User.objects.create_user(
        username="user_b",
        email="user_b@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": str(tenant_b.id), "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = str(tenant_b.id)
            profile.tenant_role = "tenant_admin"
            profile.save()
    # Force reload user to ensure profile is accessible
    user = User.objects.select_related("profile").get(pk=user.pk)
    return user


@pytest.fixture
def client_a(api_client, tenant_a_user):
    """Authenticated client for User A."""
    api_client.force_authenticate(user=tenant_a_user)
    return api_client


@pytest.fixture
def client_b(api_client, tenant_b_user):
    """Authenticated client for User B."""
    api_client.force_authenticate(user=tenant_b_user)
    return api_client


@pytest.mark.django_db
class TestTenantIsolation:
    """
    CRITICAL: Tenant isolation tests.
    These tests verify that tenants cannot access each other's data.
    """

    def test_user_cannot_list_other_tenant_roles(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's roles in list."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_a_id_str = get_user_tenant_id(tenant_a_user)
        tenant_b_id_str = get_user_tenant_id(tenant_b_user)
        tenant_a_id = uuid.UUID(tenant_a_id_str) if tenant_a_id_str else None
        tenant_b_id = uuid.UUID(tenant_b_id_str) if tenant_b_id_str else None

        # Create role for tenant A
        Role.objects.create(tenant_id=tenant_a_id, name="Tenant A Role", code="tenant_a_role")

        # Create role for tenant B
        other_role = Role.objects.create(tenant_id=tenant_b_id, name="Tenant B Role", code="tenant_b_role")

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/security-access-control/roles/")

        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        names = [r["name"] for r in data]
        assert "Tenant A Role" in names
        assert "Tenant B Role" not in names
        role_ids = [r["id"] for r in data]
        assert str(other_role.id) not in role_ids

    def test_user_cannot_access_other_tenant_role(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's role by ID."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id_str = get_user_tenant_id(tenant_b_user)

        if not tenant_b_id_str:
            pytest.skip("User must have tenant_id for isolation tests")

        tenant_b_id = uuid.UUID(tenant_b_id_str)

        # Create role for tenant B
        other_role = Role.objects.create(tenant_id=tenant_b_id, name="Other Role", code="other_role")

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get(f"/api/v1/security-access-control/roles/{other_role.id}/")

        # MUST return 404 (not 403) to hide existence
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_role(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot PATCH other tenant's role."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id_str = get_user_tenant_id(tenant_b_user)

        if not tenant_b_id_str:
            pytest.skip("User must have tenant_id for isolation tests")

        tenant_b_id = uuid.UUID(tenant_b_id_str)

        # Create role for tenant B
        other_role = Role.objects.create(tenant_id=tenant_b_id, name="Other Role", code="other_role")
        original_name = other_role.name

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        data = {"name": "Updated Name"}
        response = api_client.patch(
            f"/api/v1/security-access-control/roles/{other_role.id}/",
            data,
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        # Ensure name was not changed
        other_role.refresh_from_db()
        assert other_role.name == original_name

    def test_user_cannot_delete_other_tenant_role(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot DELETE other tenant's role."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_b_id_str = get_user_tenant_id(tenant_b_user)

        if not tenant_b_id_str:
            pytest.skip("User must have tenant_id for isolation tests")

        tenant_b_id = uuid.UUID(tenant_b_id_str)

        # Create role for tenant B
        other_role = Role.objects.create(tenant_id=tenant_b_id, name="Other Role", code="other_role")
        initial_count = Role.objects.count()

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.delete(f"/api/v1/security-access-control/roles/{other_role.id}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        # Ensure role was not deleted
        assert Role.objects.count() == initial_count

    def test_permission_set_tenant_isolation(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User A should not see permission sets belonging to Tenant B."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_a_id_str = get_user_tenant_id(tenant_a_user)
        tenant_b_id_str = get_user_tenant_id(tenant_b_user)

        if not tenant_a_id_str or not tenant_b_id_str:
            pytest.skip("Users must have tenant_id for isolation tests")

        tenant_a_id = uuid.UUID(tenant_a_id_str)
        tenant_b_id = uuid.UUID(tenant_b_id_str)

        PermissionSet.objects.create(tenant_id=tenant_a_id, name="Tenant A Set", permission_ids=[])
        other_set = PermissionSet.objects.create(tenant_id=tenant_b_id, name="Tenant B Set", permission_ids=[])

        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/security-access-control/permission-sets/")
        assert response.status_code == status.HTTP_200_OK
        names = [s["name"] for s in response.data]
        assert "Tenant A Set" in names
        assert "Tenant B Set" not in names
        set_ids = [s["id"] for s in response.data]
        assert str(other_set.id) not in set_ids

    def test_security_profile_tenant_isolation(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User A should not see security profiles belonging to Tenant B."""
        from src.core.auth_utils import get_user_tenant_id

        tenant_a_id_str = get_user_tenant_id(tenant_a_user)
        tenant_b_id_str = get_user_tenant_id(tenant_b_user)

        if not tenant_a_id_str or not tenant_b_id_str:
            pytest.skip("Users must have tenant_id for isolation tests")

        tenant_a_id = uuid.UUID(tenant_a_id_str)
        tenant_b_id = uuid.UUID(tenant_b_id_str)

        SecurityProfile.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Profile",
            profile_type=SecurityProfile.ProfileType.STANDARD,
        )
        other_profile = SecurityProfile.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Profile",
            profile_type=SecurityProfile.ProfileType.STANDARD,
        )

        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/security-access-control/security-profiles/")
        assert response.status_code == status.HTTP_200_OK
        names = [p["name"] for p in response.data]
        assert "Tenant A Profile" in names
        assert "Tenant B Profile" not in names
        profile_ids = [p["id"] for p in response.data]
        assert str(other_profile.id) not in profile_ids
