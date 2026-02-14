"""
Model tests for Sales Management module.
"""

import uuid
import pytest
from datetime import date

from src.modules.sales_management.models import Customer, SalesOrder


@pytest.mark.django_db
class TestCustomerModel:
    """Test Customer model."""

    def test_create_customer(self):
        """Test creating a customer."""
        tenant_id = uuid.uuid4()
        customer = Customer.objects.create(
            tenant_id=tenant_id,
            customer_code="CUST-001",
            customer_name="Test Customer",
        )
        assert customer.customer_code == "CUST-001"
        assert customer.customer_name == "Test Customer"
        assert customer.is_active is True


@pytest.mark.django_db
class TestSalesOrderModel:
    """Test SalesOrder model."""

    def test_create_sales_order(self):
        """Test creating a sales order."""
        tenant_id = uuid.uuid4()
        customer = Customer.objects.create(
            tenant_id=tenant_id,
            customer_code="CUST-001",
            customer_name="Test Customer",
        )

        order = SalesOrder.objects.create(
            tenant_id=tenant_id,
            order_number="SO-001",
            order_date=date(2024, 1, 1),
            customer=customer,
        )

        assert order.order_number == "SO-001"
        assert order.customer == customer
        assert order.status == "draft"
