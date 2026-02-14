"""
Service tests for Master Data Management module.
"""

import uuid
import pytest

from src.modules.master_data_management.models import MasterDataEntity
from src.modules.master_data_management.services import MasterDataService


@pytest.mark.django_db
class TestMasterDataService:
    """Test MasterDataService."""

    def test_create_entity(self):
        """Test creating an entity via service."""
        tenant_id = uuid.uuid4()
        entity = MasterDataService.create_entity(
            tenant_id=str(tenant_id),
            entity_type="product",
            entity_code="PROD-001",
            entity_name="Test Product",
        )

        assert entity.entity_type == "product"
        assert entity.entity_code == "PROD-001"
        assert str(entity.tenant_id) == str(tenant_id)
