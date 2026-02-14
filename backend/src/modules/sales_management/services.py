"""
Business logic services for Sales Management module.
"""

from typing import Optional

from django.db import transaction

from .models import Customer, Quotation, SalesOrder


class CustomerService:
    """Service for customer operations."""

    @staticmethod
    def create_customer(tenant_id: str, customer_code: str, customer_name: str, **kwargs) -> Customer:
        """Create a new customer."""
        return Customer.objects.create(
            tenant_id=tenant_id,
            customer_code=customer_code,
            customer_name=customer_name,
            **kwargs,
        )


class QuotationService:
    """Service for quotation operations."""

    @staticmethod
    def convert_to_sales_order(quotation: Quotation) -> SalesOrder:
        """Convert a quotation to a sales order."""
        sales_order = SalesOrder.objects.create(
            tenant_id=quotation.tenant_id,
            order_date=quotation.quotation_date,
            customer=quotation.customer,
            quotation=quotation,
            total_amount=quotation.total_amount,
            currency=quotation.currency,
            status="draft",
        )
        quotation.status = "converted"
        quotation.save()
        return sales_order


class SalesOrderService:
    """Service for sales order operations."""

    @staticmethod
    @transaction.atomic
    def confirm_order(sales_order: SalesOrder) -> SalesOrder:
        """Confirm a sales order."""
        sales_order.status = "confirmed"
        sales_order.save()
        return sales_order
