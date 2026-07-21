"""Install typed, forced PostgreSQL tenant RLS on orchestration tables."""

from django.db import migrations


TENANT_TABLES = (
    "automation_orchestration_definitions",
    "automation_orchestration_nodes",
    "automation_orchestration_edges",
    "automation_orchestration_schedules",
    "automation_orchestration_runs",
    "automation_orchestration_task_runs",
    "automation_orchestration_retry_attempts",
    "automation_orchestration_events",
)


def enable_orchestration_rls(apps, schema_editor) -> None:
    """Use the canonical REGCLASS helper, which verifies UUID tenant columns."""
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table_name}'::REGCLASS);")


def disable_orchestration_rls(apps, schema_editor) -> None:
    """Drop module policies and fully disable forced RLS in reverse order."""
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in reversed(TENANT_TABLES):
        policy_name = f"tenant_isolation_{table_name}"
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name};")
        schema_editor.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("automation_orchestration", "0002_create_orchestration_domain"),
        ("core", "0011_apply_typed_rls_to_notifications"),
    ]

    operations = [migrations.RunPython(enable_orchestration_rls, disable_orchestration_rls)]

