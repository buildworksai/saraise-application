"""
DRF Serializers for Fixed Assets module.
"""

from rest_framework import serializers

from .models import FixedAsset


class FixedAssetSerializer(serializers.ModelSerializer):
    """FixedAsset serializer."""

    class Meta:
        model = FixedAsset
        fields = [
            "id",
            "tenant_id",
            "asset_code",
            "asset_name",
            "asset_category",
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
