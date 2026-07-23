"""Validate legacy data and install final relational tenant guards."""

from decimal import Decimal

from django.db import migrations, models


RELATION_CHECKS = (
    ("Quotation", "customer", "Customer"),
    ("Quotation", "revision_of", "Quotation"),
    ("QuotationLine", "quotation", "Quotation"),
    ("SalesOrder", "customer", "Customer"),
    ("SalesOrder", "quotation", "Quotation"),
    ("SalesOrderLine", "sales_order", "SalesOrder"),
    ("DeliveryNote", "sales_order", "SalesOrder"),
    ("DeliveryNoteLine", "delivery_note", "DeliveryNote"),
    ("DeliveryNoteLine", "sales_order_line", "SalesOrderLine"),
    ("SalesConfigurationVersion", "configuration", "SalesConfiguration"),
)

COMPOSITE_FOREIGN_KEYS = (
    ("sales_quotations", "customer_id", "sales_customers", "sales_quote_customer_tenant_fk"),
    ("sales_quotations", "revision_of_id", "sales_quotations", "sales_quote_revision_tenant_fk"),
    ("sales_quotation_lines", "quotation_id", "sales_quotations", "sales_ql_quote_tenant_fk"),
    ("sales_orders", "customer_id", "sales_customers", "sales_order_customer_tenant_fk"),
    ("sales_orders", "quotation_id", "sales_quotations", "sales_order_quote_tenant_fk"),
    ("sales_order_lines", "sales_order_id", "sales_orders", "sales_ol_order_tenant_fk"),
    ("sales_delivery_notes", "sales_order_id", "sales_orders", "sales_dn_order_tenant_fk"),
    ("sales_delivery_note_lines", "delivery_note_id", "sales_delivery_notes", "sales_dl_note_tenant_fk"),
    ("sales_delivery_note_lines", "sales_order_line_id", "sales_order_lines", "sales_dl_order_line_tenant_fk"),
    ("sales_configuration_versions", "configuration_id", "sales_configurations", "sales_cfg_hist_parent_tenant_fk"),
)


