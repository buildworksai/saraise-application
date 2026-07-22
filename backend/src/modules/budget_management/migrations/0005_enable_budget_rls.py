"""Enable canonical forced PostgreSQL RLS for every budget-domain table."""

from django.db import migrations


TENANT_TABLES = (
    "budget_budgets",
    "budget_lines",
    "budget_approvals",
    "budget_approval_decisions",
    "budget_transitions",
    "budget_variance_alerts",
    "budget_commitments",
)


def enable_budget_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS);")


def disable_budget_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(TENANT_TABLES):
        quoted_table = schema_editor.quote_name(table)
        quoted_policy = schema_editor.quote_name(f"tenant_isolation_{table}"[:63])
        schema_editor.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table};")
        schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("budget_management", "0004_enforce_budget_constraints"),
    ]

    operations = [migrations.RunPython(enable_budget_rls, disable_budget_rls)]
