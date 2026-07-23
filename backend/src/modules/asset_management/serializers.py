"""Operation-specific serializers for Asset Management."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import (
    Asset,
    AssetCategory,
    AssetManagementConfiguration,
    AssetManagementConfigurationAudit,
    AssetManagementConfigurationVersion,
    DepreciationEntry,
    DepreciationMethod,
)
from .services import DECIMAL_LIMITS, INTEGER_LIMITS

SERVER_OWNED_FIELDS = frozenset(
    {"id", "tenant_id", "current_value", "created_at", "updated_at", "deleted_at", "is_deleted", "is_active"}
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
    asset_code = serializers.CharField()
    asset_name = serializers.CharField()
    category = serializers.ChoiceField(choices=AssetCategory.choices, required=False)
    purchase_date = serializers.DateField()
    purchase_cost = serializers.CharField()
    residual_value = serializers.CharField(required=False)
    depreciation_method = serializers.ChoiceField(choices=DepreciationMethod.choices, required=False)
    useful_life_years = serializers.IntegerField(allow_null=True, required=False)
    declining_balance_rate = serializers.CharField(allow_null=True, required=False)
    location = serializers.CharField(allow_blank=True, required=False)


class AssetUpdateSerializer(StrictInputFieldsMixin, serializers.Serializer):
    asset_code = serializers.CharField(required=False)
    asset_name = serializers.CharField(required=False)
    category = serializers.ChoiceField(choices=AssetCategory.choices, required=False)
    purchase_date = serializers.DateField(required=False)
    purchase_cost = serializers.CharField(required=False)
    residual_value = serializers.CharField(required=False)
    depreciation_method = serializers.ChoiceField(choices=DepreciationMethod.choices, required=False)
    useful_life_years = serializers.IntegerField(allow_null=True, required=False)
    declining_balance_rate = serializers.CharField(allow_null=True, required=False)
    location = serializers.CharField(allow_blank=True, required=False)


class DepreciationCalculationSerializer(StrictInputFieldsMixin, serializers.Serializer):
    entry_date = serializers.DateField()


class DepreciationEntrySerializer(serializers.ModelSerializer):
    asset_code = serializers.CharField(source="asset.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset.asset_name", read_only=True)

    class Meta:
        model = DepreciationEntry
        fields = (
            "id",
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


class AssetConfigurationSerializer(serializers.ModelSerializer):
    limits = serializers.SerializerMethodField()

    class Meta:
        model = AssetManagementConfiguration
        fields = ("id", "version", "document", "limits", "updated_at")
        read_only_fields = fields

    def get_limits(self, instance: AssetManagementConfiguration) -> dict[str, tuple[object, object]]:
        del instance
        return {**INTEGER_LIMITS, **DECIMAL_LIMITS}


class AssetConfigurationVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetManagementConfigurationVersion
        fields = ("id", "version", "document", "source", "correlation_id", "created_at")
        read_only_fields = fields


class AssetConfigurationAuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetManagementConfigurationAudit
        fields = ("id", "version", "action", "previous_document", "current_document", "correlation_id", "created_at")
        read_only_fields = fields


class ConfigurationDocumentSerializer(StrictInputFieldsMixin, serializers.Serializer):
    document = serializers.JSONField()


class ConfigurationImportSerializer(StrictInputFieldsMixin, serializers.Serializer):
    configuration = serializers.JSONField()


class ConfigurationRollbackSerializer(StrictInputFieldsMixin, serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


# Backward-compatible public import used by existing module consumers.
AssetSerializer = AssetDetailSerializer


__all__ = [
    "AssetDetailSerializer",
    "AssetListSerializer",
    "AssetSerializer",
    "AssetUpdateSerializer",
    "AssetWriteSerializer",
    "AssetConfigurationAuditSerializer",
    "AssetConfigurationSerializer",
    "AssetConfigurationVersionSerializer",
    "ConfigurationDocumentSerializer",
    "ConfigurationImportSerializer",
    "ConfigurationRollbackSerializer",
    "DepreciationCalculationSerializer",
    "DepreciationEntrySerializer",
]
