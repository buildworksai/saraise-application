"""Align localization tenant columns with the runtime UUID contract."""

from __future__ import annotations

import uuid

from django.db import migrations, models

TENANT_MODELS = (
    "CurrencyConfig",
    "LocaleConfig",
    "RegionalSettings",
    "Translation",
)


def validate_tenant_ids(apps, schema_editor) -> None:
    """Fail closed before converting any malformed tenant identifier."""
    del schema_editor
    for model_name in TENANT_MODELS:
        model = apps.get_model("localization", model_name)
        for tenant_id in model.objects.values_list("tenant_id", flat=True).iterator():
            try:
                uuid.UUID(str(tenant_id))
            except (AttributeError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"Cannot convert localization.{model_name} tenant_id "
                    f"{tenant_id!r} to UUID. Correct the source row before retrying."
                ) from exc


class Migration(migrations.Migration):
    dependencies = [
        ("localization", "0002_add_localization_models"),
    ]

    operations = [
        migrations.RunPython(validate_tenant_ids, migrations.RunPython.noop),
        migrations.RenameIndex(
            model_name="currencyconfig",
            new_name="localizatio_tenant__f6cddc_idx",
            old_name="localization_currency_tenant_id_idx",
        ),
        migrations.RenameIndex(
            model_name="language",
            new_name="localizatio_code_f22a7e_idx",
            old_name="localization_language_code__active_idx",
        ),
        migrations.RenameIndex(
            model_name="localeconfig",
            new_name="localizatio_tenant__6e6413_idx",
            old_name="localization_locale_tenant_id_idx",
        ),
        migrations.RenameIndex(
            model_name="regionalsettings",
            new_name="localizatio_tenant__d961a5_idx",
            old_name="localization_regional_tenant__country_idx",
        ),
        migrations.RenameIndex(
            model_name="translation",
            new_name="localizatio_tenant__8b191b_idx",
            old_name="localization_tenant__language__key_idx",
        ),
        migrations.RenameIndex(
            model_name="translation",
            new_name="localizatio_tenant__b41e1e_idx",
            old_name="localization_tenant__context_idx",
        ),
        migrations.AlterField(
            model_name="currencyconfig",
            name="tenant_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="localeconfig",
            name="tenant_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="regionalsettings",
            name="tenant_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="translation",
            name="tenant_id",
            field=models.UUIDField(db_index=True),
        ),
    ]
