"""
DRF Serializers for Localization module.
Provides request/response validation for all models.
"""

from rest_framework import serializers

from .models import (
    CurrencyConfig,
    Language,
    LocaleConfig,
    RegionalSettings,
    Translation,
)


class LanguageSerializer(serializers.ModelSerializer):
    """Serializer for Language model (read-only, platform-level)."""

    class Meta:
        model = Language
        fields = [
            "id",
            "code",
            "name",
            "native_name",
            "is_rtl",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TranslationSerializer(serializers.ModelSerializer):
    """Serializer for Translation model."""

    language_code = serializers.CharField(source="language.code", read_only=True)
    language_name = serializers.CharField(source="language.name", read_only=True)

    class Meta:
        model = Translation
        fields = [
            "id",
            "tenant_id",
            "language",
            "language_code",
            "language_name",
            "key",
            "value",
            "context",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]

    def validate_key(self, value):
        """Validate key field."""
        if not value or not value.strip():
            raise serializers.ValidationError("Key cannot be empty")
        return value.strip()


class LocaleConfigSerializer(serializers.ModelSerializer):
    """Serializer for LocaleConfig model."""

    default_language_code = serializers.CharField(source="default_language.code", read_only=True)
    default_language_name = serializers.CharField(source="default_language.name", read_only=True)

    class Meta:
        model = LocaleConfig
        fields = [
            "id",
            "tenant_id",
            "default_language",
            "default_language_code",
            "default_language_name",
            "timezone",
            "date_format",
            "time_format",
            "number_format",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class CurrencyConfigSerializer(serializers.ModelSerializer):
    """Serializer for CurrencyConfig model."""

    class Meta:
        model = CurrencyConfig
        fields = [
            "id",
            "tenant_id",
            "default_currency",
            "exchange_rates",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class RegionalSettingsSerializer(serializers.ModelSerializer):
    """Serializer for RegionalSettings model."""

    class Meta:
        model = RegionalSettings
        fields = [
            "id",
            "tenant_id",
            "country_code",
            "tax_settings",
            "fiscal_year_start",
            "business_days",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]
