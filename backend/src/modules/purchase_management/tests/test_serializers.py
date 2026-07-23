"""Serializer boundary proofs."""

from src.modules.purchase_management.serializers import SupplierWriteSerializer


def test_write_serializer_rejects_tenant_and_state_spoofing():
    serializer = SupplierWriteSerializer(
        data={
            "supplier_code": "SUP",
            "supplier_name": "Supplier",
            "payment_terms": "Net 30",
            "currency": "USD",
            "tenant_id": "00000000-0000-0000-0000-000000000000",
            "status": "active",
        }
    )
    assert not serializer.is_valid()
    assert set(serializer.errors) == {"tenant_id", "status"}
