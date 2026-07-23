"""Enable typed, fail-closed PostgreSQL RLS on every sales-owned table."""

from django.db import migrations

TENANT_TABLES = (
    "sales_customers",
    "sales_quotations",
    "sales_quotation_lines",
    "sales_orders",
    "sales_order_lines",
    "sales_delivery_notes",
    "sales_delivery_note_lines",
    "sales_configurations",
    "sales_configuration_versions",
    "sales_document_sequences",
)


def enable_sales_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS);")


def disable_sales_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(TENANT_TABLES):
        schema_editor.execute(f'DROP POLICY IF EXISTS "tenant_isolation_{table}" ON "{table}";')
        schema_editor.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;')
        schema_editor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("sales_management", "0004_enforce_sales_constraints"),
    ]
    operations = [migrations.RunPython(enable_sales_rls, disable_sales_rls)]
