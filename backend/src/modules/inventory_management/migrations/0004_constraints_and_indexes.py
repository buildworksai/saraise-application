"""Finalize normalized constraints and PostgreSQL tenant relation guards."""

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import F, Q


RELATIONS = (
    ("inventory_storage_locations", "warehouse_id", "inventory_warehouses"),
    ("inventory_storage_locations", "parent_id", "inventory_storage_locations"),
    ("inventory_items", "default_warehouse_id", "inventory_warehouses"),
    ("inventory_batches", "item_id", "inventory_items"),
    ("inventory_serial_numbers", "item_id", "inventory_items"),
    ("inventory_serial_numbers", "current_warehouse_id", "inventory_warehouses"),
    ("inventory_serial_numbers", "current_location_id", "inventory_storage_locations"),
    ("inventory_stock_entries", "source_warehouse_id", "inventory_warehouses"),
    ("inventory_stock_entries", "destination_warehouse_id", "inventory_warehouses"),
    ("inventory_stock_entries", "warehouse_id", "inventory_warehouses"),
    ("inventory_stock_entries", "reversal_of_id", "inventory_stock_entries"),
    ("inventory_stock_entry_lines", "stock_entry_id", "inventory_stock_entries"),
    ("inventory_stock_entry_lines", "item_id", "inventory_items"),
    ("inventory_stock_entry_lines", "source_location_id", "inventory_storage_locations"),
    ("inventory_stock_entry_lines", "destination_location_id", "inventory_storage_locations"),
    ("inventory_stock_entry_lines", "batch_id", "inventory_batches"),
    ("inventory_stock_entry_lines", "serial_number_id", "inventory_serial_numbers"),
    ("inventory_stock_ledger_entries", "stock_entry_id", "inventory_stock_entries"),
    ("inventory_stock_ledger_entries", "stock_entry_line_id", "inventory_stock_entry_lines"),
    ("inventory_stock_ledger_entries", "item_id", "inventory_items"),
    ("inventory_stock_ledger_entries", "warehouse_id", "inventory_warehouses"),
    ("inventory_stock_ledger_entries", "location_id", "inventory_storage_locations"),
    ("inventory_stock_ledger_entries", "batch_id", "inventory_batches"),
    ("inventory_stock_ledger_entries", "serial_number_id", "inventory_serial_numbers"),
    ("inventory_stock_cost_layers", "item_id", "inventory_items"),
    ("inventory_stock_cost_layers", "warehouse_id", "inventory_warehouses"),
    ("inventory_stock_cost_layers", "location_id", "inventory_storage_locations"),
    ("inventory_stock_cost_layers", "batch_id", "inventory_batches"),
    ("inventory_stock_cost_layers", "originating_ledger_entry_id", "inventory_stock_ledger_entries"),
    ("inventory_stock_balances", "item_id", "inventory_items"),
    ("inventory_stock_balances", "warehouse_id", "inventory_warehouses"),
    ("inventory_stock_balances", "location_id", "inventory_storage_locations"),
    ("inventory_stock_balances", "batch_id", "inventory_batches"),
    ("inventory_stock_balances", "serial_number_id", "inventory_serial_numbers"),
    ("inventory_stock_balances", "last_ledger_entry_id", "inventory_stock_ledger_entries"),
    ("inventory_stock_reservations", "item_id", "inventory_items"),
    ("inventory_stock_reservations", "warehouse_id", "inventory_warehouses"),
    ("inventory_stock_reservations", "location_id", "inventory_storage_locations"),
    ("inventory_stock_reservations", "batch_id", "inventory_batches"),
    ("inventory_stock_reservations", "serial_number_id", "inventory_serial_numbers"),
    ("inventory_cycle_counts", "warehouse_id", "inventory_warehouses"),
    ("inventory_cycle_counts", "location_id", "inventory_storage_locations"),
    ("inventory_cycle_count_lines", "cycle_count_id", "inventory_cycle_counts"),
    ("inventory_cycle_count_lines", "item_id", "inventory_items"),
    ("inventory_cycle_count_lines", "location_id", "inventory_storage_locations"),
    ("inventory_cycle_count_lines", "batch_id", "inventory_batches"),
    ("inventory_cycle_count_lines", "serial_number_id", "inventory_serial_numbers"),
    ("inventory_configuration_revisions", "configuration_id", "inventory_configurations"),
)


