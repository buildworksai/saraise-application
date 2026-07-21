"""Enable and force typed tenant RLS on all disaster-recovery tables."""

from django.db import migrations


TENANT_TABLES = (
    "bdr_recovery_points",
    "bdr_runbooks",
    "bdr_runbook_steps",
    "bdr_exercises",
    "bdr_restore_runs",
    "bdr_step_executions",
)


def enable_rls(apps, schema_editor):
    """Apply the canonical typed RLS helper on PostgreSQL only."""

    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS);")


def disable_rls(apps, schema_editor):
    """Remove only this module's policies and RLS table settings."""

    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(TENANT_TABLES):
        # Names are static constants, not user-controlled identifiers.
        schema_editor.execute(
            f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("backup_disaster_recovery", "0002_domain_models"),
        ("core", "0011_apply_typed_rls_to_notifications"),
    ]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
