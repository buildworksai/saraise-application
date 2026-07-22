"""Install forced PostgreSQL row-level tenant isolation on workflow data."""

from django.db import migrations


TENANT_TABLES = (
    "workflow_definitions",
    "workflow_steps",
    "workflow_instances",
    "workflow_tasks",
    "workflow_step_executions",
)


def install_workflow_rls(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in TENANT_TABLES:
        policy_name = f"tenant_isolation_{table_name}"
        schema_editor.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name};")
        schema_editor.execute(
            f"CREATE POLICY {policy_name} ON {table_name} "
            "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);"
        )


def remove_workflow_rls(apps, schema_editor) -> None:
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
        ("workflow_automation", "0004_enforce_v2_constraints"),
        ("core", "0011_apply_typed_rls_to_notifications"),
    ]

    operations = [migrations.RunPython(install_workflow_rls, remove_workflow_rls)]
