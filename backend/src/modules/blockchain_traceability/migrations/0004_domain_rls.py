"""Enable typed PostgreSQL RLS on every traceability domain table."""

from django.db import migrations

DOMAIN_TABLES = (
    "blockchain_traceability_ledger_networks",
    "blockchain_traceability_assets",
    "blockchain_traceability_events",
    "blockchain_traceability_ledger_anchors",
    "blockchain_traceability_authenticity_credentials",
    "blockchain_traceability_compliance_evidence",
    "blockchain_traceability_verification_attempts",
)


def enable_domain_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in DOMAIN_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS);")


def disable_domain_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(DOMAIN_TABLES):
        quoted_table = schema_editor.quote_name(table)
        policy = schema_editor.quote_name(f"tenant_isolation_{table}"[:63])
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {quoted_table};")
        schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("blockchain_traceability", "0003_domain_schema"),
    ]

    operations = [migrations.RunPython(enable_domain_rls, disable_domain_rls)]
