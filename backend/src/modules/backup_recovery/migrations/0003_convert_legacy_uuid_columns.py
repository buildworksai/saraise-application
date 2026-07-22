"""Convert legacy text identifiers while retaining reversible text copies."""

from __future__ import annotations

import uuid

from django.db import migrations, models

MODELS = ("BackupJob", "BackupSchedule", "BackupRetentionPolicy", "BackupArchive")


def preserve_text_identifiers(apps, schema_editor):
    del schema_editor
    for model_name in MODELS:
        model = apps.get_model("backup_recovery", model_name)
        for row in model.objects.all().iterator(chunk_size=2_000):
            row.legacy_id_text = str(row.id)
            row.legacy_tenant_id_text = str(row.tenant_id)
            row.save(update_fields=("legacy_id_text", "legacy_tenant_id_text"))


def restore_text_identifiers(apps, schema_editor):
    del schema_editor
    for model_name in MODELS:
        model = apps.get_model("backup_recovery", model_name)
        for row in model.objects.exclude(legacy_id_text="").iterator(chunk_size=2_000):
            row.id = row.legacy_id_text
            row.tenant_id = row.legacy_tenant_id_text
            row.save(update_fields=("id", "tenant_id"))


def normalize_sqlite_uuid_storage(apps, schema_editor):
    """Match SQLite's compact UUID storage after textual column conversion."""

    if schema_editor.connection.vendor != "sqlite":
        return
    quote = schema_editor.connection.ops.quote_name
    for model_name in MODELS:
        table = quote(apps.get_model("backup_recovery", model_name)._meta.db_table)
        schema_editor.execute(
            f"UPDATE {table} SET {quote('id')} = REPLACE({quote('id')}, '-', ''), "
            f"{quote('tenant_id')} = REPLACE({quote('tenant_id')}, '-', '')"
        )
    archive_table = quote(apps.get_model("backup_recovery", "BackupArchive")._meta.db_table)
    schema_editor.execute(
        f"UPDATE {archive_table} SET {quote('backup_job_id')} = " f"REPLACE({quote('backup_job_id')}, '-', '')"
    )


def restore_sqlite_text_storage(apps, schema_editor):
    """Restore the preserved textual UUID representation before rollback."""

    if schema_editor.connection.vendor != "sqlite":
        return
    quote = schema_editor.connection.ops.quote_name
    Archive = apps.get_model("backup_recovery", "BackupArchive")
    archive_table = quote(Archive._meta.db_table)

    def uuid_text(column: str) -> str:
        compact = f"REPLACE({column}, '-', '')"
        return (
            f"CASE WHEN LENGTH({compact}) = 32 THEN "
            f"SUBSTR({compact}, 1, 8) || '-' || SUBSTR({compact}, 9, 4) || '-' || "
            f"SUBSTR({compact}, 13, 4) || '-' || SUBSTR({compact}, 17, 4) || '-' || "
            f"SUBSTR({compact}, 21, 12) ELSE {column} END"
        )

    archive_job_id = quote("backup_job_id")
    schema_editor.execute(f"UPDATE {archive_table} SET {archive_job_id} = {uuid_text(archive_job_id)}")
    for model_name in MODELS:
        table = quote(apps.get_model("backup_recovery", model_name)._meta.db_table)
        row_id = quote("id")
        tenant_id = quote("tenant_id")
        legacy_id = quote("legacy_id_text")
        legacy_tenant_id = quote("legacy_tenant_id_text")
        schema_editor.execute(
            f"UPDATE {table} SET {row_id} = CASE WHEN {legacy_id} <> '' "
            f"THEN {legacy_id} ELSE {uuid_text(row_id)} END, "
            f"{tenant_id} = CASE WHEN {legacy_tenant_id} <> '' "
            f"THEN {legacy_tenant_id} ELSE {uuid_text(tenant_id)} END"
        )


def legacy_fields(model_name: str) -> list[migrations.operations.base.Operation]:
    return [
        migrations.AddField(
            model_name=model_name,
            name="legacy_id_text",
            field=models.CharField(max_length=36, blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name=model_name,
            name="legacy_tenant_id_text",
            field=models.CharField(max_length=36, blank=True, default=""),
            preserve_default=False,
        ),
    ]


operations: list[migrations.operations.base.Operation] = []
for _model in ("backupjob", "backupschedule", "backupretentionpolicy", "backuparchive"):
    operations.extend(legacy_fields(_model))
operations.append(migrations.RunPython(preserve_text_identifiers, restore_text_identifiers))
# This reverse-only operation runs after UUIDField columns have been reverted to
# text columns. Restoring hyphenated values while the fields are still UUIDField
# makes SQLite's table-copy conversion turn them into empty identifiers.
operations.append(migrations.RunPython(migrations.RunPython.noop, restore_sqlite_text_storage))
for _model in ("backupjob", "backupschedule", "backupretentionpolicy", "backuparchive"):
    operations.extend(
        [
            migrations.AlterField(
                model_name=_model,
                name="id",
                field=models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False),
            ),
            migrations.AlterField(
                model_name=_model,
                name="tenant_id",
                field=models.UUIDField(db_index=True),
            ),
        ]
    )
operations.append(migrations.RunPython(normalize_sqlite_uuid_storage, migrations.RunPython.noop))


class Migration(migrations.Migration):
    dependencies = [("backup_recovery", "0002_validate_legacy_uuid_values")]
    operations = operations
