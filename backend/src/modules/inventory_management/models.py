"""
Inventory Management Models.

Defines data models for warehouses, stock items, stock movements, and inventory tracking.
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


class Warehouse(TenantBaseModel):
    """Warehouse model - Physical storage location."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    warehouse_code = models.CharField(max_length=50, db_index=True)
    warehouse_name = models.CharField(max_length=255)
    warehouse_type = models.CharField(max_length=50, default="distribution_center")
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "inventory_warehouses"
        indexes = [
            models.Index(fields=["tenant_id", "warehouse_code"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "warehouse_code"], name="unique_warehouse_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.warehouse_code} - {self.warehouse_name}"


class Item(TenantBaseModel):
    """Stock item model - Products/SKUs."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    item_code = models.CharField(max_length=100, db_index=True)
    item_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    barcode = models.CharField(max_length=100, blank=True, db_index=True)
    has_batch_no = models.BooleanField(default=False)
    has_serial_no = models.BooleanField(default=False)
    valuation_method = models.CharField(max_length=20, default="fifo")  # fifo, lifo, weighted_avg
    reorder_point = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    reorder_qty = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "inventory_items"
        indexes = [
            models.Index(fields=["tenant_id", "item_code"]),
            models.Index(fields=["tenant_id", "category"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "item_code"], name="unique_item_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.item_code} - {self.item_name}"


class StockEntryType(models.TextChoices):
    """Stock entry type choices."""

    RECEIPT = "receipt", "Goods Receipt"
    ISSUE = "issue", "Goods Issue"
    TRANSFER = "transfer", "Stock Transfer"
    ADJUSTMENT = "adjustment", "Stock Adjustment"
    MANUFACTURING = "manufacturing", "Manufacturing"
    RETURN = "return", "Return"
    SCRAP = "scrap", "Scrap"


class StockEntry(TenantBaseModel):
    """Stock entry - Stock movement transaction."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    entry_number = models.CharField(max_length=50, db_index=True)
    entry_type = models.CharField(max_length=50, choices=StockEntryType.choices, db_index=True)
    posting_date = models.DateField(db_index=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="stock_entries")
    reference_document = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, default="draft")

    class Meta:
        db_table = "inventory_stock_entries"
        indexes = [
            models.Index(fields=["tenant_id", "posting_date"]),
            models.Index(fields=["tenant_id", "entry_type"]),
            models.Index(fields=["tenant_id", "entry_number"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "entry_number"], name="inventory_unique_entry_number_per_tenant"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.entry_number} - {self.entry_type}"


class StockEntryLine(TenantBaseModel):
    """Stock entry line - Individual item movement in a stock entry."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    stock_entry = models.ForeignKey(StockEntry, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="stock_entry_lines")
    quantity = models.DecimalField(max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0.00"))])
    batch_no = models.CharField(max_length=100, blank=True)
    serial_no = models.CharField(max_length=100, blank=True)
    cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = "inventory_stock_entry_lines"
        indexes = [
            models.Index(fields=["tenant_id", "stock_entry"]),
            models.Index(fields=["tenant_id", "item"]),
        ]

    def __str__(self) -> str:
        return f"{self.stock_entry.entry_number} - {self.item.item_code}"


class StockBalance(TenantBaseModel):
    """Stock balance - Current stock level per item per warehouse."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="stock_balances")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="stock_balances")
    quantity_on_hand = models.DecimalField(max_digits=15, decimal_places=4, default=Decimal("0.00"))
    quantity_allocated = models.DecimalField(max_digits=15, decimal_places=4, default=Decimal("0.00"))
    quantity_available = models.DecimalField(max_digits=15, decimal_places=4, default=Decimal("0.00"))
    stock_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    valuation_rate = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = "inventory_stock_balances"
        indexes = [
            models.Index(fields=["tenant_id", "item", "warehouse"]),
            models.Index(fields=["tenant_id", "warehouse"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "item", "warehouse"], name="unique_stock_balance_per_item_warehouse"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item.item_code} @ {self.warehouse.warehouse_code}: {self.quantity_on_hand}"
