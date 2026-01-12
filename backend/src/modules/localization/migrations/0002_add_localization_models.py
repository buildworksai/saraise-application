# Generated migration for Localization models

import src.modules.localization.models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("localization", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Language",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=src.modules.localization.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("code", models.CharField(db_index=True, help_text="ISO 639-1 language code (e.g., 'en', 'fr', 'es')", max_length=10, unique=True)),
                ("name", models.CharField(help_text="English name", max_length=100)),
                ("native_name", models.CharField(help_text="Native name", max_length=100)),
                ("is_rtl", models.BooleanField(default=False, help_text="Right-to-left language")),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "localization_languages",
                "indexes": [
                    models.Index(fields=["code", "is_active"], name="localization_language_code__active_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Translation",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.localization.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("key", models.CharField(db_index=True, help_text="Translation key (e.g., 'common.save', 'errors.not_found')", max_length=500)),
                ("value", models.TextField(help_text="Translated text")),
                ("context", models.CharField(blank=True, help_text="Context (e.g., 'module', 'page', 'component')", max_length=100)),
                (
                    "language",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="translations",
                        to="localization.language",
                    ),
                ),
            ],
            options={
                "db_table": "localization_translations",
                "indexes": [
                    models.Index(fields=["tenant_id", "language", "key"], name="localization_tenant__language__key_idx"),
                    models.Index(fields=["tenant_id", "context"], name="localization_tenant__context_idx"),
                ],
                "unique_together": {("tenant_id", "language", "key", "context")},
            },
        ),
        migrations.CreateModel(
            name="LocaleConfig",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.localization.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("timezone", models.CharField(default="UTC", help_text="IANA timezone (e.g., 'America/New_York')", max_length=100)),
                ("date_format", models.CharField(default="YYYY-MM-DD", help_text="Date format pattern", max_length=50)),
                ("time_format", models.CharField(default="HH:mm:ss", help_text="Time format pattern", max_length=50)),
                ("number_format", models.CharField(default="en-US", help_text="Number format locale (e.g., 'en-US', 'de-DE')", max_length=50)),
                (
                    "default_language",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="locale_configs",
                        to="localization.language",
                    ),
                ),
            ],
            options={
                "db_table": "localization_locale_configs",
                "indexes": [
                    models.Index(fields=["tenant_id"], name="localization_locale_tenant_id_idx"),
                ],
                "unique_together": {("tenant_id",)},
            },
        ),
        migrations.CreateModel(
            name="CurrencyConfig",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.localization.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("default_currency", models.CharField(default="USD", help_text="ISO 4217 currency code", max_length=3)),
                ("exchange_rates", models.JSONField(default=dict, help_text="Exchange rates relative to default currency")),
            ],
            options={
                "db_table": "localization_currency_configs",
                "indexes": [
                    models.Index(fields=["tenant_id"], name="localization_currency_tenant_id_idx"),
                ],
                "unique_together": {("tenant_id",)},
            },
        ),
        migrations.CreateModel(
            name="RegionalSettings",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.localization.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("country_code", models.CharField(help_text="ISO 3166-1 alpha-2 country code", max_length=2)),
                ("tax_settings", models.JSONField(default=dict, help_text="Tax configuration (rates, rules, etc.)")),
                ("fiscal_year_start", models.DateField(blank=True, help_text="Fiscal year start date", null=True)),
                ("business_days", models.JSONField(default=list, help_text="List of business days (0=Monday, 6=Sunday)")),
            ],
            options={
                "db_table": "localization_regional_settings",
                "indexes": [
                    models.Index(fields=["tenant_id", "country_code"], name="localization_regional_tenant__country_idx"),
                ],
            },
        ),
    ]
