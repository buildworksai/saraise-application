"""
Service tests for Inventory Management module.
"""

import uuid
import pytest

from src.modules.inventory_management.models import Warehouse
from src.modules.inventory_management.services import WarehouseService


@pytest.mark.django_db
class TestWarehouseService:
    """Test WarehouseService."""

    def test_create_warehouse(self):
        """Test creating a warehouse via service."""
        tenant_id = uuid.uuid4()
        warehouse = WarehouseService.create_warehouse(
            tenant_id=str(tenant_id),
            warehouse_code="WH-01",
            warehouse_name="Main Warehouse",
        )

        assert warehouse.warehouse_code == "WH-01"
        assert warehouse.warehouse_name == "Main Warehouse"
        assert str(warehouse.tenant_id) == str(tenant_id)
