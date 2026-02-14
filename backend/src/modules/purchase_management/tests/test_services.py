"""
Service tests for Purchase Management module.
"""

import uuid
import pytest
from datetime import date

from src.modules.purchase_management.models import PurchaseOrder, Supplier
from src.modules.purchase_management.services import PurchaseOrderService, SupplierService


@pytest.mark.django_db
class TestSupplierService:
    """Test SupplierService."""

    def test_create_supplier(self):
        """Test creating a supplier via service."""
        tenant_id = uuid.uuid4()
        supplier = SupplierService.create_supplier(
            tenant_id=str(tenant_id),
            supplier_code="SUP-001",
            supplier_name="Test Supplier",
        )

        assert supplier.supplier_code == "SUP-001"
        assert supplier.supplier_name == "Test Supplier"
        assert str(supplier.tenant_id) == str(tenant_id)


@pytest.mark.django_db
class TestPurchaseOrderService:
    """Test PurchaseOrderService."""

    def test_create_purchase_order(self):
        """Test creating a purchase order via service."""
        tenant_id = uuid.uuid4()
        supplier = Supplier.objects.create(
            tenant_id=tenant_id,
            supplier_code="SUP-001",
            supplier_name="Test Supplier",
        )

        po = PurchaseOrderService.create_purchase_order(
            tenant_id=str(tenant_id),
            supplier_id=str(supplier.id),
            po_date=date(2024, 1, 1),
        )

        assert po.supplier == supplier
        assert str(po.tenant_id) == str(tenant_id)
