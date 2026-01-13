"""
Localization Models.

Defines data models for Localization module.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from django.db import models


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class TenantBaseModel(models.Model):
    """Base model for tenant-scoped models with Row-Level Multitenancy.

    CRITICAL: All tenant-scoped models MUST inherit from this base class
    and include tenant_id. All queries MUST filter explicitly by tenant_id.
    """

    tenant_id = models.CharField(max_length=36, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "localization"
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class Language(models.Model):
    """Language model (platform-level, no tenant_id)."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    code = models.CharField(
        max_length=10,
        unique=True,
        db_index=True,
        help_text="ISO 639-1 language code (e.g., 'en', 'fr', 'es')",
    )
    name = models.CharField(max_length=100, help_text="English name")
    native_name = models.CharField(max_length=100, help_text="Native name")
    is_rtl = models.BooleanField(
        default=False,
        help_text="Right-to-left language",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "localization"
        db_table = "localization_languages"
        indexes = [
            models.Index(fields=["code", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class Translation(TenantBaseModel):
    """Translation model for storing translated strings."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    language = models.ForeignKey(
        Language,
        on_delete=models.CASCADE,
        related_name="translations",
    )
    key = models.CharField(
        max_length=500,
        db_index=True,
        help_text="Translation key (e.g., 'common.save', 'errors.not_found')",
    )
    value = models.TextField(help_text="Translated text")
    context = models.CharField(
        max_length=100,
        blank=True,
        help_text="Context (e.g., 'module', 'page', 'component')",
    )

    class Meta:
        app_label = "localization"
        db_table = "localization_translations"
        indexes = [
            models.Index(fields=["tenant_id", "language", "key"]),
            models.Index(fields=["tenant_id", "context"]),
        ]
        unique_together = [["tenant_id", "language", "key", "context"]]

    def __str__(self) -> str:
        return f"{self.key} ({self.language.code}): {self.value[:50]}"


class LocaleConfig(TenantBaseModel):
    """Locale configuration model for tenant-specific locale settings."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    default_language = models.ForeignKey(
        Language,
        on_delete=models.PROTECT,
        related_name="locale_configs",
    )
    timezone = models.CharField(
        max_length=100,
        default="UTC",
        help_text="IANA timezone (e.g., 'America/New_York')",
    )
    date_format = models.CharField(
        max_length=50,
        default="YYYY-MM-DD",
        help_text="Date format pattern",
    )
    time_format = models.CharField(
        max_length=50,
        default="HH:mm:ss",
        help_text="Time format pattern",
    )
    number_format = models.CharField(
        max_length=50,
        default="en-US",
        help_text="Number format locale (e.g., 'en-US', 'de-DE')",
    )

    class Meta:
        app_label = "localization"
        db_table = "localization_locale_configs"
        indexes = [
            models.Index(fields=["tenant_id"]),
        ]
        unique_together = [["tenant_id"]]

    def __str__(self) -> str:
        return f"Locale config for tenant {self.tenant_id}"


class CurrencyConfig(TenantBaseModel):
    """Currency configuration model for tenant-specific currency settings."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    default_currency = models.CharField(
        max_length=3,
        default="USD",
        help_text="ISO 4217 currency code",
    )
    exchange_rates = models.JSONField(
        default=dict,
        help_text="Exchange rates relative to default currency",
    )

    class Meta:
        app_label = "localization"
        db_table = "localization_currency_configs"
        indexes = [
            models.Index(fields=["tenant_id"]),
        ]
        unique_together = [["tenant_id"]]

    def __str__(self) -> str:
        return f"Currency config for tenant {self.tenant_id}: {self.default_currency}"


class RegionalSettings(TenantBaseModel):
    """Regional settings model for tenant-specific regional configurations."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    country_code = models.CharField(
        max_length=2,
        help_text="ISO 3166-1 alpha-2 country code",
    )
    tax_settings = models.JSONField(
        default=dict,
        help_text="Tax configuration (rates, rules, etc.)",
    )
    fiscal_year_start = models.DateField(
        null=True,
        blank=True,
        help_text="Fiscal year start date",
    )
    business_days = models.JSONField(
        default=list,
        help_text="List of business days (0=Monday, 6=Sunday)",
    )

    class Meta:
        app_label = "localization"
        db_table = "localization_regional_settings"
        indexes = [
            models.Index(fields=["tenant_id", "country_code"]),
        ]

    def __str__(self) -> str:
        return f"Regional settings for tenant {self.tenant_id}: {self.country_code}"
