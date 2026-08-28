"""Enforce monitoring evidence immutability in the database itself."""

from django.db import migrations

EVIDENCE_TABLES = (
    "performance_metric_data_points",
    "performance_log_entries",
    "performance_traces",
    "performance_spans",
    "performance_alert_notification_outcomes",
    "performance_sla_compliance",
    "performance_sla_breaches",
    "performance_error_budget_snapshots",
    "performance_sla_reports",
)


def protect_evidence(apps, schema_editor):
    del apps
    vendor = schema_editor.connection.vendor
    if vendor == "postgresql":
        schema_editor.execute("""
            CREATE OR REPLACE FUNCTION performance_monitoring_reject_evidence_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Monitoring evidence is append-only';
            END;
            $$ LANGUAGE plpgsql;
            """)
        for table in EVIDENCE_TABLES:
            trigger = f"pm_immutable_{table.removeprefix('performance_')}"
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "{trigger}" ON "{table}";')
            schema_editor.execute(
                f'CREATE TRIGGER "{trigger}" BEFORE UPDATE OR DELETE ON "{table}" '
                "FOR EACH ROW EXECUTE FUNCTION performance_monitoring_reject_evidence_mutation();"
            )


def unprotect_evidence(apps, schema_editor):
    del apps
    vendor = schema_editor.connection.vendor
    if vendor == "postgresql":
        for table in reversed(EVIDENCE_TABLES):
            trigger = f"pm_immutable_{table.removeprefix('performance_')}"
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "{trigger}" ON "{table}";')
        schema_editor.execute("DROP FUNCTION IF EXISTS performance_monitoring_reject_evidence_mutation();")


class Migration(migrations.Migration):
    dependencies = [("performance_monitoring", "0004_configuration_first")]

    operations = [migrations.RunPython(protect_evidence, unprotect_evidence)]
