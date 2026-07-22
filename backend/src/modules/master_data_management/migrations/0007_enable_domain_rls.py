"""Enable typed, forced PostgreSQL RLS on every MDM tenant table."""

from django.db import migrations


TENANT_TABLES = (
    "mdm_entity_types",
    "mdm_entities",
    "mdm_entity_versions",
    "mdm_quality_rules",
    "mdm_quality_issues",
    "mdm_matching_rules",
    "mdm_merge_history",
    "mdm_match_candidates",
    "mdm_merge_participants",
)


def enable_domain_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table_name}'::REGCLASS);")


def disable_domain_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    quote = schema_editor.quote_name
    for table_name in reversed(TENANT_TABLES):
        table = quote(table_name)
        policy = quote(f"tenant_isolation_{table_name}")
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("master_data_management", "0006_add_concurrent_indexes"),
    ]

    operations = [migrations.RunPython(enable_domain_rls, disable_domain_rls)]