def _constraint_name(index, table, column):
    return f"inv_tenant_fk_{index}_{table.removeprefix('inventory_')[:18]}_{column[:12]}"


def add_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for index, (table, column, parent) in enumerate(RELATIONS, start=1):
        name = _constraint_name(index, table, column)
        schema_editor.execute(
            f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" '
            f'FOREIGN KEY ("tenant_id", "{column}") REFERENCES "{parent}" ("tenant_id", "id") '
            "DEFERRABLE INITIALLY IMMEDIATE"
        )
    schema_editor.execute(
        """
        CREATE OR REPLACE FUNCTION inventory_reject_evidence_mutation()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'inventory evidence in % is append-only', TG_TABLE_NAME;
        END;
        $$;
        CREATE TRIGGER inventory_ledger_immutable
          BEFORE UPDATE OR DELETE ON inventory_stock_ledger_entries
          FOR EACH ROW EXECUTE FUNCTION inventory_reject_evidence_mutation();
        CREATE TRIGGER inventory_config_revision_immutable
          BEFORE UPDATE OR DELETE ON inventory_configuration_revisions
          FOR EACH ROW EXECUTE FUNCTION inventory_reject_evidence_mutation();
        """
    )


def remove_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS inventory_ledger_immutable ON inventory_stock_ledger_entries")
    schema_editor.execute("DROP TRIGGER IF EXISTS inventory_config_revision_immutable ON inventory_configuration_revisions")
    schema_editor.execute("DROP FUNCTION IF EXISTS inventory_reject_evidence_mutation()")
    for index, (table, column, _parent) in reversed(tuple(enumerate(RELATIONS, start=1))):
        name = _constraint_name(index, table, column)
        schema_editor.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{name}"')


class Migration(migrations.Migration):
    dependencies = [("inventory_management", "0003_legacy_backfill")]
    operations = [
        migrations.AlterField(
            model_name="warehouse", name="country_code", field=models.CharField(max_length=2)
        ),
        migrations.AlterField(
            model_name="warehouse", name="timezone", field=models.CharField(max_length=64)
        ),
        migrations.AlterField(model_name="item", name="base_uom", field=models.CharField(max_length=32)),
        migrations.AlterField(model_name="stockentry", name="posting_at", field=models.DateTimeField()),
        migrations.AlterField(
            model_name="stockentry", name="idempotency_key", field=models.CharField(max_length=255)
        ),
        migrations.AlterField(
            model_name="stockentryline", name="line_number", field=models.PositiveIntegerField()
        ),
        migrations.AlterField(model_name="stockentryline", name="uom", field=models.CharField(max_length=32)),
        migrations.AlterField(
            model_name="stockbalance",
            name="location",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="stock_balances",
                to="inventory_management.storagelocation",
            ),
        ),
        migrations.AddConstraint(
            model_name="stockentry",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"), name="inv_entry_idempotency_uq"
            ),
        ),
        migrations.AddConstraint(
            model_name="stockentry",
            constraint=models.CheckConstraint(
                condition=~Q(entry_type="transfer")
                | (
                    Q(source_warehouse__isnull=False)
                    & Q(destination_warehouse__isnull=False)
                    & ~Q(source_warehouse=F("destination_warehouse"))
                ),
                name="inv_entry_transfer_wh_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="stockentry",
            constraint=models.CheckConstraint(
                condition=~Q(entry_type__in=("receipt", "return")) | Q(destination_warehouse__isnull=False),
                name="inv_entry_destination_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="stockentry",
            constraint=models.CheckConstraint(
                condition=~Q(entry_type__in=("issue", "scrap")) | Q(source_warehouse__isnull=False),
                name="inv_entry_source_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="stockentry",
            constraint=models.CheckConstraint(
                condition=~Q(status="posted") | (Q(posted_by_id__isnull=False) & Q(posted_at__isnull=False)),
                name="inv_entry_posted_audit_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="stockentryline",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "stock_entry", "line_number"), name="inv_line_number_uq"
            ),
        ),
        migrations.AddConstraint(
            model_name="stockentryline",
            constraint=models.CheckConstraint(condition=Q(quantity__gt=0), name="inv_line_quantity_ck"),
        ),
        migrations.RunPython(add_postgres_guards, remove_postgres_guards),
    ]
