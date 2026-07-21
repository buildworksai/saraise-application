"""Force typed PostgreSQL tenant RLS across monitoring domain tables."""

from django.db import migrations

TABLES = (
    "performance_telemetry_sources",
    "performance_environments",
    "performance_monitored_services",
    "performance_metrics",
    "performance_metric_data_points",
    "performance_log_entries",
    "performance_traces",
    "performance_spans",
    "performance_dashboards",
    "performance_alert_rules",
    "performance_alerts",
    "performance_alert_notification_outcomes",
    "performance_sla_definitions",
    "performance_slos",
    "performance_sla_compliance",
    "performance_sla_breaches",
    "performance_error_budget_snapshots",
    "performance_sla_reports",
    "performance_monitoring_extensions",
)


def enable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
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


def disable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(TABLES):
        quoted_table = schema_editor.quote_name(table)
        policy = schema_editor.quote_name(f"pm_tenant_{table.removeprefix('performance_')}")
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {quoted_table};")
        schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("performance_monitoring", "0002_domain_models"),
    ]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
