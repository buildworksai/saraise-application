"""Install typed, forced PostgreSQL RLS on every reconciliation table."""

from django.db import migrations

TENANT_TABLES = (
    "bank_accounts",
    "bank_statement_imports",
    "bank_statements",
    "bank_transactions",
    "bank_matching_rules",
    "bank_reconciliation_sessions",
    "bank_reconciliation_matches",
    "bank_reconciliation_match_lines",
)


def enable_domain_rls(apps, schema_editor):
    """Apply the canonical typed helper, which verifies UUID ownership columns."""
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table_name}'::REGCLASS);")


def disable_domain_rls(apps, schema_editor):
    """Remove module policies and disable forced RLS without dropping any data."""
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
        ("bank_reconciliation", "0003_domain_constraints"),
        ("core", "0011_apply_typed_rls_to_notifications"),
    ]

    operations = [migrations.RunPython(enable_domain_rls, disable_domain_rls)]
