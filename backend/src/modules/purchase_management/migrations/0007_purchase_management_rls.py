from django.db import migrations

TABLES = ["purchase_suppliers", "purchase_requisitions", "purchase_requisition_lines", "purchase_rfqs", "purchase_rfq_lines", "purchase_rfq_invitations", "purchase_supplier_quotes", "purchase_supplier_quote_lines", "purchase_orders", "purchase_order_lines", "purchase_receipts", "purchase_receipt_lines", "purchase_configurations"]

def enable(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql": return
    q = schema_editor.quote_name
    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            policy = f"{table}_tenant_policy"
            cursor.execute(f"ALTER TABLE {q(table)} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {q(table)} FORCE ROW LEVEL SECURITY")
            cursor.execute(f"CREATE POLICY {q(policy)} ON {q(table)} USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)")

def disable(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql": return
    q = schema_editor.quote_name
    with schema_editor.connection.cursor() as cursor:
        for table in reversed(TABLES):
            cursor.execute(f"DROP POLICY IF EXISTS {q(table + '_tenant_policy')} ON {q(table)}")
            cursor.execute(f"ALTER TABLE {q(table)} NO FORCE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {q(table)} DISABLE ROW LEVEL SECURITY")

class Migration(migrations.Migration):
    dependencies = [("purchase_management", "0006_cross_tenant_constraints")]
    operations = [migrations.RunSQL("SELECT 1", reverse_sql="SELECT 1"), migrations.RunPython(enable, disable)]

