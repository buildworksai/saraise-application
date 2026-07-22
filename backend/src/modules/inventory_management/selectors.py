"""Tenant-safe, deterministic inventory read models.

Selectors are deliberately side-effect free.  They are the only query surface
used by :class:`InventoryQueryService`, which keeps API filtering and paid
trace enrichers away from persistence internals.
"""

from __future__ import annotations

from uuid import UUID

from django.db.models import QuerySet

from .models import (
    Batch,
    SerialNumber,
    StockBalance,
    StockLedgerEntry,
)


def balances_for_tenant(tenant_id: UUID) -> QuerySet[StockBalance]:
    return (
        StockBalance.objects.for_tenant(tenant_id)
        .select_related("item", "warehouse", "location", "batch", "serial_number", "last_ledger_entry")
        .order_by("item__item_code", "warehouse__warehouse_code", "location__location_code", "id")
    )


def ledger_for_tenant(tenant_id: UUID) -> QuerySet[StockLedgerEntry]:
    return (
        StockLedgerEntry.objects.for_tenant(tenant_id)
        .select_related("stock_entry", "stock_entry_line", "item", "warehouse", "location", "batch", "serial_number")
        .order_by("sequence", "id")
    )


def batch_trace(tenant_id: UUID, batch_id: UUID) -> QuerySet[StockLedgerEntry]:
    Batch.objects.for_tenant(tenant_id).get(pk=batch_id)
    return ledger_for_tenant(tenant_id).filter(batch_id=batch_id)


def serial_trace(tenant_id: UUID, serial_id: UUID) -> QuerySet[StockLedgerEntry]:
    SerialNumber.objects.for_tenant(tenant_id).get(pk=serial_id)
    return ledger_for_tenant(tenant_id).filter(serial_number_id=serial_id)
