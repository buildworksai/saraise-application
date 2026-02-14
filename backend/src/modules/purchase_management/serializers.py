"""
DRF Serializers for Purchase Management module.
"""

from rest_framework import serializers

from .models import PurchaseOrder, PurchaseReceipt, PurchaseRequisition, Supplier


class SupplierSerializer(serializers.ModelSerializer):
    """Supplier serializer."""

    class Meta:
        model = Supplier
        fields = [
            "id",
            "tenant_id",
            "supplier_code",
            "supplier_name",
            "email",
            "phone",
            "address",
            "payment_terms",
            "currency",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class PurchaseRequisitionSerializer(serializers.ModelSerializer):
    """PurchaseRequisition serializer."""

    class Meta:
        model = PurchaseRequisition
        fields = [
            "id",
            "tenant_id",
            "requisition_number",
            "requisition_date",
            "required_date",
            "purpose",
            "status",
            "requested_by",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "requisition_number",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    """PurchaseOrder serializer."""

    supplier_code = serializers.CharField(source="supplier.supplier_code", read_only=True)
    supplier_name = serializers.CharField(source="supplier.supplier_name", read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "tenant_id",
            "po_number",
            "po_date",
            "supplier",
            "supplier_code",
            "supplier_name",
            "expected_delivery_date",
            "total_amount",
            "currency",
            "status",
            "requisition",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "po_number",
            "total_amount",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ]


class PurchaseReceiptSerializer(serializers.ModelSerializer):
    """PurchaseReceipt serializer."""

    po_number = serializers.CharField(source="purchase_order.po_number", read_only=True)
    supplier_name = serializers.CharField(source="purchase_order.supplier.supplier_name", read_only=True)

    class Meta:
        model = PurchaseReceipt
        fields = [
            "id",
            "tenant_id",
            "receipt_number",
            "receipt_date",
            "purchase_order",
            "po_number",
            "supplier_name",
            "warehouse_id",
            "status",
            "received_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "receipt_number", "created_at", "updated_at"]
