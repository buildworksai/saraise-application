"""Enable and force typed PostgreSQL RLS on all catalog tables."""

from django.db import migrations

TABLES = (
    "backup_recovery_storage_targets",
    "backup_recovery_retention_policies",
    "backup_recovery_schedules",
    "backup_recovery_jobs",
    "backup_recovery_archives",
    "backup_recovery_verifications",
)


def enable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return  # SQLite has no row-level security; this is an intentional test no-op.
    for table in TABLES:
        schema_editor.execute("SELECT saraise_enable_rls(%s::regclass)", [table])


def disable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(TABLES):
        policy = f"tenant_isolation_{table}"
        quoted_table = schema_editor.quote_name(table)
        quoted_policy = schema_editor.quote_name(policy)
        schema_editor.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table}")
        schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [
        ("backup_recovery", "0006_enforce_catalog_constraints"),
        ("core", "0011_apply_typed_rls_to_notifications"),
    ]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
