"""
Model tests for Purchase Management module.
"""

import uuid
import pytest
from datetime import date

from src.modules.purchase_management.models import PurchaseOrder, Supplier


@pytest.mark.django_db
class TestSupplierModel:
    """Test Supplier model."""

    def test_create_supplier(self):
        """Test creating a supplier."""
        tenant_id = uuid.uuid4()
        supplier = Supplier.objects.create(
            tenant_id=tenant_id,
            supplier_code="SUP-001",
            supplier_name="Test Supplier",
        )
        assert supplier.supplier_code == "SUP-001"
        assert supplier.supplier_name == "Test Supplier"
        assert supplier.is_active is True


@pytest.mark.django_db
class TestPurchaseOrderModel:
    """Test PurchaseOrder model."""

    def test_create_purchase_order(self):
        """Test creating a purchase order."""
        tenant_id = uuid.uuid4()
        supplier = Supplier.objects.create(
            tenant_id=tenant_id,
            supplier_code="SUP-001",
            supplier_name="Test Supplier",
        )

        po = PurchaseOrder.objects.create(
            tenant_id=tenant_id,
            po_number="PO-001",
            po_date=date(2024, 1, 1),
            supplier=supplier,
        )

        assert po.po_number == "PO-001"
        assert po.supplier == supplier
        assert po.status == "draft"
