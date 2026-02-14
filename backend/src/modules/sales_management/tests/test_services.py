"""
Service tests for Sales Management module.
"""

import uuid
import pytest
from datetime import date

from src.modules.sales_management.models import Customer, Quotation, SalesOrder
from src.modules.sales_management.services import CustomerService, QuotationService


@pytest.mark.django_db
class TestCustomerService:
    """Test CustomerService."""

    def test_create_customer(self):
        """Test creating a customer via service."""
        tenant_id = uuid.uuid4()
        customer = CustomerService.create_customer(
            tenant_id=str(tenant_id),
            customer_code="CUST-001",
            customer_name="Test Customer",
        )

        assert customer.customer_code == "CUST-001"
        assert customer.customer_name == "Test Customer"
        assert str(customer.tenant_id) == str(tenant_id)


@pytest.mark.django_db
class TestQuotationService:
    """Test QuotationService."""

    def test_convert_to_sales_order(self):
        """Test converting quotation to sales order."""
        tenant_id = uuid.uuid4()
        customer = Customer.objects.create(
            tenant_id=tenant_id,
            customer_code="CUST-001",
            customer_name="Test Customer",
        )

        quotation = Quotation.objects.create(
            tenant_id=tenant_id,
            quotation_number="QT-001",
            quotation_date=date(2024, 1, 1),
            customer=customer,
            total_amount=1000.00,
        )

        sales_order = QuotationService.convert_to_sales_order(quotation)

        assert sales_order.customer == customer
        assert sales_order.quotation == quotation
        assert sales_order.total_amount == quotation.total_amount
        assert quotation.status == "converted"
