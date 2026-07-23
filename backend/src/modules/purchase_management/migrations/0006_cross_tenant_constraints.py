from django.db import migrations

PARENTS = ["purchase_suppliers", "purchase_requisitions", "purchase_requisition_lines", "purchase_rfqs", "purchase_rfq_lines", "purchase_supplier_quotes", "purchase_supplier_quote_lines", "purchase_orders", "purchase_order_lines", "purchase_receipts"]
RELATIONS = [
    ("purchase_requisition_lines", "requisition_id", "purchase_requisitions"),
    ("purchase_rfqs", "requisition_id", "purchase_requisitions"),
    ("purchase_rfq_lines", "rfq_id", "purchase_rfqs"), ("purchase_rfq_lines", "requisition_line_id", "purchase_requisition_lines"),
    ("purchase_rfq_invitations", "rfq_id", "purchase_rfqs"), ("purchase_rfq_invitations", "supplier_id", "purchase_suppliers"),
    ("purchase_supplier_quotes", "rfq_id", "purchase_rfqs"), ("purchase_supplier_quotes", "supplier_id", "purchase_suppliers"),
    ("purchase_supplier_quote_lines", "quote_id", "purchase_supplier_quotes"), ("purchase_supplier_quote_lines", "rfq_line_id", "purchase_rfq_lines"),
    ("purchase_orders", "supplier_id", "purchase_suppliers"), ("purchase_orders", "requisition_id", "purchase_requisitions"), ("purchase_orders", "rfq_id", "purchase_rfqs"), ("purchase_orders", "accepted_quote_id", "purchase_supplier_quotes"),
    ("purchase_order_lines", "purchase_order_id", "purchase_orders"), ("purchase_order_lines", "requisition_line_id", "purchase_requisition_lines"), ("purchase_order_lines", "quote_line_id", "purchase_supplier_quote_lines"),
    ("purchase_receipts", "purchase_order_id", "purchase_orders"), ("purchase_receipt_lines", "purchase_receipt_id", "purchase_receipts"), ("purchase_receipt_lines", "purchase_order_line_id", "purchase_order_lines"),
]

def forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql": return
    q = schema_editor.quote_name
    with schema_editor.connection.cursor() as cursor:
        for table in PARENTS:
            cursor.execute(f"ALTER TABLE {q(table)} ADD CONSTRAINT {q(table[:18] + '_tenant_id_uq')} UNIQUE (tenant_id, id)")
        for index, (child, column, parent) in enumerate(RELATIONS):
            cursor.execute(f"ALTER TABLE {q(child)} ADD CONSTRAINT {q('purchase_tenant_fk_' + str(index))} FOREIGN KEY (tenant_id, {q(column)}) REFERENCES {q(parent)} (tenant_id, id) DEFERRABLE INITIALLY DEFERRED")

def reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql": return
    q = schema_editor.quote_name
    with schema_editor.connection.cursor() as cursor:
        for index, (child, _, _) in reversed(list(enumerate(RELATIONS))): cursor.execute(f"ALTER TABLE {q(child)} DROP CONSTRAINT IF EXISTS {q('purchase_tenant_fk_' + str(index))}")
        for table in reversed(PARENTS): cursor.execute(f"ALTER TABLE {q(table)} DROP CONSTRAINT IF EXISTS {q(table[:18] + '_tenant_id_uq')}")

class Migration(migrations.Migration):
    dependencies = [("purchase_management", "0005_procurement_configuration")]
    operations = [migrations.RunSQL("SELECT 1", reverse_sql="SELECT 1"), migrations.RunPython(forward, reverse)]

