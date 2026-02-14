"""
Model tests for Inventory Management module.
"""

import uuid
import pytest
from decimal import Decimal

from src.modules.inventory_management.models import Item, Warehouse


@pytest.mark.django_db
class TestWarehouseModel:
    """Test Warehouse model."""

    def test_create_warehouse(self):
        """Test creating a warehouse."""
        tenant_id = uuid.uuid4()
        warehouse = Warehouse.objects.create(
            tenant_id=tenant_id,
            warehouse_code="WH-01",
            warehouse_name="Main Warehouse",
        )
        assert warehouse.warehouse_code == "WH-01"
        assert warehouse.warehouse_name == "Main Warehouse"
        assert warehouse.is_active is True


@pytest.mark.django_db
class TestItemModel:
    """Test Item model."""

    def test_create_item(self):
        """Test creating an item."""
        tenant_id = uuid.uuid4()
        item = Item.objects.create(
            tenant_id=tenant_id,
            item_code="ITEM-001",
            item_name="Test Item",
        )
        assert item.item_code == "ITEM-001"
        assert item.item_name == "Test Item"
        assert item.is_active is True
