"""
Purchase Management Models.

Defines data models for suppliers, purchase requisitions, purchase orders, RFQs, and receipts.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class TenantBaseModel(models.Model):
    """Base model for tenant-scoped models with Row-Level Multitenancy.

    CRITICAL: All tenant-scoped models MUST inherit from this base class
    and include tenant_id. All queries MUST filter explicitly by tenant_id.
    """

    tenant_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class Supplier(TenantBaseModel):
    """Supplier model - Vendor entity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    supplier_code = models.CharField(max_length=50, db_index=True)
    supplier_name = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    payment_terms = models.CharField(max_length=50, default="Net 30")
    currency = models.CharField(max_length=3, default="USD")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "purchase_suppliers"
        indexes = [
            models.Index(fields=["tenant_id", "supplier_code"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "supplier_code"], name="unique_supplier_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.supplier_code} - {self.supplier_name}"


class PurchaseRequisitionStatus(models.TextChoices):
    """Purchase requisition status choices."""

    DRAFT = "draft", "Draft"
    PENDING_APPROVAL = "pending_approval", "Pending Approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CONVERTED = "converted", "Converted to PO"
    CANCELLED = "cancelled", "Cancelled"


class PurchaseRequisition(TenantBaseModel):
    """Purchase requisition model - Internal purchase request."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    requisition_number = models.CharField(max_length=50, db_index=True)
    requisition_date = models.DateField(db_index=True)
    required_date = models.DateField(db_index=True)
    purpose = models.TextField(blank=True)
    status = models.CharField(
        max_length=50, choices=PurchaseRequisitionStatus.choices, default=PurchaseRequisitionStatus.DRAFT
    )
    requested_by = models.UUIDField(null=True, blank=True)
    approved_by = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "purchase_requisitions"
        indexes = [
            models.Index(fields=["tenant_id", "requisition_date"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "requisition_number"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "requisition_number"], name="unique_requisition_number_per_tenant"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.requisition_number} - {self.requisition_date}"


class PurchaseOrderStatus(models.TextChoices):
    """Purchase order status choices."""

    DRAFT = "draft", "Draft"
    PENDING_APPROVAL = "pending_approval", "Pending Approval"
    APPROVED = "approved", "Approved"
    SENT = "sent", "Sent to Supplier"
    ACKNOWLEDGED = "acknowledged", "Acknowledged"
    PARTIALLY_RECEIVED = "partially_received", "Partially Received"
    RECEIVED = "received", "Fully Received"
    CANCELLED = "cancelled", "Cancelled"


class PurchaseOrder(TenantBaseModel):
    """Purchase order model - PO to supplier."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    po_number = models.CharField(max_length=50, db_index=True)
    po_date = models.DateField(db_index=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    expected_delivery_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=50, choices=PurchaseOrderStatus.choices, default=PurchaseOrderStatus.DRAFT)
    requisition = models.ForeignKey(
        PurchaseRequisition, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_orders"
    )
    approved_by = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "purchase_orders"
        indexes = [
            models.Index(fields=["tenant_id", "po_date"]),
            models.Index(fields=["tenant_id", "supplier"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "po_number"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "po_number"], name="unique_po_number_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.po_number} - {self.supplier.supplier_name}"


class PurchaseOrderLine(TenantBaseModel):
    """Purchase order line - Individual item in a purchase order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    item_id = models.UUIDField(db_index=True, help_text="FK to inventory item")
    item_code = models.CharField(max_length=100)
    item_name = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0.00"))])
    unit_price = models.DecimalField(max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0.00"))])
    total_price = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    received_quantity = models.DecimalField(max_digits=15, decimal_places=4, default=Decimal("0.00"))

    class Meta:
        db_table = "purchase_order_lines"
        indexes = [
            models.Index(fields=["tenant_id", "purchase_order"]),
            models.Index(fields=["tenant_id", "item_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.purchase_order.po_number} - {self.item_code}"

    def save(self, *args, **kwargs):
        """Calculate total_price on save."""
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)


class PurchaseReceiptStatus(models.TextChoices):
    """Purchase receipt status choices."""

    DRAFT = "draft", "Draft"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class PurchaseReceipt(TenantBaseModel):
    """Purchase receipt model - Goods receipt from supplier."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    receipt_number = models.CharField(max_length=50, db_index=True)
    receipt_date = models.DateField(db_index=True)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="receipts")
    warehouse_id = models.UUIDField(db_index=True, help_text="FK to warehouse")
    status = models.CharField(max_length=50, choices=PurchaseReceiptStatus.choices, default=PurchaseReceiptStatus.DRAFT)
    received_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "purchase_receipts"
        indexes = [
            models.Index(fields=["tenant_id", "receipt_date"]),
            models.Index(fields=["tenant_id", "purchase_order"]),
            models.Index(fields=["tenant_id", "receipt_number"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "receipt_number"], name="unique_receipt_number_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.receipt_number} - {self.purchase_order.po_number}"


class PurchaseReceiptLine(TenantBaseModel):
    """Purchase receipt line - Individual item received."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    purchase_receipt = models.ForeignKey(PurchaseReceipt, on_delete=models.CASCADE, related_name="lines")
    purchase_order_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.PROTECT, related_name="receipt_lines")
    item_id = models.UUIDField(db_index=True)
    quantity_received = models.DecimalField(
        max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0.00"))]
    )
    batch_no = models.CharField(max_length=100, blank=True)
    serial_no = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "purchase_receipt_lines"
        indexes = [
            models.Index(fields=["tenant_id", "purchase_receipt"]),
            models.Index(fields=["tenant_id", "item_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.purchase_receipt.receipt_number} - {self.quantity_received}"
