"""Enforce tenant-qualified relationships at the PostgreSQL boundary."""
from django.db import migrations

CONSTRAINTS = (
    ("project_tasks", "pm_task_project_tenant_fk", "project_id", "project_projects"),
    ("project_tasks", "pm_task_parent_tenant_fk", "parent_task_id", "project_tasks"),
    ("project_members", "pm_member_project_tenant_fk", "project_id", "project_projects"),
    ("project_time_entries", "pm_time_project_tenant_fk", "project_id", "project_projects"),
    ("project_time_entries", "pm_time_task_tenant_fk", "task_id", "project_tasks"),
    ("project_milestones", "pm_milestone_project_tenant_fk", "project_id", "project_projects"),
    ("project_management_configuration_versions", "pm_configver_config_tenant_fk", "configuration_id", "project_management_configurations"),
    ("project_management_configurations", "pm_config_active_tenant_fk", "active_version_id", "project_management_configuration_versions"),
)


def install_same_tenant_fks(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql": return
    for table, name, column, target in CONSTRAINTS:
        schema_editor.execute(
            f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" '
            f'FOREIGN KEY (tenant_id, "{column}") REFERENCES "{target}" (tenant_id, id) '
            'DEFERRABLE INITIALLY DEFERRED;'
        )


def remove_same_tenant_fks(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql": return
    for table, name, _column, _target in reversed(CONSTRAINTS):
        schema_editor.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{name}";')


class Migration(migrations.Migration):
    dependencies = [("project_management", "0004_projectmanagementconfiguration_pm_config_tenant_id_uniq_and_more")]
    operations = [migrations.RunPython(install_same_tenant_fks, remove_same_tenant_fks)]
