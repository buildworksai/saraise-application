"""
Model tests for Master Data Management module.
"""

import uuid
import pytest

from src.modules.master_data_management.models import MasterDataEntity


@pytest.mark.django_db
class TestMasterDataEntityModel:
    """Test MasterDataEntity model."""

    def test_create_entity(self):
        """Test creating a master data entity."""
        tenant_id = uuid.uuid4()
        entity = MasterDataEntity.objects.create(
            tenant_id=tenant_id,
            entity_type="customer",
            entity_code="CUST-001",
            entity_name="Test Customer",
        )
        assert entity.entity_type == "customer"
        assert entity.entity_code == "CUST-001"
        assert entity.is_active is True
