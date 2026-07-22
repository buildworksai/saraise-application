"""Atomically promote validated v2 tables while retaining legacy evidence."""

from django.db import migrations

TABLES = (
    ("dms_folders", "dms_folders_v2", "dms_folders_legacy"),
    ("dms_documents", "dms_documents_v2", "dms_documents_legacy"),
    ("dms_document_versions", "dms_document_versions_v2", "dms_document_versions_legacy"),
    ("dms_document_permissions", "dms_document_permissions_v2", "dms_document_permissions_legacy"),
    ("dms_document_shares", "dms_document_shares_v2", "dms_document_shares_legacy"),
)


def swap_tables(apps, schema_editor) -> None:
    del apps
    for canonical, _shadow, legacy in TABLES:
        schema_editor.execute(
            f"ALTER TABLE {schema_editor.quote_name(canonical)} " f"RENAME TO {schema_editor.quote_name(legacy)}"
        )
    for canonical, shadow, _legacy in TABLES:
        schema_editor.execute(
            f"ALTER TABLE {schema_editor.quote_name(shadow)} " f"RENAME TO {schema_editor.quote_name(canonical)}"
        )


def restore_tables(apps, schema_editor) -> None:
    del apps
    for canonical, shadow, _legacy in reversed(TABLES):
        schema_editor.execute(
            f"ALTER TABLE {schema_editor.quote_name(canonical)} " f"RENAME TO {schema_editor.quote_name(shadow)}"
        )
    for canonical, _shadow, legacy in reversed(TABLES):
        schema_editor.execute(
            f"ALTER TABLE {schema_editor.quote_name(legacy)} " f"RENAME TO {schema_editor.quote_name(canonical)}"
        )


class Migration(migrations.Migration):
    dependencies = [("dms", "0004_validate_and_copy_legacy_data")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(swap_tables, restore_tables)],
            state_operations=[
                migrations.DeleteModel(name="DocumentShare"),
                migrations.DeleteModel(name="DocumentPermission"),
                migrations.DeleteModel(name="DocumentVersion"),
                migrations.DeleteModel(name="Document"),
                migrations.DeleteModel(name="Folder"),
                migrations.RenameModel(old_name="FolderV2", new_name="Folder"),
                migrations.RenameModel(old_name="DocumentV2", new_name="Document"),
                migrations.RenameModel(old_name="DocumentVersionV2", new_name="DocumentVersion"),
                migrations.RenameModel(old_name="DocumentPermissionV2", new_name="DocumentPermission"),
                migrations.RenameModel(old_name="DocumentShareV2", new_name="DocumentShare"),
                migrations.AlterModelTable(name="folder", table="dms_folders"),
                migrations.AlterModelTable(name="document", table="dms_documents"),
                migrations.AlterModelTable(name="documentversion", table="dms_document_versions"),
                migrations.AlterModelTable(name="documentpermission", table="dms_document_permissions"),
                migrations.AlterModelTable(name="documentshare", table="dms_document_shares"),
            ],
        )
    ]
