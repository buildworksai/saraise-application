"""
Service Unit Tests for Regional module.

Tests business logic in services layer.
"""
import pytest

from ..models import RegionalResource
from ..services import RegionalService


@pytest.mark.django_db
class TestRegionalService:
    """Test RegionalService business logic."""

    def test_create_resource(self, db):
        """Test creating a resource via service."""
        service = RegionalService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Test Resource",
            description="Test description",
            created_by="user-123",
        )
        assert resource.id is not None
        assert resource.name == "Test Resource"
        assert resource.tenant_id == "tenant-123"

    def test_get_resource(self, db):
        """Test getting a resource by ID."""
        service = RegionalService()
        created = service.create_resource(
            tenant_id="tenant-123",
            name="Test Resource",
            created_by="user-123",
        )
        
        retrieved = service.get_resource(created.id, "tenant-123")
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "Test Resource"

    def test_get_resource_wrong_tenant(self, db):
        """Test that getting resource from wrong tenant returns None."""
        service = RegionalService()
        created = service.create_resource(
            tenant_id="tenant-123",
            name="Test Resource",
            created_by="user-123",
        )
        
        retrieved = service.get_resource(created.id, "tenant-456")
        assert retrieved is None

    def test_list_resources(self, db):
        """Test listing resources for tenant."""
        service = RegionalService()
        service.create_resource(
            tenant_id="tenant-123",
            name="Resource 1",
            created_by="user-123",
        )
        service.create_resource(
            tenant_id="tenant-123",
            name="Resource 2",
            created_by="user-123",
        )
        service.create_resource(
            tenant_id="tenant-456",
            name="Resource 3",
            created_by="user-456",
        )
        
        resources = service.list_resources("tenant-123")
        assert len(resources) == 2
        assert all(r.tenant_id == "tenant-123" for r in resources)

    def test_update_resource(self, db):
        """Test updating a resource."""
        service = RegionalService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Original Name",
            created_by="user-123",
        )
        
        updated = service.update_resource(
            resource.id,
            "tenant-123",
            name="Updated Name",
            description="Updated description",
        )
        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.description == "Updated description"

    def test_delete_resource(self, db):
        """Test deleting a resource."""
        service = RegionalService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="To Delete",
            created_by="user-123",
        )
        
        result = service.delete_resource(resource.id, "tenant-123")
        assert result is True
        assert not RegionalResource.objects.filter(id=resource.id).exists()

    def test_activate_resource(self, db):
        """Test activating a resource."""
        service = RegionalService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Test Resource",
            created_by="user-123",
        )
        resource.is_active = False
        resource.save()
        
        activated = service.activate_resource(resource.id, "tenant-123")
        assert activated is not None
        assert activated.is_active is True

    def test_deactivate_resource(self, db):
        """Test deactivating a resource."""
        service = RegionalService()
        resource = service.create_resource(
            tenant_id="tenant-123",
            name="Test Resource",
            created_by="user-123",
        )
        
        deactivated = service.deactivate_resource(resource.id, "tenant-123")
        assert deactivated is not None
        assert deactivated.is_active is False
