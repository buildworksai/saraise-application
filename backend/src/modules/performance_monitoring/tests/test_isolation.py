"""
Tenant Isolation Tests for PerformanceMonitoring module.

CRITICAL: These tests verify that tenants cannot access each other's data.
This is the PRIMARY security mechanism for multi-tenant isolation.

Reference: saraise-documentation/rules/compliance-enforcement.md
Rule: ALL tenant-scoped queries MUST filter by tenant_id
"""
import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.performance_monitoring.models import TenantBaseModel
from src.core.auth_utils import get_user_tenant_id

User = get_user_model()


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def tenant_a_user(db):
    """Create user for tenant A."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_a",
        email="usera@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    return User.objects.get(pk=user.pk)


@pytest.fixture
def tenant_b_user(db):
    """Create user for tenant B."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_b",
        email="userb@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    return User.objects.get(pk=user.pk)


@pytest.mark.django_db
class TestPerformanceMonitoringTenantIsolation:
    """
    CRITICAL: Tenant isolation tests for TenantBaseModel model.
    These tests verify that tenants cannot access each other's resources.
    """

    def test_user_cannot_list_other_tenant_resources(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's resources in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)  # noqa: F841
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create resource for tenant A
        resource_a = TenantBaseModel.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Resource",
            description="Resource for tenant A",
            created_by=str(tenant_a_user.id),
        )

        # Create resource for tenant B
        resource_b = TenantBaseModel.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Resource",
            description="Resource for tenant B",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/performance-monitoring/resources/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        resource_ids = [r["id"] for r in data]

        # User A should see tenant A's resource, but NOT tenant B's resource
        assert resource_a.id in resource_ids
        assert resource_b.id not in resource_ids

    def test_user_cannot_get_other_tenant_resource_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's resource by ID (returns 404)."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)  # noqa: F841
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create resource for tenant B
        resource_b = TenantBaseModel.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Resource",
            description="Resource for tenant B",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's resource
        response = api_client.get(f"/api/v1/performance-monitoring/resources/{resource_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_resource(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot UPDATE other tenant's resource (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create resource for tenant B
        resource_b = TenantBaseModel.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Resource",
            description="Resource for tenant B",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to update tenant B's resource
        data = {"name": "Hacked Name"}
        response = api_client.put(
            f"/api/v1/performance-monitoring/resources/{resource_b.id}/",
            data,
            format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify resource was not modified
        resource_b.refresh_from_db()
        assert resource_b.name == "Tenant B Resource"

    def test_user_cannot_delete_other_tenant_resource(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot DELETE other tenant's resource (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create resource for tenant B
        resource_b = TenantBaseModel.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Resource",
            description="Resource for tenant B",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to delete tenant B's resource
        response = api_client.delete(f"/api/v1/performance-monitoring/resources/{resource_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify resource still exists
        assert TenantBaseModel.objects.filter(id=resource_b.id).exists()
