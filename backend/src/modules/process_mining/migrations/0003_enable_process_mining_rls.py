"""Enable typed PostgreSQL RLS on every process-mining domain table."""

from django.db import migrations

TABLES = (
    "process_mining_events", "process_mining_export_jobs", "process_mining_discovery_jobs",
    "process_mining_models", "process_mining_model_versions", "process_mining_conformance_checks",
    "process_mining_conformance_deviations", "process_mining_conformance_case_metrics",
    "process_mining_bottleneck_analyses", "process_mining_bottleneck_findings", "process_mining_variants",
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
    dependencies = [("core", "0011_apply_typed_rls_to_notifications"), ("process_mining", "0002_process_mining_domain")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
