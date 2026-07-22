"""Apply database-enforced tenant isolation to configuration and new evidence."""

from django.db import migrations

TABLES = (
    "process_mining_configurations",
    "process_mining_configuration_versions",
    "process_mining_configuration_audits",
    "process_mining_model_reference_assignments",
    "process_mining_event_retention_tombstones",
    "process_mining_export_artifact_deletions",
)


def enable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS);")


def disable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(TABLES):
        schema_editor.execute(
            f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )


class Migration(migrations.Migration):
    dependencies = [("process_mining", "0004_process_mining_configuration")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
