"""
Model Unit Tests for BackupDisasterRecovery module.

Tests model creation, validation, and relationships.
"""
import pytest
from django.core.exceptions import ValidationError

from ..models import BackupDisasterRecoveryResource


@pytest.mark.django_db
class TestBackupDisasterRecoveryResourceModel:
    """Test BackupDisasterRecoveryResource model."""

    def test_create_resource(self, db):
        """Test creating a resource."""
        resource = BackupDisasterRecoveryResource.objects.create(
            tenant_id="tenant-123",
            name="Test Resource",
            description="Test description",
            created_by="user-123",
        )
        assert resource.id is not None
        assert resource.name == "Test Resource"
        assert resource.tenant_id == "tenant-123"
        assert resource.is_active is True

    def test_resource_str_representation(self, db):
        """Test resource string representation."""
        resource = BackupDisasterRecoveryResource.objects.create(
            tenant_id="tenant-123",
            name="Test Resource",
            created_by="user-123",
        )
        assert str(resource) == f"Test Resource ({resource.id})"

    def test_resource_has_tenant_id(self, db):
        """Test that resource requires tenant_id."""
        resource = BackupDisasterRecoveryResource(
            name="Test Resource",
            created_by="user-123",
        )
        # Should raise error if tenant_id is missing
        with pytest.raises(Exception):
            resource.save()

    def test_resource_config_field(self, db):
        """Test resource config JSON field."""
        config = {"key1": "value1", "key2": 123}
        resource = BackupDisasterRecoveryResource.objects.create(
            tenant_id="tenant-123",
            name="Test Resource",
            config=config,
            created_by="user-123",
        )
        assert resource.config == config
