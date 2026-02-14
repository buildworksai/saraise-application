"""
Business logic services for Inventory Management module.
"""

from decimal import Decimal
from typing import Optional

from django.db import transaction

from .models import Item, StockBalance, StockEntry, StockEntryLine, Warehouse


class WarehouseService:
    """Service for warehouse operations."""

    @staticmethod
    def create_warehouse(tenant_id: str, warehouse_code: str, warehouse_name: str, **kwargs) -> Warehouse:
        """Create a new warehouse."""
        return Warehouse.objects.create(
            tenant_id=tenant_id,
            warehouse_code=warehouse_code,
            warehouse_name=warehouse_name,
            **kwargs,
        )


class StockService:
    """Service for stock operations."""

    @staticmethod
    @transaction.atomic
    def process_stock_entry(stock_entry: StockEntry) -> StockEntry:
        """Process a stock entry and update stock balances."""
        for line in stock_entry.lines.all():
            stock_balance, created = StockBalance.objects.get_or_create(
                tenant_id=stock_entry.tenant_id,
                item=line.item,
                warehouse=stock_entry.warehouse,
                defaults={
                    "quantity_on_hand": Decimal("0.00"),
                    "quantity_allocated": Decimal("0.00"),
                    "quantity_available": Decimal("0.00"),
                },
            )

            if stock_entry.entry_type in ["receipt", "adjustment"]:
                stock_balance.quantity_on_hand += line.quantity
            elif stock_entry.entry_type in ["issue", "transfer"]:
                stock_balance.quantity_on_hand -= line.quantity

            stock_balance.quantity_available = stock_balance.quantity_on_hand - stock_balance.quantity_allocated
            stock_balance.save()

        stock_entry.status = "completed"
        stock_entry.save()

        return stock_entry
