"""Operation-specific serializers for Asset Management."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from .models import Asset, AssetCategory, DepreciationEntry, DepreciationMethod

SERVER_OWNED_FIELDS = frozenset(
    {"id", "tenant_id", "current_value", "created_at", "updated_at", "deleted_at", "is_deleted"}
)


class StrictInputFieldsMixin:
    """Reject unknown and server-owned input instead of silently ignoring it."""

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        supplied = set(getattr(self, "initial_data", {}))
        server_owned = supplied.intersection(SERVER_OWNED_FIELDS)
        if server_owned:
            raise serializers.ValidationError({field: "This field is server-owned." for field in sorted(server_owned)})
        unknown = supplied.difference(self.fields)
        if unknown:
            raise serializers.ValidationError({field: "Unknown field." for field in sorted(unknown)})
        return super().validate(attrs)  # type: ignore[misc]


ASSET_READ_FIELDS = (
    "id",
    "tenant_id",
    "asset_code",
    "asset_name",
    "category",
    "purchase_date",
    "purchase_cost",
    "residual_value",
    "current_value",
    "depreciation_method",
    "useful_life_years",
    "declining_balance_rate",
    "location",
    "is_active",
    "created_at",
    "updated_at",
)


class AssetListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ASSET_READ_FIELDS
        read_only_fields = ASSET_READ_FIELDS


class AssetDetailSerializer(AssetListSerializer):
    """Detail representation retained separately for API evolution."""


class AssetWriteSerializer(StrictInputFieldsMixin, serializers.Serializer):
    asset_code = serializers.CharField(max_length=50)
    asset_name = serializers.CharField(max_length=255)
    category = serializers.ChoiceField(choices=AssetCategory.choices, default=AssetCategory.FIXED)
    purchase_date = serializers.DateField()
    purchase_cost = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal("0.01"))
    residual_value = serializers.DecimalField(
        max_digits=15,
        decimal_places=2,
        min_value=Decimal("0.00"),
        default=Decimal("0.00"),
    )
    depreciation_method = serializers.ChoiceField(
        choices=DepreciationMethod.choices,
        default=DepreciationMethod.NONE,
    )
    useful_life_years = serializers.IntegerField(min_value=1, max_value=100, allow_null=True, required=False)
    declining_balance_rate = serializers.DecimalField(
        max_digits=7,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        max_value=Decimal("100.0000"),
        allow_null=True,
        required=False,
    )
    location = serializers.CharField(max_length=255, allow_blank=True, required=False, default="")
    is_active = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        method = attrs.get("depreciation_method")
        category = attrs.get("category")
        if method != DepreciationMethod.NONE and not attrs.get("useful_life_years"):
            raise serializers.ValidationError({"useful_life_years": "This field is required for depreciation."})
        if method != DepreciationMethod.DECLINING_BALANCE and attrs.get("declining_balance_rate") is not None:
            raise serializers.ValidationError(
                {"declining_balance_rate": "This field is only valid for declining balance."}
            )
        if category == AssetCategory.CURRENT and method != DepreciationMethod.NONE:
            raise serializers.ValidationError({"depreciation_method": "Current assets are not depreciated."})
        if attrs["residual_value"] > attrs["purchase_cost"]:
            raise serializers.ValidationError({"residual_value": "Cannot exceed purchase cost."})
        return attrs


class AssetUpdateSerializer(StrictInputFieldsMixin, serializers.Serializer):
    asset_code = serializers.CharField(max_length=50, required=False)
    asset_name = serializers.CharField(max_length=255, required=False)
    category = serializers.ChoiceField(choices=AssetCategory.choices, required=False)
    purchase_date = serializers.DateField(required=False)
    purchase_cost = serializers.DecimalField(
        max_digits=15,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
    )
    residual_value = serializers.DecimalField(
        max_digits=15,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
    )
    depreciation_method = serializers.ChoiceField(choices=DepreciationMethod.choices, required=False)
    useful_life_years = serializers.IntegerField(min_value=1, max_value=100, allow_null=True, required=False)
    declining_balance_rate = serializers.DecimalField(
        max_digits=7,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        max_value=Decimal("100.0000"),
        allow_null=True,
        required=False,
    )
    location = serializers.CharField(max_length=255, allow_blank=True, required=False)
    is_active = serializers.BooleanField(required=False)


class DepreciationCalculationSerializer(StrictInputFieldsMixin, serializers.Serializer):
    entry_date = serializers.DateField()


class DepreciationEntrySerializer(serializers.ModelSerializer):
    asset_code = serializers.CharField(source="asset.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset.asset_name", read_only=True)

    class Meta:
        model = DepreciationEntry
        fields = (
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
        )
        read_only_fields = fields


# Backward-compatible public import used by existing module consumers.
AssetSerializer = AssetDetailSerializer


__all__ = [
    "AssetDetailSerializer",
    "AssetListSerializer",
    "AssetSerializer",
    "AssetUpdateSerializer",
    "AssetWriteSerializer",
    "DepreciationCalculationSerializer",
    "DepreciationEntrySerializer",
]
