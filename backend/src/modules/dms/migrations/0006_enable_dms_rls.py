"""Enable and force typed PostgreSQL tenant RLS on canonical DMS tables."""

from django.db import migrations

TENANT_TABLES = (
    "dms_folders",
    "dms_documents",
    "dms_document_versions",
    "dms_document_permissions",
    "dms_document_shares",
)


def enable_dms_rls(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table_name}'::REGCLASS);")


def disable_dms_rls(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in reversed(TENANT_TABLES):
        quoted_table = schema_editor.quote_name(table_name)
        quoted_policy = schema_editor.quote_name(f"tenant_isolation_{table_name}")
        schema_editor.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table};")
        schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("dms", "0005_swap_v2_tables"),
    ]

    operations = [migrations.RunPython(enable_dms_rls, disable_dms_rls)]