def validate_sales_data(apps, schema_editor):
    failures = []
    for child_name, field_name, parent_name in RELATION_CHECKS:
        child = apps.get_model("sales_management", child_name)
        parent = apps.get_model("sales_management", parent_name)
        field_id = f"{field_name}_id"
        parent_tenants = parent.objects.filter(id=models.OuterRef(field_id)).values("tenant_id")[:1]
        invalid = (
            child.objects.exclude(**{f"{field_id}__isnull": True})
            .annotate(parent_tenant=models.Subquery(parent_tenants))
            .exclude(parent_tenant=models.F("tenant_id"))
            .count()
        )
        if invalid:
            failures.append(f"{child_name}.{field_name}: {invalid} cross-tenant reference(s)")

    DeliveryNoteLine = apps.get_model("sales_management", "DeliveryNoteLine")
    mismatched_items = DeliveryNoteLine.objects.exclude(item_id=models.F("sales_order_line__item_id")).count()
    wrong_orders = DeliveryNoteLine.objects.exclude(
        delivery_note__sales_order_id=models.F("sales_order_line__sales_order_id")
    ).count()
    if mismatched_items:
        failures.append(f"DeliveryNoteLine.item_id: {mismatched_items} source-item mismatch(es)")
    if wrong_orders:
        failures.append(f"DeliveryNoteLine.sales_order_line: {wrong_orders} source-order mismatch(es)")

    Customer = apps.get_model("sales_management", "Customer")
    Quotation = apps.get_model("sales_management", "Quotation")
    SalesOrder = apps.get_model("sales_management", "SalesOrder")
    SalesOrderLine = apps.get_model("sales_management", "SalesOrderLine")
    DeliveryNote = apps.get_model("sales_management", "DeliveryNote")
    scalar_checks = (
        ("Customer.credit_limit", Customer.objects.filter(credit_limit__lt=0)),
        ("Quotation.valid_until", Quotation.objects.filter(valid_until__lt=models.F("quotation_date"))),
        ("Quotation.amounts", Quotation.objects.filter(models.Q(subtotal_amount__lt=0) | models.Q(discount_amount__lt=0) | models.Q(tax_amount__lt=0) | models.Q(total_amount__lt=0))),
        ("SalesOrder.delivery_date", SalesOrder.objects.filter(delivery_date__lt=models.F("order_date"))),
        ("SalesOrder.amounts", SalesOrder.objects.filter(models.Q(subtotal_amount__lt=0) | models.Q(discount_amount__lt=0) | models.Q(tax_amount__lt=0) | models.Q(total_amount__lt=0))),
        ("SalesOrderLine.quantity", SalesOrderLine.objects.filter(models.Q(quantity__lte=0) | models.Q(quantity__gt=Decimal("999999")))),
        ("SalesOrderLine.unit_price", SalesOrderLine.objects.filter(models.Q(unit_price__lt=0) | models.Q(unit_price__gt=Decimal("999999999.99")))),
        ("SalesOrderLine.delivered_quantity", SalesOrderLine.objects.filter(models.Q(delivered_quantity__lt=0) | models.Q(delivered_quantity__gt=models.F("quantity")))),
        ("DeliveryNote.tracking_number", DeliveryNote.objects.exclude(tracking_number="").filter(carrier_name="")),
        ("DeliveryNoteLine.quantity_delivered", DeliveryNoteLine.objects.filter(quantity_delivered__lte=0)),
    )
    for label, queryset in scalar_checks:
        invalid = queryset.count()
        if invalid:
            failures.append(f"{label}: {invalid} invalid legacy row(s)")

    duplicate_order_quotes = (
        SalesOrder.objects.filter(quotation_id__isnull=False, deleted_at__isnull=True)
        .values("tenant_id", "quotation_id")
        .annotate(row_count=models.Count("id"))
        .filter(row_count__gt=1)
        .count()
    )
    if duplicate_order_quotes:
        failures.append(f"SalesOrder.quotation: {duplicate_order_quotes} duplicate conversion group(s)")

    for model, field in ((Customer, "currency"), (Quotation, "currency"), (SalesOrder, "currency")):
        invalid = sum(
            1
            for value in model.objects.values_list(field, flat=True).iterator()
            if not isinstance(value, str) or len(value) != 3 or not value.isalpha() or value != value.upper()
        )
        if invalid:
            failures.append(f"{model.__name__}.{field}: {invalid} invalid ISO currency code(s)")
    if failures:
        raise RuntimeError("Cannot enforce sales constraints: " + "; ".join(failures))


def install_composite_tenant_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for child_table, child_column, parent_table, constraint_name in COMPOSITE_FOREIGN_KEYS:
        schema_editor.execute(
            f'ALTER TABLE "{child_table}" ADD CONSTRAINT "{constraint_name}" '
            f'FOREIGN KEY ("tenant_id", "{child_column}") '
            f'REFERENCES "{parent_table}" ("tenant_id", "id") DEFERRABLE INITIALLY IMMEDIATE'
        )


def remove_composite_tenant_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for child_table, _child_column, _parent_table, constraint_name in reversed(COMPOSITE_FOREIGN_KEYS):
        schema_editor.execute(f'ALTER TABLE "{child_table}" DROP CONSTRAINT IF EXISTS "{constraint_name}"')


