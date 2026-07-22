"""Enable and force PostgreSQL row-level security on every tenant table."""
from django.db import migrations

TABLES = (
    "project_projects", "project_tasks", "project_members",
    "project_time_entries", "project_milestones",
    "project_management_configurations",
    "project_management_configuration_versions", "project_activities",
)


def install_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql": return
    for table in TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS);")


def remove_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql": return
    for table in reversed(TABLES):
        policy = f"tenant_isolation_{table}"
        schema_editor.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}";')
        schema_editor.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;')
        schema_editor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [("core", "0011_apply_typed_rls_to_notifications"), ("project_management", "0002_projectactivity_projectmanagementconfiguration_and_more")]
    operations = [migrations.RunPython(install_rls, remove_rls)]
