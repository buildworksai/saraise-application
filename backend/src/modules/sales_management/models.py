"""
Sales Management Models.

Defines data models for customers, quotations, sales orders, and delivery notes.
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


class Customer(TenantBaseModel):
    """Customer model - Buyer entity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    customer_code = models.CharField(max_length=50, db_index=True)
    customer_name = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    credit_limit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "sales_customers"
        indexes = [
            models.Index(fields=["tenant_id", "customer_code"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "customer_code"], name="unique_customer_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.customer_code} - {self.customer_name}"


class QuotationStatus(models.TextChoices):
    """Quotation status choices."""

    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"
    CONVERTED = "converted", "Converted to Order"


class Quotation(TenantBaseModel):
    """Quotation model - Sales quote (pre-order)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    quotation_number = models.CharField(max_length=50, db_index=True)
    quotation_date = models.DateField(db_index=True)
    valid_until = models.DateField(null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="quotations")
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=50, choices=QuotationStatus.choices, default=QuotationStatus.DRAFT)

    class Meta:
        db_table = "sales_quotations"
        indexes = [
            models.Index(fields=["tenant_id", "quotation_date"]),
            models.Index(fields=["tenant_id", "customer"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "quotation_number"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "quotation_number"], name="unique_quotation_number_per_tenant"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quotation_number} - {self.customer.customer_name}"


class SalesOrderStatus(models.TextChoices):
    """Sales order status choices."""

    DRAFT = "draft", "Draft"
    CONFIRMED = "confirmed", "Confirmed"
    PICKING = "picking", "Picking"
    PACKING = "packing", "Packing"
    READY_TO_SHIP = "ready_to_ship", "Ready to Ship"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    INVOICED = "invoiced", "Invoiced"
    CANCELLED = "cancelled", "Cancelled"


class SalesOrder(TenantBaseModel):
    """Sales order model - Confirmed customer order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    order_number = models.CharField(max_length=50, db_index=True)
    order_date = models.DateField(db_index=True)
    delivery_date = models.DateField(null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales_orders")
    quotation = models.ForeignKey(
        Quotation, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales_orders"
    )
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=50, choices=SalesOrderStatus.choices, default=SalesOrderStatus.DRAFT)
    warehouse_id = models.UUIDField(null=True, blank=True, help_text="FK to warehouse")

    class Meta:
        db_table = "sales_orders"
        indexes = [
            models.Index(fields=["tenant_id", "order_date"]),
            models.Index(fields=["tenant_id", "customer"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "order_number"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "order_number"], name="unique_order_number_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.order_number} - {self.customer.customer_name}"


class SalesOrderLine(TenantBaseModel):
    """Sales order line - Individual item in a sales order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="lines")
    item_id = models.UUIDField(db_index=True, help_text="FK to inventory item")
    item_code = models.CharField(max_length=100)
    item_name = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0.00"))])
    unit_price = models.DecimalField(max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0.00"))])
    total_price = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    delivered_quantity = models.DecimalField(max_digits=15, decimal_places=4, default=Decimal("0.00"))

    class Meta:
        db_table = "sales_order_lines"
        indexes = [
            models.Index(fields=["tenant_id", "sales_order"]),
            models.Index(fields=["tenant_id", "item_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.sales_order.order_number} - {self.item_code}"

    def save(self, *args, **kwargs):
        """Calculate total_price on save."""
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)


class DeliveryNoteStatus(models.TextChoices):
    """Delivery note status choices."""

    DRAFT = "draft", "Draft"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class DeliveryNote(TenantBaseModel):
    """Delivery note model - Shipment record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    delivery_number = models.CharField(max_length=50, db_index=True)
    delivery_date = models.DateField(db_index=True)
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="delivery_notes")
    warehouse_id = models.UUIDField(db_index=True, help_text="FK to warehouse")
    status = models.CharField(max_length=50, choices=DeliveryNoteStatus.choices, default=DeliveryNoteStatus.DRAFT)

    class Meta:
        db_table = "sales_delivery_notes"
        indexes = [
            models.Index(fields=["tenant_id", "delivery_date"]),
            models.Index(fields=["tenant_id", "sales_order"]),
            models.Index(fields=["tenant_id", "delivery_number"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "delivery_number"], name="unique_delivery_number_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.delivery_number} - {self.sales_order.order_number}"


class DeliveryNoteLine(TenantBaseModel):
    """Delivery note line - Individual item delivered."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    delivery_note = models.ForeignKey(DeliveryNote, on_delete=models.CASCADE, related_name="lines")
    sales_order_line = models.ForeignKey(SalesOrderLine, on_delete=models.PROTECT, related_name="delivery_lines")
    item_id = models.UUIDField(db_index=True)
    quantity_delivered = models.DecimalField(
        max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0.00"))]
    )
    batch_no = models.CharField(max_length=100, blank=True)
    serial_no = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "sales_delivery_note_lines"
        indexes = [
            models.Index(fields=["tenant_id", "delivery_note"]),
            models.Index(fields=["tenant_id", "item_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.delivery_note.delivery_number} - {self.quantity_delivered}"
