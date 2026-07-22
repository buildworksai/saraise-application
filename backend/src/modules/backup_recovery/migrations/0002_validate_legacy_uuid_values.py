"""Fail closed before converting legacy textual identifiers to UUID columns."""

from __future__ import annotations

import uuid

from django.db import migrations

MODELS = ("BackupJob", "BackupSchedule", "BackupRetentionPolicy", "BackupArchive")


def validate_uuid_values(apps, schema_editor):
    del schema_editor
    invalid: list[str] = []
    for model_name in MODELS:
        model = apps.get_model("backup_recovery", model_name)
        for row_id, tenant_id in model.objects.values_list("id", "tenant_id").iterator(chunk_size=2_000):
            for field, value in (("id", row_id), ("tenant_id", tenant_id)):
                try:
                    uuid.UUID(str(value))
                except (TypeError, ValueError, AttributeError):
                    # Row identifiers are truncated/sanitized; no tenant data is logged.
                    invalid.append(f"{model_name}:{str(row_id)[:12]}:{field}")
                    if len(invalid) >= 20:
                        break
            if len(invalid) >= 20:
                break
    if invalid:
        raise RuntimeError("Invalid legacy UUID values: " + ", ".join(invalid))


class Migration(migrations.Migration):
    dependencies = [("backup_recovery", "0001_initial")]
    operations = [migrations.RunPython(validate_uuid_values, validate_uuid_values)]
