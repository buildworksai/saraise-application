"""
Business logic services for Purchase Management module.
"""

from typing import Optional

from django.db import transaction

from .models import PurchaseOrder, PurchaseReceipt, Supplier


class SupplierService:
    """Service for supplier operations."""

    @staticmethod
    def create_supplier(tenant_id: str, supplier_code: str, supplier_name: str, **kwargs) -> Supplier:
        """Create a new supplier."""
        return Supplier.objects.create(
            tenant_id=tenant_id,
            supplier_code=supplier_code,
            supplier_name=supplier_name,
            **kwargs,
        )


class PurchaseOrderService:
    """Service for purchase order operations."""

    @staticmethod
    @transaction.atomic
    def create_purchase_order(tenant_id: str, supplier_id: str, po_date: str, **kwargs) -> PurchaseOrder:
        """Create a new purchase order."""
        po = PurchaseOrder.objects.create(
            tenant_id=tenant_id,
            supplier_id=supplier_id,
            po_date=po_date,
            **kwargs,
        )
        return po


class PurchaseReceiptService:
    """Service for purchase receipt operations."""

    @staticmethod
    @transaction.atomic
    def process_receipt(purchase_receipt: PurchaseReceipt) -> PurchaseReceipt:
        """Process a purchase receipt and update stock."""
        # Update purchase order line received quantities
        for line in purchase_receipt.lines.all():
            po_line = line.purchase_order_line
            po_line.received_quantity += line.quantity_received
            po_line.save()

        purchase_receipt.status = "completed"
        purchase_receipt.save()

        return purchase_receipt
