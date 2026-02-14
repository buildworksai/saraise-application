"""
DRF Serializers for Inventory Management module.
"""

from rest_framework import serializers

from .models import Item, StockBalance, StockEntry, Warehouse


class WarehouseSerializer(serializers.ModelSerializer):
    """Warehouse serializer."""

    class Meta:
        model = Warehouse
        fields = [
            "id",
            "tenant_id",
            "warehouse_code",
            "warehouse_name",
            "warehouse_type",
            "address",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class ItemSerializer(serializers.ModelSerializer):
    """Item serializer."""

    class Meta:
        model = Item
        fields = [
            "id",
            "tenant_id",
            "item_code",
            "item_name",
            "description",
            "category",
            "barcode",
            "has_batch_no",
            "has_serial_no",
            "valuation_method",
            "reorder_point",
            "reorder_qty",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class StockEntrySerializer(serializers.ModelSerializer):
    """StockEntry serializer."""

    class Meta:
        model = StockEntry
        fields = [
            "id",
            "tenant_id",
            "entry_number",
            "entry_type",
            "posting_date",
            "warehouse",
            "reference_document",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "entry_number", "created_at", "updated_at"]


class StockBalanceSerializer(serializers.ModelSerializer):
    """StockBalance serializer."""

    item_code = serializers.CharField(source="item.item_code", read_only=True)
    item_name = serializers.CharField(source="item.item_name", read_only=True)
    warehouse_code = serializers.CharField(source="warehouse.warehouse_code", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.warehouse_name", read_only=True)

    class Meta:
        model = StockBalance
        fields = [
            "id",
            "tenant_id",
            "item",
            "item_code",
            "item_name",
            "warehouse",
            "warehouse_code",
            "warehouse_name",
            "quantity_on_hand",
            "quantity_allocated",
            "quantity_available",
            "stock_value",
            "valuation_rate",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]
