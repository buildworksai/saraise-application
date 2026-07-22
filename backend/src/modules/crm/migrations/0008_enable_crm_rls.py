"""Enable typed, fail-closed PostgreSQL RLS on every CRM table."""

from django.db import migrations


TABLES = ("crm_leads", "crm_accounts", "crm_contacts", "crm_opportunities", "crm_activities")


def enable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS)")


def disable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(TABLES):
        schema_editor.execute(
            f'DROP POLICY IF EXISTS "tenant_isolation_{table}" ON "{table}";'
            f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;'
            f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;'
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0011_apply_typed_rls_to_notifications"), ("crm", "0007_same_tenant_reference_guards")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
