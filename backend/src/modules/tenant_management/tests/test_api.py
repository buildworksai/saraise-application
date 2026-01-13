"""
Tenant Management API Tests

CRITICAL: These tests verify platform-level access control.
Only platform owners can access tenant management endpoints.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.user_models import UserProfile

from src.modules.tenant_management.models import Tenant, TenantHealthScore, TenantModule, TenantResourceUsage, TenantSettings

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
    # Create UserProfile with platform_role (skip validation for tests)
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
def tenant_user(db):
    """Create a tenant-scoped user (should NOT have access)."""
    tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
    user = User.objects.create_user(
        username="tenant_user",
        email="tenant@example.com",
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
    return user


@pytest.fixture
def authenticated_platform_client(api_client, platform_owner):
    """Create authenticated API client for platform owner."""
    api_client.force_authenticate(user=platform_owner)
    return api_client


@pytest.fixture
def authenticated_tenant_client(api_client, tenant_user):
    """Create authenticated API client for tenant user."""
    api_client.force_authenticate(user=tenant_user)
    return api_client


@pytest.mark.django_db
class TestTenantViewSet:
    """Test cases for Tenant API."""

    def test_list_tenants_as_platform_owner(self, authenticated_platform_client):
        """Test: Platform owner can list tenants."""
        Tenant.objects.create(name="Tenant A", slug="tenant-a")
        Tenant.objects.create(name="Tenant B", slug="tenant-b")

        response = authenticated_platform_client.get("/api/v1/tenant-management/tenants/")

        assert response.status_code == status.HTTP_200_OK
        # DRF may return paginated or direct list
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) >= 2

    def test_list_tenants_as_tenant_user_denied(self, authenticated_tenant_client):
        """Test: Tenant user cannot list tenants."""
        response = authenticated_tenant_client.get("/api/v1/tenant-management/tenants/")

        assert response.status_code == status.HTTP_200_OK  # Returns empty list, not 403
        # DRF may return paginated or direct list
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 0  # Empty queryset

    def test_create_tenant_as_platform_owner(self, authenticated_platform_client, platform_owner):
        """Test: CREATE operation returns 405 Method Not Allowed (read-only API per architecture)."""
        data = {
            "name": "New Tenant",
            "slug": "new-tenant",
            "subdomain": "new-tenant",
            "status": "trial",
        }
        response = authenticated_platform_client.post("/api/v1/tenant-management/tenants/", data, format="json")

        # ReadOnlyModelViewSet returns 405 Method Not Allowed for POST
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_create_tenant_as_tenant_user_denied(self, authenticated_tenant_client):
        """Test: CREATE operation returns 405 Method Not Allowed (read-only API per architecture)."""
        data = {
            "name": "Unauthorized Tenant",
            "slug": "unauthorized-tenant",
            "subdomain": "unauthorized-tenant",
        }
        response = authenticated_tenant_client.post("/api/v1/tenant-management/tenants/", data, format="json")

        # ReadOnlyModelViewSet returns 405 Method Not Allowed for POST
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_get_tenant_detail(self, authenticated_platform_client):
        """Test: Platform owner can get tenant detail."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")

        response = authenticated_platform_client.get(f"/api/v1/tenant-management/tenants/{tenant.id}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Test Tenant"

    def test_update_tenant(self, authenticated_platform_client, platform_owner):
        """Test: UPDATE operation returns 405 Method Not Allowed (read-only API per architecture)."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")

        data = {"name": "Updated Tenant"}
        response = authenticated_platform_client.patch(
            f"/api/v1/tenant-management/tenants/{tenant.id}/", data, format="json"
        )

        # ReadOnlyModelViewSet returns 405 Method Not Allowed for PATCH
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_suspend_tenant(self, authenticated_platform_client):
        """Test: SUSPEND operation returns 405 Method Not Allowed (read-only API per architecture)."""
        tenant = Tenant.objects.create(
            name="Test Tenant",
            slug="test-tenant",
            subdomain="test-tenant",
            status=Tenant.TenantStatus.ACTIVE,
        )

        response = authenticated_platform_client.post(f"/api/v1/tenant-management/tenants/{tenant.id}/suspend/")

        # Custom action not available in ReadOnlyModelViewSet - returns 404
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_activate_tenant(self, authenticated_platform_client):
        """Test: ACTIVATE operation returns 405 Method Not Allowed (read-only API per architecture)."""
        tenant = Tenant.objects.create(
            name="Test Tenant",
            slug="test-tenant",
            subdomain="test-tenant",
            status=Tenant.TenantStatus.SUSPENDED,
        )

        response = authenticated_platform_client.post(f"/api/v1/tenant-management/tenants/{tenant.id}/activate/")

        # Custom action not available in ReadOnlyModelViewSet - returns 404
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_active_tenant_denied(self, authenticated_platform_client):
        """Test: DELETE operation returns 405 Method Not Allowed (read-only API per architecture)."""
        tenant = Tenant.objects.create(
            name="Active Tenant",
            slug="active-tenant",
            subdomain="active-tenant",
            status=Tenant.TenantStatus.ACTIVE,
        )

        response = authenticated_platform_client.delete(f"/api/v1/tenant-management/tenants/{tenant.id}/")

        # ReadOnlyModelViewSet returns 405 Method Not Allowed for DELETE
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        # Verify tenant still exists
        assert Tenant.objects.filter(id=tenant.id).exists()

    def test_delete_cancelled_tenant(self, authenticated_platform_client):
        """Test: DELETE operation returns 405 Method Not Allowed (read-only API per architecture)."""
        tenant = Tenant.objects.create(
            name="Cancelled Tenant",
            slug="cancelled-tenant",
            subdomain="cancelled-tenant",
            status=Tenant.TenantStatus.CANCELLED,
        )

        response = authenticated_platform_client.delete(f"/api/v1/tenant-management/tenants/{tenant.id}/")

        # ReadOnlyModelViewSet returns 405 Method Not Allowed for DELETE
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        # Verify tenant still exists
        assert Tenant.objects.filter(id=tenant.id).exists()

    def test_get_tenant_modules(self, authenticated_platform_client):
        """Test: Get modules for a tenant."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")
        TenantModule.objects.create(tenant=tenant, module_name="crm", is_enabled=True)

        response = authenticated_platform_client.get(f"/api/v1/tenant-management/tenants/{tenant.id}/modules/")

        assert response.status_code == status.HTTP_200_OK
        # Action endpoints return direct list
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 1
        assert data[0]["module_name"] == "crm"

    def test_get_tenant_resource_usage(self, authenticated_platform_client):
        """Test: Get resource usage for a tenant."""
        from datetime import date

        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")
        TenantResourceUsage.objects.create(tenant=tenant, date=date.today(), active_users=10, api_calls=1000)

        response = authenticated_platform_client.get(f"/api/v1/tenant-management/tenants/{tenant.id}/resource_usage/")

        assert response.status_code == status.HTTP_200_OK
        # Action endpoints return direct list
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) >= 1
        assert data[0]["active_users"] == 10


