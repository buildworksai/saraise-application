"""
DRF Serializers for Asset Management module.
"""

from rest_framework import serializers

from .models import Asset, DepreciationEntry


class AssetSerializer(serializers.ModelSerializer):
    """Asset serializer."""

    class Meta:
        model = Asset
        fields = [
            "id",
            "tenant_id",
            "asset_code",
            "asset_name",
            "category",
            "purchase_date",
            "purchase_cost",
            "current_value",
            "depreciation_method",
            "useful_life_years",
            "location",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "current_value", "created_at", "updated_at"]


class DepreciationEntrySerializer(serializers.ModelSerializer):
    """DepreciationEntry serializer."""

    asset_code = serializers.CharField(source="asset.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset.asset_name", read_only=True)

    class Meta:
        model = DepreciationEntry
        fields = [
            "id",
            "tenant_id",
            "asset",
            "asset_code",
            "asset_name",
            "entry_date",
            "depreciation_amount",
            "accumulated_depreciation",
            "book_value",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]
