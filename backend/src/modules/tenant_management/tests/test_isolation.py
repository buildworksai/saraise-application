"""
Tenant Management Platform-Level Access Control Tests

CRITICAL: These tests verify platform-level access control.
Tenant Management is a platform-level module - only platform owners can access.
Tenant-scoped users should NOT have access to tenant management endpoints.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.user_models import UserProfile

from src.modules.tenant_management.models import Tenant

User = get_user_model()


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def platform_owner(db):
    """Create a platform owner user."""
    user = User.objects.create_user(
        username="platform_owner",
        email="platform@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, created = UserProfile.objects.get_or_create(
            user=user, defaults={"platform_role": "platform_owner", "tenant_id": None}
        )
        if not created:
            # Update existing profile
            profile.platform_role = "platform_owner"
            profile.tenant_id = None
            profile.save()
        elif not profile.platform_role:
            profile.platform_role = "platform_owner"
            profile.tenant_id = None
            profile.save()
    # Force reload user to ensure profile is accessible
    user = User.objects.select_related("profile").get(pk=user.pk)
    return user


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
    return user


@pytest.fixture
def tenant_b_user(db):
    """Create a user for Tenant B."""
    tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b", subdomain="tenant-b")
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
    return user


@pytest.mark.django_db
class TestPlatformLevelAccessControl:
    """
    CRITICAL: Platform-level access control tests.
    These tests verify that only platform owners can access tenant management endpoints.
    """

    def test_tenant_user_cannot_list_tenants(self, api_client, tenant_a_user):
        """Test: Tenant user cannot list tenants (returns empty queryset)."""
        # Create tenants with unique slugs (not conflicting with fixtures)
        Tenant.objects.create(
            name="Isolation List Tenant A",
            slug="isolation-list-tenant-a",
            subdomain="isolation-list-tenant-a",
        )
        Tenant.objects.create(
            name="Isolation List Tenant B",
            slug="isolation-list-tenant-b",
            subdomain="isolation-list-tenant-b",
        )

        api_client.force_authenticate(user=tenant_a_user)
        response = api_client.get("/api/v1/tenant-management/tenants/")

        # Returns empty queryset (not 403) because get_queryset filters by platform_role
        assert response.status_code == status.HTTP_200_OK
        # DRF may return paginated or direct list
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 0

    def test_tenant_user_cannot_create_tenant(self, api_client, tenant_a_user):
        """Test: Tenant user cannot create tenant (405 Method Not Allowed - read-only API)."""
        # Provide valid data to pass serializer validation
        data = {
            "name": "Unauthorized Tenant",
            "slug": "unauthorized-tenant",
            "subdomain": "unauthorized-tenant",
        }

        api_client.force_authenticate(user=tenant_a_user)
        response = api_client.post("/api/v1/tenant-management/tenants/", data, format="json")

        # ReadOnlyModelViewSet returns 405 Method Not Allowed for POST
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_tenant_user_cannot_access_tenant_detail(self, api_client, tenant_a_user):
        """Test: Tenant user cannot access tenant detail."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")

        api_client.force_authenticate(user=tenant_a_user)
        response = api_client.get(f"/api/v1/tenant-management/tenants/{tenant.id}/")

        # Returns 404 (not 403) because queryset is empty
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_tenant_user_cannot_update_tenant(self, api_client, tenant_a_user):
        """Test: Tenant user cannot update tenant (405 Method Not Allowed - read-only API)."""
        tenant = Tenant.objects.create(
            name="Isolation Update Tenant",
            slug="isolation-update-tenant",
            subdomain="isolation-update-tenant",
        )

        api_client.force_authenticate(user=tenant_a_user)
        response = api_client.patch(
            f"/api/v1/tenant-management/tenants/{tenant.id}/",
            {"name": "Hacked Tenant"},
            format="json",
        )

        # ReadOnlyModelViewSet returns 405 Method Not Allowed for PATCH
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_tenant_user_cannot_delete_tenant(self, api_client, tenant_a_user):
        """Test: Tenant user cannot delete tenant (405 Method Not Allowed - read-only API)."""
        tenant = Tenant.objects.create(
            name="Isolation Delete Tenant",
            slug="isolation-delete-tenant",
            subdomain="isolation-delete-tenant",
        )

        api_client.force_authenticate(user=tenant_a_user)
        response = api_client.delete(f"/api/v1/tenant-management/tenants/{tenant.id}/")

        # ReadOnlyModelViewSet returns 405 Method Not Allowed for DELETE
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_tenant_user_cannot_manage_modules(self, api_client, tenant_a_user):
        """Test: Tenant user cannot manage tenant modules."""
        Tenant.objects.create(
            name="Isolation Module Tenant",
            slug="isolation-module-tenant",
            subdomain="isolation-module-tenant",
        )

        api_client.force_authenticate(user=tenant_a_user)
        response = api_client.get("/api/v1/tenant-management/modules/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 0  # Empty queryset

    def test_tenant_user_cannot_manage_settings(self, api_client, tenant_a_user):
        """Test: Tenant user cannot manage tenant settings."""
        Tenant.objects.create(
            name="Isolation Settings Tenant",
            slug="isolation-settings-tenant",
            subdomain="isolation-settings-tenant",
        )

        api_client.force_authenticate(user=tenant_a_user)
        response = api_client.get("/api/v1/tenant-management/settings/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 0  # Empty queryset

    def test_platform_owner_can_access_all_tenants(self, api_client, platform_owner):
        """Test: Platform owner can access all tenants."""
        tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a", subdomain="tenant-a")
        tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b", subdomain="tenant-b")

        api_client.force_authenticate(user=platform_owner)
        response = api_client.get("/api/v1/tenant-management/tenants/")

        assert response.status_code == status.HTTP_200_OK
        # DRF may return paginated or direct list
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        tenant_ids = [t["id"] for t in data]
        assert tenant_a.id in tenant_ids
        assert tenant_b.id in tenant_ids