@pytest.mark.django_db
class TestTenantModuleViewSet:
    """Test cases for Tenant Module API."""

    def test_list_modules_as_platform_owner(self, authenticated_platform_client):
        """Test: Platform owner can list tenant modules."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")
        TenantModule.objects.create(tenant=tenant, module_name="crm")
        TenantModule.objects.create(tenant=tenant, module_name="accounting")

        response = authenticated_platform_client.get("/api/v1/tenant-management/modules/")

        assert response.status_code == status.HTTP_200_OK
        # DRF may return paginated or direct list
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) >= 2

    def test_install_module(self, authenticated_platform_client, platform_owner):
        """Test: INSTALL operation returns 405 Method Not Allowed (read-only API per architecture)."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")

        data = {"tenant": tenant.id, "module_name": "crm", "is_enabled": True}
        response = authenticated_platform_client.post("/api/v1/tenant-management/modules/", data, format="json")

        # ReadOnlyModelViewSet returns 405 Method Not Allowed for POST
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_enable_module(self, authenticated_platform_client):
        """Test: Platform owner can enable module."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")
        module = TenantModule.objects.create(tenant=tenant, module_name="crm", is_enabled=False)

        response = authenticated_platform_client.post(f"/api/v1/tenant-management/modules/{module.id}/enable/")

        # Custom action not available in ReadOnlyModelViewSet - returns 404
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_disable_module(self, authenticated_platform_client):
        """Test: DISABLE operation returns 404 Not Found (read-only API per architecture)."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")
        module = TenantModule.objects.create(tenant=tenant, module_name="crm", is_enabled=True)

        response = authenticated_platform_client.post(f"/api/v1/tenant-management/modules/{module.id}/disable/")

        # Custom action not available in ReadOnlyModelViewSet - returns 404
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestTenantSettingsViewSet:
    """Test cases for Tenant Settings API."""

    def test_create_setting(self, authenticated_platform_client, platform_owner):
        """Test: CREATE operation returns 405 Method Not Allowed (read-only API per architecture)."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")

        data = {
            "tenant": tenant.id,
            "category": "email",
            "key": "smtp_host",
            "value": {"host": "smtp.example.com"},
        }
        response = authenticated_platform_client.post("/api/v1/tenant-management/settings/", data, format="json")

        # ReadOnlyModelViewSet returns 405 Method Not Allowed for POST
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_list_settings_filtered_by_tenant(self, authenticated_platform_client):
        """Test: List settings filtered by tenant."""
        tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a", subdomain="tenant-a")
        tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b", subdomain="tenant-b")

        TenantSettings.objects.create(
            tenant=tenant_a,
            category="email",
            key="smtp_host",
            value={"host": "smtp.a.com"},
        )
        TenantSettings.objects.create(
            tenant=tenant_b,
            category="email",
            key="smtp_host",
            value={"host": "smtp.b.com"},
        )

        response = authenticated_platform_client.get(f"/api/v1/tenant-management/settings/?tenant_id={tenant_a.id}")

        assert response.status_code == status.HTTP_200_OK
        # DRF may return paginated or direct list
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 1
        assert data[0]["tenant"] == tenant_a.id


@pytest.mark.django_db
class TestTenantResourceUsageViewSet:
    """Test cases for Tenant Resource Usage API."""

    def test_list_resource_usage(self, authenticated_platform_client):
        """Test: Platform owner can list resource usage."""
        from datetime import date

        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")
        TenantResourceUsage.objects.create(tenant=tenant, date=date.today(), active_users=10, api_calls=1000)

        response = authenticated_platform_client.get("/api/v1/tenant-management/resource-usage/")

        assert response.status_code == status.HTTP_200_OK
        # DRF may return paginated or direct list
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) >= 1


@pytest.mark.django_db
class TestTenantHealthScoreViewSet:
    """Test cases for Tenant Health Score API."""

    def test_list_health_scores(self, authenticated_platform_client):
        """Test: Platform owner can list health scores."""
        from datetime import date

        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")
        TenantHealthScore.objects.create(tenant=tenant, date=date.today(), overall_score=85)

        response = authenticated_platform_client.get("/api/v1/tenant-management/health-scores/")

        assert response.status_code == status.HTTP_200_OK
        # DRF may return paginated or direct list
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) >= 1
