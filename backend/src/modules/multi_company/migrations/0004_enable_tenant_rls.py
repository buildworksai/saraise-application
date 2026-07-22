"""Enable and force canonical typed PostgreSQL RLS for every domain table."""

from django.db import migrations


TENANT_TABLES = (
    "multi_company_companies",
    "multi_company_access_grants",
    "multi_company_transfer_pricing_rules",
    "multi_company_transactions",
    "multi_company_approvals",
    "multi_company_consolidation_runs",
    "multi_company_eliminations",
    "multi_company_configuration_versions",
    "multi_company_configuration_audit",
)


def enable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS);")


def disable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(TENANT_TABLES):
        schema_editor.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("multi_company", "0003_backfill_company_contract"),
        ("core", "0011_apply_typed_rls_to_notifications"),
    ]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
