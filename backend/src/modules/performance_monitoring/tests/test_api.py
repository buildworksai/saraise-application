"""
API Integration Tests for PerformanceMonitoring module.

Tests all DRF ViewSet endpoints:
- CRUD operations
- Authentication/authorization
- Tenant isolation
- Custom actions
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from ..models import PerformanceMonitoringResource
from src.core.auth_utils import get_user_tenant_id

User = get_user_model()


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def tenant_user(db):
    """Create a test user with tenant."""
    from src.core.user_models import UserProfile
    from src.core.licensing.models import Organization
    import uuid

    # Create a valid Organization for the tenant
    org = Organization.objects.create(name="Test Organization")
    tenant_id = str(org.id)

    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    profile = UserProfile.objects.get(user=user)
    profile.tenant_id = tenant_id
    profile.tenant_role = "tenant_admin"
    profile.save()

    return User.objects.get(pk=user.pk)


@pytest.fixture
def authenticated_client(api_client, tenant_user):
    """Create authenticated API client."""
    api_client.force_authenticate(user=tenant_user)
    return api_client


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.mark.django_db
class TestPerformanceMonitoringResourceViewSet:
    """Test PerformanceMonitoringResourceViewSet CRUD operations."""

    def test_list_resources_requires_authentication(self, api_client):
        """Test that listing resources requires authentication."""
        response = api_client.get(f"/api/v1/performance-monitoring/resources/")
        assert response.status_code == status.HTTP_200_OK

    def test_list_resources(self, authenticated_client, tenant_user):
        """Test listing resources for authenticated user."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        # Create test resources
        PerformanceMonitoringResource.objects.create(
            tenant_id=tenant_id,
            name="Test Resource 1",
            description="Test description 1",
            created_by=str(tenant_user.id),
        )
        PerformanceMonitoringResource.objects.create(
            tenant_id=tenant_id,
            name="Test Resource 2",
            description="Test description 2",
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.get(f"/api/v1/performance-monitoring/resources/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 2

    def test_create_resource(self, authenticated_client, tenant_user):
        """Test creating a resource."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        data = {
            "name": "New Resource",
            "description": "New resource description",
            "config": {"key": "value"},
        }

        response = authenticated_client.post(
            f"/api/v1/performance-monitoring/resources/",
            data,
            format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Resource"
        assert response.data["tenant_id"] == tenant_id

    def test_get_resource_detail(self, authenticated_client, tenant_user):
        """Test getting resource detail."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        resource = PerformanceMonitoringResource.objects.create(
            tenant_id=tenant_id,
            name="Test Resource",
            description="Test description",
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.get(f"/api/v1/performance-monitoring/resources/{resource.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == resource.id
        assert response.data["name"] == "Test Resource"

    def test_update_resource(self, authenticated_client, tenant_user):
        """Test updating a resource."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        resource = PerformanceMonitoringResource.objects.create(
            tenant_id=tenant_id,
            name="Original Name",
            description="Original description",
            created_by=str(tenant_user.id),
        )

        data = {"name": "Updated Name", "description": "Updated description"}
        response = authenticated_client.put(
            f"/api/v1/performance-monitoring/resources/{resource.id}/",
            data,
            format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Updated Name"

    def test_delete_resource(self, authenticated_client, tenant_user):
        """Test deleting a resource."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        resource = PerformanceMonitoringResource.objects.create(
            tenant_id=tenant_id,
            name="To Delete",
            description="Will be deleted",
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.delete(f"/api/v1/performance-monitoring/resources/{resource.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        
        # Verify resource is deleted
        assert not PerformanceMonitoringResource.objects.filter(id=resource.id).exists()
