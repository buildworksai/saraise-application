"""Enable and FORCE canonical UUID tenant RLS on every inventory table."""

from django.db import migrations

TENANT_TABLES = (
    "inventory_warehouses",
    "inventory_storage_locations",
    "inventory_items",
    "inventory_batches",
    "inventory_serial_numbers",
    "inventory_stock_entries",
    "inventory_stock_entry_lines",
    "inventory_stock_ledger_entries",
    "inventory_stock_cost_layers",
    "inventory_stock_balances",
    "inventory_stock_reservations",
    "inventory_cycle_counts",
    "inventory_cycle_count_lines",
    "inventory_configurations",
    "inventory_configuration_revisions",
)


def enable_inventory_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS)")


def disable_inventory_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(TENANT_TABLES):
        schema_editor.execute(f'DROP POLICY IF EXISTS "tenant_isolation_{table}" ON "{table}"')
        schema_editor.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("inventory_management", "0004_constraints_and_indexes"),
    ]
    operations = [migrations.RunPython(enable_inventory_rls, disable_inventory_rls)]
