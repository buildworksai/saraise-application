"""Declared tenant-query index proofs."""

from src.modules.purchase_management.models import ProcurementConfiguration, PurchaseOrder, PurchaseReceipt, Supplier


def test_hot_query_indexes_begin_with_tenant_boundary():
    for model in (Supplier, PurchaseOrder, PurchaseReceipt, ProcurementConfiguration):
        assert model._meta.indexes
        assert all(index.fields[0] == "tenant_id" for index in model._meta.indexes)
