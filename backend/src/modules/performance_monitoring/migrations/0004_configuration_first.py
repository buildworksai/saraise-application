"""Add tenant-owned, versioned, correlation-aware monitoring configuration."""

import uuid

import django.db.models.deletion
from django.db import migrations, models

CONFIGURATION_TABLES = (
    "performance_monitoring_configurations",
    "performance_monitoring_configuration_versions",
    "performance_monitoring_configuration_audit",
)


def enable_configuration_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in CONFIGURATION_TABLES:
        quoted_table = schema_editor.quote_name(table)
        policy = schema_editor.quote_name(f"pm_tenant_{table.removeprefix('performance_')}")
        schema_editor.execute(f"ALTER TABLE {quoted_table} ENABLE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {quoted_table} FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {quoted_table};")
        schema_editor.execute(
            f"CREATE POLICY {policy} ON {quoted_table} "
            "USING (tenant_id = saraise_current_tenant_id()) "
            "WITH CHECK (tenant_id = saraise_current_tenant_id());"
        )


def disable_configuration_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(CONFIGURATION_TABLES):
        quoted_table = schema_editor.quote_name(table)
        policy = schema_editor.quote_name(f"pm_tenant_{table.removeprefix('performance_')}")
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {quoted_table};")
        schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY;")


def protect_configuration_history(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "CREATE OR REPLACE FUNCTION performance_monitoring_reject_config_history_mutation() "
        "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
        "RAISE EXCEPTION 'performance monitoring configuration history is append-only'; END; $$;"
    )
    for table in CONFIGURATION_TABLES[1:]:
        quoted_table = schema_editor.quote_name(table)
        trigger = schema_editor.quote_name(
            f"pm_immutable_{table.removeprefix('performance_monitoring_configuration_')}"
        )
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {quoted_table};")
        schema_editor.execute(
            f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {quoted_table} "
            "FOR EACH ROW EXECUTE FUNCTION performance_monitoring_reject_config_history_mutation();"
        )


def unprotect_configuration_history(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(CONFIGURATION_TABLES[1:]):
        quoted_table = schema_editor.quote_name(table)
        trigger = schema_editor.quote_name(
            f"pm_immutable_{table.removeprefix('performance_monitoring_configuration_')}"
        )
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {quoted_table};")
    schema_editor.execute("DROP FUNCTION IF EXISTS performance_monitoring_reject_config_history_mutation();")


class Migration(migrations.Migration):
    dependencies = [("performance_monitoring", "0003_domain_rls")]

    operations = [
        migrations.AddConstraint(
            model_name="telemetrysource",
            constraint=models.CheckConstraint(
                condition=models.Q(daily_event_quota__gte=1, daily_event_quota__lte=100_000_000),
                name="pm_source_daily_quota_safe",
            ),
        ),
        migrations.CreateModel(
            name="PerformanceMonitoringConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.SlugField(default="default", max_length=64)),
                ("document", models.JSONField()),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_by", models.UUIDField(db_index=True)),
                ("updated_by", models.UUIDField(db_index=True)),
                ("correlation_id", models.CharField(db_index=True, max_length=128)),
            ],
            options={
                "db_table": "performance_monitoring_configurations",
                "indexes": [
                    models.Index(fields=["tenant_id", "environment", "version"], name="pm_cfg_tenant_env_ver_idx")
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "environment"), name="pm_config_tenant_env_uq"),
                    models.CheckConstraint(condition=models.Q(version__gte=1), name="pm_config_version_positive"),
                    models.CheckConstraint(
                        condition=~models.Q(correlation_id=""), name="pm_config_correlation_present"
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PerformanceMonitoringConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("actor_id", models.UUIDField(db_index=True)),
                ("correlation_id", models.CharField(db_index=True, max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("environment", models.SlugField(max_length=64)),
                ("version", models.PositiveIntegerField()),
                ("document", models.JSONField()),
                ("change_reason", models.CharField(max_length=240)),
                (
                    "configuration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="versions",
                        to="performance_monitoring.performancemonitoringconfiguration",
                    ),
                ),
            ],
            options={
                "db_table": "performance_monitoring_configuration_versions",
                "base_manager_name": "objects",
                "default_manager_name": "objects",
                "indexes": [
                    models.Index(fields=["tenant_id", "environment", "-version"], name="pm_cfg_tenant_version_idx")
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("configuration", "version"), name="pm_config_version_uq"),
                    models.CheckConstraint(
                        condition=models.Q(version__gte=1), name="pm_config_snapshot_version_positive"
                    ),
                    models.CheckConstraint(
                        condition=~models.Q(correlation_id=""), name="pm_config_version_correlation_present"
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PerformanceMonitoringConfigurationAudit",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("actor_id", models.UUIDField(db_index=True)),
                ("correlation_id", models.CharField(db_index=True, max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("environment", models.SlugField(max_length=64)),
                ("action", models.CharField(max_length=24)),
                ("from_version", models.PositiveIntegerField(blank=True, null=True)),
                ("to_version", models.PositiveIntegerField()),
                ("before", models.JSONField(blank=True, null=True)),
                ("after", models.JSONField()),
                ("change_reason", models.CharField(max_length=240)),
                (
                    "configuration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="audit_records",
                        to="performance_monitoring.performancemonitoringconfiguration",
                    ),
                ),
            ],
            options={
                "db_table": "performance_monitoring_configuration_audit",
                "base_manager_name": "objects",
                "default_manager_name": "objects",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "environment", "-created_at"], name="pm_cfg_audit_tenant_time_idx"
                    ),
                    models.Index(fields=["tenant_id", "correlation_id"], name="pm_cfg_audit_corr_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(to_version__gte=1), name="pm_config_audit_version_positive"
                    ),
                    models.CheckConstraint(
                        condition=~models.Q(correlation_id=""), name="pm_config_audit_correlation_present"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(action__in=("create", "update", "import", "rollback")),
                        name="pm_config_audit_action_allowed",
                    ),
                ],
            },
        ),
        migrations.RunPython(enable_configuration_rls, disable_configuration_rls),
        migrations.RunPython(protect_configuration_history, unprotect_configuration_history),
    ]