class Migration(migrations.Migration):

    dependencies = [
        ('sales_management', '0003_backfill_sales_domain'),
    ]

    operations = [
        migrations.RunPython(validate_sales_data, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='salesconfiguration',
            name='environment',
            field=models.CharField(choices=[('development', 'development'), ('self-hosted', 'self-hosted'), ('saas', 'saas')], max_length=32),
        ),
        migrations.AlterField(
            model_name='salesdocumentsequence',
            name='environment',
            field=models.CharField(choices=[('development', 'development'), ('self-hosted', 'self-hosted'), ('saas', 'saas')], max_length=32),
        ),
        migrations.AddConstraint(
            model_name='customer',
            constraint=models.UniqueConstraint(fields=('tenant_id', 'id'), name='sales_customer_tenant_id_uq'),
        ),
        migrations.AddConstraint(
            model_name='customer',
            constraint=models.CheckConstraint(condition=models.Q(('currency__regex', '^[A-Z]{3}$')), name='sales_customer_currency_ck'),
        ),
        migrations.AddConstraint(
            model_name='deliverynote',
            constraint=models.UniqueConstraint(fields=('tenant_id', 'id'), name='sales_delivery_tenant_id_uq'),
        ),
        migrations.AddConstraint(
            model_name='deliverynoteline',
            constraint=models.UniqueConstraint(fields=('tenant_id', 'id'), name='sales_delivery_line_tenant_uq'),
        ),
        migrations.AddConstraint(
            model_name='deliverynoteline',
            constraint=models.UniqueConstraint(condition=models.Q(('deleted_at__isnull', True)), fields=('tenant_id', 'delivery_note', 'line_number'), name='sales_delivery_line_number_uq'),
        ),
        migrations.AddConstraint(
            model_name='quotation',
            constraint=models.UniqueConstraint(fields=('tenant_id', 'id'), name='sales_quote_tenant_id_uq'),
        ),
        migrations.AddConstraint(
            model_name='quotation',
            constraint=models.CheckConstraint(condition=models.Q(('currency__regex', '^[A-Z]{3}$')), name='sales_quote_currency_ck'),
        ),
        migrations.AddConstraint(
            model_name='quotationline',
            constraint=models.UniqueConstraint(fields=('tenant_id', 'id'), name='sales_quote_line_tenant_id_uq'),
        ),
        migrations.AddConstraint(
            model_name='salesconfiguration',
            constraint=models.UniqueConstraint(fields=('tenant_id', 'id'), name='sales_config_tenant_id_uq'),
        ),
        migrations.AddConstraint(
            model_name='salesconfiguration',
            constraint=models.CheckConstraint(condition=models.Q(('environment__in', ('development', 'self-hosted', 'saas'))), name='sales_config_environment_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesconfiguration',
            constraint=models.CheckConstraint(condition=models.Q(('default_currency__regex', '^[A-Z]{3}$')), name='sales_config_currency_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesconfiguration',
            constraint=models.CheckConstraint(condition=models.Q(('quotation_prefix__regex', '^[A-Z0-9-]{1,12}$')), name='sales_config_quote_prefix_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesconfiguration',
            constraint=models.CheckConstraint(condition=models.Q(('order_prefix__regex', '^[A-Z0-9-]{1,12}$')), name='sales_config_order_prefix_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesconfiguration',
            constraint=models.CheckConstraint(condition=models.Q(('delivery_prefix__regex', '^[A-Z0-9-]{1,12}$')), name='sales_config_delivery_prefix_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesdocumentsequence',
            constraint=models.CheckConstraint(condition=models.Q(('environment__in', ('development', 'self-hosted', 'saas'))), name='sales_sequence_environment_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorder',
            constraint=models.UniqueConstraint(fields=('tenant_id', 'id'), name='sales_order_tenant_id_uq'),
        ),
        migrations.AddConstraint(
            model_name='salesorder',
            constraint=models.CheckConstraint(condition=models.Q(('currency__regex', '^[A-Z]{3}$')), name='sales_order_currency_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorderline',
            constraint=models.UniqueConstraint(fields=('tenant_id', 'id'), name='sales_order_line_tenant_id_uq'),
        ),
        migrations.AddConstraint(
            model_name='salesorderline',
            constraint=models.UniqueConstraint(condition=models.Q(('deleted_at__isnull', True)), fields=('tenant_id', 'sales_order', 'line_number'), name='sales_order_line_number_uq'),
        ),
        migrations.RemoveConstraint(
            model_name='customer',
            name='unique_customer_code_per_tenant',
        ),
        migrations.RemoveConstraint(
            model_name='deliverynote',
            name='unique_delivery_number_per_tenant',
        ),
        migrations.RemoveConstraint(
            model_name='quotation',
            name='unique_quotation_number_per_tenant',
        ),
        migrations.RemoveConstraint(
            model_name='salesorder',
            name='unique_order_number_per_tenant',
        ),
        migrations.RemoveIndex(
            model_name='deliverynote',
            name='sales_deliv_tenant__5b86ac_idx',
        ),
        migrations.RemoveIndex(
            model_name='deliverynote',
            name='sales_deliv_tenant__39f885_idx',
        ),
        migrations.RemoveIndex(
            model_name='deliverynoteline',
            name='sales_deliv_tenant__79846c_idx',
        ),
        migrations.RemoveIndex(
            model_name='quotation',
            name='sales_quota_tenant__42c204_idx',
        ),
        migrations.RemoveIndex(
            model_name='quotation',
            name='sales_quota_tenant__20a8ce_idx',
        ),
        migrations.RemoveIndex(
            model_name='quotation',
            name='sales_quota_tenant__ea78fb_idx',
        ),
        migrations.RemoveIndex(
            model_name='salesorder',
            name='sales_order_tenant__f031bd_idx',
        ),
        migrations.RemoveIndex(
            model_name='salesorder',
            name='sales_order_tenant__a2081b_idx',
        ),
        migrations.RemoveIndex(
            model_name='salesorder',
            name='sales_order_tenant__0b7893_idx',
        ),
        migrations.RemoveIndex(
            model_name='salesorderline',
            name='sales_order_tenant__7d85e1_idx',
        ),
        migrations.RenameIndex(
            model_name='customer',
            new_name='sales_cust_code_ix',
            old_name='sales_custo_tenant__abefa2_idx',
        ),
        migrations.RenameIndex(
            model_name='deliverynote',
            new_name='sales_delivery_number_ix',
            old_name='sales_deliv_tenant__de8c87_idx',
        ),
        migrations.RenameIndex(
            model_name='deliverynoteline',
            new_name='sales_dl_item_ix',
            old_name='sales_deliv_tenant__457dcf_idx',
        ),
        migrations.RenameIndex(
            model_name='quotation',
            new_name='sales_quote_number_ix',
            old_name='sales_quota_tenant__57baa3_idx',
        ),
        migrations.RenameIndex(
            model_name='salesorder',
            new_name='sales_order_number_ix',
            old_name='sales_order_tenant__c69512_idx',
        ),
        migrations.RenameIndex(
            model_name='salesorderline',
            new_name='sales_ol_item_ix',
            old_name='sales_order_tenant__972ca9_idx',
        ),
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['tenant_id', 'is_active', 'customer_name'], name='sales_cust_active_name_ix'),
        ),
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['tenant_id', 'currency'], name='sales_cust_currency_ix'),
        ),
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['tenant_id', 'deleted_at'], name='sales_cust_deleted_ix'),
        ),
        migrations.AddIndex(
            model_name='deliverynote',
            index=models.Index(fields=['tenant_id', 'sales_order', 'delivery_date'], name='sales_delivery_order_date_ix'),
        ),
        migrations.AddIndex(
            model_name='deliverynote',
            index=models.Index(fields=['tenant_id', 'status', 'delivery_date'], name='sales_delivery_status_date_ix'),
        ),
        migrations.AddIndex(
            model_name='deliverynote',
            index=models.Index(fields=['tenant_id', 'tracking_number'], name='sales_delivery_tracking_ix'),
        ),
        migrations.AddIndex(
            model_name='deliverynote',
            index=models.Index(fields=['tenant_id', 'deleted_at'], name='sales_delivery_deleted_ix'),
        ),
        migrations.AddIndex(
            model_name='deliverynoteline',
            index=models.Index(fields=['tenant_id', 'delivery_note', 'line_number'], name='sales_dl_note_line_ix'),
        ),
        migrations.AddIndex(
            model_name='deliverynoteline',
            index=models.Index(fields=['tenant_id', 'sales_order_line'], name='sales_dl_order_line_ix'),
        ),
        migrations.AddIndex(
            model_name='deliverynoteline',
            index=models.Index(fields=['tenant_id', 'serial_number'], name='sales_dl_serial_ix'),
        ),
        migrations.AddIndex(
            model_name='deliverynoteline',
            index=models.Index(fields=['tenant_id', 'deleted_at'], name='sales_dl_deleted_ix'),
        ),
        migrations.AddIndex(
            model_name='quotation',
            index=models.Index(fields=['tenant_id', 'customer', 'quotation_date'], name='sales_quote_customer_date_ix'),
        ),
        migrations.AddIndex(
            model_name='quotation',
            index=models.Index(fields=['tenant_id', 'status', 'valid_until'], name='sales_quote_status_valid_ix'),
        ),
        migrations.AddIndex(
            model_name='quotation',
            index=models.Index(fields=['tenant_id', 'created_at'], name='sales_quote_created_ix'),
        ),
        migrations.AddIndex(
            model_name='quotation',
            index=models.Index(fields=['tenant_id', 'deleted_at'], name='sales_quote_deleted_ix'),
        ),
        migrations.AddIndex(
            model_name='salesorder',
            index=models.Index(fields=['tenant_id', 'customer', 'order_date'], name='sales_order_customer_date_ix'),
        ),
        migrations.AddIndex(
            model_name='salesorder',
            index=models.Index(fields=['tenant_id', 'status', 'delivery_date'], name='sales_order_status_date_ix'),
        ),
        migrations.AddIndex(
            model_name='salesorder',
            index=models.Index(fields=['tenant_id', 'warehouse_id'], name='sales_order_warehouse_ix'),
        ),
        migrations.AddIndex(
            model_name='salesorder',
            index=models.Index(fields=['tenant_id', 'quotation'], name='sales_order_quote_ix'),
        ),
        migrations.AddIndex(
            model_name='salesorder',
            index=models.Index(fields=['tenant_id', 'deleted_at'], name='sales_order_deleted_ix'),
        ),
        migrations.AddIndex(
            model_name='salesorderline',
            index=models.Index(fields=['tenant_id', 'sales_order', 'line_number'], name='sales_ol_order_line_ix'),
        ),
        migrations.AddIndex(
            model_name='salesorderline',
            index=models.Index(fields=['tenant_id', 'delivered_quantity'], name='sales_ol_delivered_ix'),
        ),
        migrations.AddIndex(
            model_name='salesorderline',
            index=models.Index(fields=['tenant_id', 'deleted_at'], name='sales_ol_deleted_ix'),
        ),
        migrations.AddConstraint(
            model_name='customer',
            constraint=models.UniqueConstraint(condition=models.Q(('deleted_at__isnull', True)), fields=('tenant_id', 'customer_code'), name='sales_customer_code_tenant_uniq'),
        ),
        migrations.AddConstraint(
            model_name='customer',
            constraint=models.CheckConstraint(condition=models.Q(('credit_limit__isnull', True), ('credit_limit__gte', 0), _connector='OR'), name='sales_customer_credit_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='deliverynote',
            constraint=models.UniqueConstraint(condition=models.Q(('deleted_at__isnull', True)), fields=('tenant_id', 'delivery_number'), name='sales_delivery_number_uq'),
        ),
        migrations.AddConstraint(
            model_name='deliverynote',
            constraint=models.CheckConstraint(condition=models.Q(('tracking_number', ''), models.Q(('carrier_name', ''), _negated=True), _connector='OR'), name='sales_delivery_tracking_ck'),
        ),
        migrations.AddConstraint(
            model_name='deliverynoteline',
            constraint=models.CheckConstraint(condition=models.Q(('quantity_delivered__gt', 0)), name='sales_dl_quantity_ck'),
        ),
        migrations.AddConstraint(
            model_name='quotation',
            constraint=models.UniqueConstraint(condition=models.Q(('deleted_at__isnull', True)), fields=('tenant_id', 'quotation_number', 'revision_number'), name='sales_quote_number_rev_uq'),
        ),
        migrations.AddConstraint(
            model_name='quotation',
            constraint=models.CheckConstraint(condition=models.Q(('valid_until__gte', models.F('quotation_date'))), name='sales_quote_dates_ck'),
        ),
        migrations.AddConstraint(
            model_name='quotation',
            constraint=models.CheckConstraint(condition=models.Q(('subtotal_amount__gte', 0)), name='sales_quote_subtotal_ck'),
        ),
        migrations.AddConstraint(
            model_name='quotation',
            constraint=models.CheckConstraint(condition=models.Q(('discount_amount__gte', 0)), name='sales_quote_discount_ck'),
        ),
        migrations.AddConstraint(
            model_name='quotation',
            constraint=models.CheckConstraint(condition=models.Q(('tax_amount__gte', 0)), name='sales_quote_tax_ck'),
        ),
        migrations.AddConstraint(
            model_name='quotation',
            constraint=models.CheckConstraint(condition=models.Q(('total_amount__gte', 0)), name='sales_quote_total_ck'),
        ),
        migrations.AddConstraint(
            model_name='quotation',
            constraint=models.CheckConstraint(condition=models.Q(('revision_number__gte', 1)), name='sales_quote_revision_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorder',
            constraint=models.UniqueConstraint(condition=models.Q(('deleted_at__isnull', True)), fields=('tenant_id', 'order_number'), name='sales_order_number_tenant_uq'),
        ),
        migrations.AddConstraint(
            model_name='salesorder',
            constraint=models.UniqueConstraint(condition=models.Q(('deleted_at__isnull', True), ('quotation__isnull', False)), fields=('tenant_id', 'quotation'), name='sales_order_quote_once_uq'),
        ),
        migrations.AddConstraint(
            model_name='salesorder',
            constraint=models.CheckConstraint(condition=models.Q(('delivery_date__isnull', True), ('delivery_date__gte', models.F('order_date')), _connector='OR'), name='sales_order_dates_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorder',
            constraint=models.CheckConstraint(condition=models.Q(('subtotal_amount__gte', 0)), name='sales_order_subtotal_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorder',
            constraint=models.CheckConstraint(condition=models.Q(('discount_amount__gte', 0)), name='sales_order_discount_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorder',
            constraint=models.CheckConstraint(condition=models.Q(('tax_amount__gte', 0)), name='sales_order_tax_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorder',
            constraint=models.CheckConstraint(condition=models.Q(('total_amount__gte', 0)), name='sales_order_total_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorderline',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__gt', 0), ('quantity__lte', Decimal('999999'))), name='sales_ol_qty_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorderline',
            constraint=models.CheckConstraint(condition=models.Q(('unit_price__gte', 0), ('unit_price__lte', Decimal('999999999.99'))), name='sales_ol_price_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorderline',
            constraint=models.CheckConstraint(condition=models.Q(('discount_percent__gte', 0), ('discount_percent__lte', 100)), name='sales_ol_discount_pct_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorderline',
            constraint=models.CheckConstraint(condition=models.Q(('gross_amount__gte', 0)), name='sales_ol_gross_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorderline',
            constraint=models.CheckConstraint(condition=models.Q(('discount_amount__gte', 0)), name='sales_ol_discount_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorderline',
            constraint=models.CheckConstraint(condition=models.Q(('tax_amount__gte', 0)), name='sales_ol_tax_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorderline',
            constraint=models.CheckConstraint(condition=models.Q(('tax_rate__gte', 0), ('tax_rate__lte', 100)), name='sales_ol_tax_rate_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorderline',
            constraint=models.CheckConstraint(condition=models.Q(('total_price__gte', 0)), name='sales_ol_total_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesorderline',
            constraint=models.CheckConstraint(condition=models.Q(('delivered_quantity__gte', 0), ('delivered_quantity__lte', models.F('quantity'))), name='sales_ol_delivered_ck'),
        ),
        migrations.AddIndex(
            model_name='salesconfiguration',
            index=models.Index(fields=['tenant_id', 'environment'], name='sales_config_environment_ix'),
        ),
        migrations.AddConstraint(
            model_name='salesconfiguration',
            constraint=models.UniqueConstraint(condition=models.Q(('deleted_at__isnull', True)), fields=('tenant_id', 'environment'), name='sales_config_environment_uq'),
        ),
        migrations.AddConstraint(
            model_name='salesconfiguration',
            constraint=models.CheckConstraint(condition=models.Q(('quotation_validity_days__gte', 1), ('quotation_validity_days__lte', 365)), name='sales_config_validity_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesconfiguration',
            constraint=models.CheckConstraint(condition=models.Q(('currency_decimal_places__gte', 0), ('currency_decimal_places__lte', 4)), name='sales_config_precision_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesconfiguration',
            constraint=models.CheckConstraint(condition=models.Q(('maximum_manual_discount_percent__gte', 0), ('maximum_manual_discount_percent__lte', 100)), name='sales_config_discount_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesconfiguration',
            constraint=models.CheckConstraint(condition=models.Q(('sequence_padding__gte', 4), ('sequence_padding__lte', 12)), name='sales_config_padding_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesconfiguration',
            constraint=models.CheckConstraint(condition=models.Q(('version__gte', 1)), name='sales_config_version_ck'),
        ),
        migrations.AddIndex(
            model_name='salesdocumentsequence',
            index=models.Index(fields=['tenant_id', 'environment', 'document_kind'], name='sales_sequence_lookup_ix'),
        ),
        migrations.AddConstraint(
            model_name='salesdocumentsequence',
            constraint=models.UniqueConstraint(fields=('tenant_id', 'environment', 'document_kind'), name='sales_document_sequence_uq'),
        ),
        migrations.AddConstraint(
            model_name='salesdocumentsequence',
            constraint=models.CheckConstraint(condition=models.Q(('next_value__gte', 1)), name='sales_sequence_next_ck'),
        ),
        migrations.AddConstraint(
            model_name='salesdocumentsequence',
            constraint=models.CheckConstraint(condition=models.Q(('lock_version__gte', 1)), name='sales_sequence_lock_ck'),
        ),
        migrations.AddIndex(
            model_name='quotationline',
            index=models.Index(fields=['tenant_id', 'quotation', 'line_number'], name='sales_ql_quote_line_ix'),
        ),
        migrations.AddIndex(
            model_name='quotationline',
            index=models.Index(fields=['tenant_id', 'item_id'], name='sales_ql_item_ix'),
        ),
        migrations.AddIndex(
            model_name='quotationline',
            index=models.Index(fields=['tenant_id', 'deleted_at'], name='sales_ql_deleted_ix'),
        ),
        migrations.AddConstraint(
            model_name='quotationline',
            constraint=models.UniqueConstraint(condition=models.Q(('deleted_at__isnull', True)), fields=('tenant_id', 'quotation', 'line_number'), name='sales_quote_line_number_uq'),
        ),
        migrations.AddConstraint(
            model_name='quotationline',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__gt', 0), ('quantity__lte', Decimal('999999'))), name='sales_ql_qty_ck'),
        ),
        migrations.AddConstraint(
            model_name='quotationline',
            constraint=models.CheckConstraint(condition=models.Q(('unit_price__gte', 0), ('unit_price__lte', Decimal('999999999.99'))), name='sales_ql_price_ck'),
        ),
        migrations.AddConstraint(
            model_name='quotationline',
            constraint=models.CheckConstraint(condition=models.Q(('discount_percent__gte', 0), ('discount_percent__lte', 100)), name='sales_ql_discount_pct_ck'),
        ),
        migrations.AddConstraint(
            model_name='quotationline',
            constraint=models.CheckConstraint(condition=models.Q(('gross_amount__gte', 0)), name='sales_ql_gross_ck'),
        ),
        migrations.AddConstraint(
            model_name='quotationline',
            constraint=models.CheckConstraint(condition=models.Q(('discount_amount__gte', 0)), name='sales_ql_discount_ck'),
        ),
        migrations.AddConstraint(
            model_name='quotationline',
            constraint=models.CheckConstraint(condition=models.Q(('tax_amount__gte', 0)), name='sales_ql_tax_ck'),
        ),
        migrations.AddConstraint(
            model_name='quotationline',
            constraint=models.CheckConstraint(condition=models.Q(('tax_rate__gte', 0), ('tax_rate__lte', 100)), name='sales_ql_tax_rate_ck'),
        ),
        migrations.AddConstraint(
            model_name='quotationline',
            constraint=models.CheckConstraint(condition=models.Q(('line_total__gte', 0)), name='sales_ql_total_ck'),
        ),
        migrations.AddIndex(
            model_name='salesconfigurationversion',
            index=models.Index(fields=['tenant_id', 'configuration', '-version'], name='sales_config_hist_version_ix'),
        ),
        migrations.AddIndex(
            model_name='salesconfigurationversion',
            index=models.Index(fields=['tenant_id', '-created_at'], name='sales_config_hist_created_ix'),
        ),
        migrations.AddIndex(
            model_name='salesconfigurationversion',
            index=models.Index(fields=['tenant_id', 'correlation_id'], name='sales_config_hist_corr_ix'),
        ),
        migrations.AddConstraint(
            model_name='salesconfigurationversion',
            constraint=models.UniqueConstraint(fields=('tenant_id', 'configuration', 'version'), name='sales_config_version_uq'),
        ),
        migrations.AddConstraint(
            model_name='salesconfigurationversion',
            constraint=models.CheckConstraint(condition=models.Q(('version__gte', 1)), name='sales_config_hist_version_ck'),
        ),
        migrations.RunPython(install_composite_tenant_guards, remove_composite_tenant_guards),
    ]
