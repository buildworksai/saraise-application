"""Complete the additive sales domain without rewriting applied 0001 history."""

import datetime
import django.core.validators
import django.db.models.deletion
import src.modules.sales_management.models
import uuid
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales_management', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='QuotationLine',
            fields=[
                ('tenant_id', models.UUIDField(db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_by', models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False)),
                ('updated_by', models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False)),
                ('deleted_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('deleted_by', models.UUIDField(blank=True, editable=False, null=True)),
                ('lock_version', models.PositiveBigIntegerField(default=1, editable=False)),
                ('line_number', models.PositiveIntegerField(default=1)),
                ('item_id', models.UUIDField(blank=True, null=True)),
                ('item_code', models.CharField(max_length=100)),
                ('item_name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('quantity', models.DecimalField(decimal_places=4, max_digits=15)),
                ('unit_price', models.DecimalField(decimal_places=4, max_digits=15)),
                ('discount_percent', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=5)),
                ('gross_amount', models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=15)),
                ('discount_amount', models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=15)),
                ('tax_amount', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=15)),
                ('tax_rate', models.DecimalField(decimal_places=4, default=Decimal('0'), max_digits=7)),
                ('tax_source', models.CharField(blank=True, max_length=64)),
                ('tax_snapshot', models.JSONField(blank=True, default=dict)),
                ('line_total', models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=15)),
            ],
            options={
                'db_table': 'sales_quotation_lines',
                'ordering': ('line_number', 'id'),
            },
        ),
        migrations.CreateModel(
            name='SalesConfiguration',
            fields=[
                ('tenant_id', models.UUIDField(db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_by', models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False)),
                ('updated_by', models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False)),
                ('deleted_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('deleted_by', models.UUIDField(blank=True, editable=False, null=True)),
                ('lock_version', models.PositiveBigIntegerField(default=1, editable=False)),
                ('environment', models.CharField(max_length=32)),
                ('default_currency', models.CharField(default='USD', max_length=3, validators=[django.core.validators.RegexValidator('^[A-Z]{3}$', 'Use a three-letter uppercase ISO-4217 currency code.')])),
                ('currency_decimal_places', models.PositiveSmallIntegerField(default=2, validators=[django.core.validators.MaxValueValidator(4)])),
                ('rounding_mode', models.CharField(choices=[('ROUND_HALF_UP', 'Half up'), ('ROUND_HALF_EVEN', 'Half even')], default='ROUND_HALF_UP', max_length=20)),
                ('quotation_validity_days', models.PositiveSmallIntegerField(default=30, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(365)])),
                ('credit_check_enabled', models.BooleanField(default=True)),
                ('inventory_confirmation_required', models.BooleanField(default=False)),
                ('manual_discount_enabled', models.BooleanField(default=True)),
                ('maximum_manual_discount_percent', models.DecimalField(decimal_places=2, default=Decimal('20'), max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('100'))])),
                ('manual_tax_enabled', models.BooleanField(default=True)),
                ('quotation_prefix', models.CharField(default='QT', max_length=12, validators=[django.core.validators.RegexValidator('^[A-Z0-9-]{1,12}$', 'Use 1-12 uppercase letters, digits, or hyphens.')])),
                ('order_prefix', models.CharField(default='SO', max_length=12, validators=[django.core.validators.RegexValidator('^[A-Z0-9-]{1,12}$', 'Use 1-12 uppercase letters, digits, or hyphens.')])),
                ('delivery_prefix', models.CharField(default='DN', max_length=12, validators=[django.core.validators.RegexValidator('^[A-Z0-9-]{1,12}$', 'Use 1-12 uppercase letters, digits, or hyphens.')])),
                ('sequence_padding', models.PositiveSmallIntegerField(default=6, validators=[django.core.validators.MinValueValidator(4), django.core.validators.MaxValueValidator(12)])),
                ('version', models.PositiveBigIntegerField(default=1, editable=False)),
            ],
            options={
                'db_table': 'sales_configurations',
                'ordering': ('environment',),
            },
        ),
        migrations.CreateModel(
            name='SalesConfigurationVersion',
            fields=[
                ('tenant_id', models.UUIDField(db_index=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version', models.PositiveBigIntegerField()),
                ('snapshot', models.JSONField(validators=[src.modules.sales_management.models.validate_configuration_snapshot])),
                ('change_reason', models.CharField(max_length=500)),
                ('actor_id', models.UUIDField()),
                ('correlation_id', models.UUIDField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'sales_configuration_versions',
                'ordering': ('-version', '-created_at'),
            },
        ),
        migrations.CreateModel(
            name='SalesDocumentSequence',
            fields=[
                ('tenant_id', models.UUIDField(db_index=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('environment', models.CharField(max_length=32)),
                ('document_kind', models.CharField(choices=[('quotation', 'Quotation'), ('sales_order', 'Sales order'), ('delivery_note', 'Delivery note')], max_length=20)),
                ('next_value', models.PositiveBigIntegerField(default=1)),
                ('lock_version', models.PositiveBigIntegerField(default=1)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'sales_document_sequences',
                'ordering': ('environment', 'document_kind'),
            },
        ),
        migrations.AlterModelOptions(
            name='customer',
            options={'ordering': ('customer_code', 'id')},
        ),
        migrations.AlterModelOptions(
            name='deliverynote',
            options={'ordering': ('-delivery_date', 'delivery_number')},
        ),
        migrations.AlterModelOptions(
            name='deliverynoteline',
            options={'ordering': ('line_number', 'id')},
        ),
        migrations.AlterModelOptions(
            name='quotation',
            options={'ordering': ('-quotation_date', 'quotation_number', '-revision_number')},
        ),
        migrations.AlterModelOptions(
            name='salesorder',
            options={'ordering': ('-order_date', 'order_number')},
        ),
        migrations.AlterModelOptions(
            name='salesorderline',
            options={'ordering': ('line_number', 'id')},
        ),
        migrations.RenameField(
            model_name='deliverynoteline',
            old_name='batch_no',
            new_name='batch_number',
        ),
        migrations.RenameField(
            model_name='deliverynoteline',
            old_name='serial_no',
            new_name='serial_number',
        ),
        migrations.AddField(
            model_name='customer',
            name='created_by',
            field=models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False),
        ),
        migrations.AddField(
            model_name='customer',
            name='deleted_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='customer',
            name='deleted_by',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='customer',
            name='lock_version',
            field=models.PositiveBigIntegerField(default=1, editable=False),
        ),
        migrations.AddField(
            model_name='customer',
            name='updated_by',
            field=models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False),
        ),
        migrations.AddField(
            model_name='deliverynote',
            name='carrier_name',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='deliverynote',
            name='created_by',
            field=models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False),
        ),
        migrations.AddField(
            model_name='deliverynote',
            name='deleted_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='deliverynote',
            name='deleted_by',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='deliverynote',
            name='lock_version',
            field=models.PositiveBigIntegerField(default=1, editable=False),
        ),
        migrations.AddField(
            model_name='deliverynote',
            name='notes',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='deliverynote',
            name='proof_document_id',
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='deliverynote',
            name='tracking_number',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='deliverynote',
            name='transition_history',
            field=models.JSONField(blank=True, default=list, editable=False),
        ),
        migrations.AddField(
            model_name='deliverynote',
            name='updated_by',
            field=models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False),
        ),
        migrations.AddField(
            model_name='deliverynoteline',
            name='created_by',
            field=models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False),
        ),
        migrations.AddField(
            model_name='deliverynoteline',
            name='deleted_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='deliverynoteline',
            name='deleted_by',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='deliverynoteline',
            name='line_number',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='deliverynoteline',
            name='lock_version',
            field=models.PositiveBigIntegerField(default=1, editable=False),
        ),
        migrations.AddField(
            model_name='deliverynoteline',
            name='updated_by',
            field=models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False),
        ),
        migrations.AddField(
            model_name='quotation',
            name='created_by',
            field=models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False),
        ),
        migrations.AddField(
            model_name='quotation',
            name='deleted_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='quotation',
            name='deleted_by',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='quotation',
            name='discount_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=15),
        ),
        migrations.AddField(
            model_name='quotation',
            name='lock_version',
            field=models.PositiveBigIntegerField(default=1, editable=False),
        ),
        migrations.AddField(
            model_name='quotation',
            name='notes',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='quotation',
            name='revision_number',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='quotation',
            name='revision_of',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='revisions', to='sales_management.quotation'),
        ),
        migrations.AddField(
            model_name='quotation',
            name='subtotal_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=15),
        ),
        migrations.AddField(
            model_name='quotation',
            name='tax_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=15),
        ),
        migrations.AddField(
            model_name='quotation',
            name='transition_history',
            field=models.JSONField(blank=True, default=list, editable=False),
        ),
        migrations.AddField(
            model_name='quotation',
            name='updated_by',
            field=models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False),
        ),
        migrations.AddField(
            model_name='salesorder',
            name='created_by',
            field=models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False),
        ),
        migrations.AddField(
            model_name='salesorder',
            name='deleted_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='salesorder',
            name='deleted_by',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='salesorder',
            name='discount_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=15),
        ),
        migrations.AddField(
            model_name='salesorder',
            name='external_invoice_id',
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='salesorder',
            name='lock_version',
            field=models.PositiveBigIntegerField(default=1, editable=False),
        ),
        migrations.AddField(
            model_name='salesorder',
            name='notes',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='salesorder',
            name='subtotal_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=15),
        ),
        migrations.AddField(
            model_name='salesorder',
            name='tax_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=15),
        ),
        migrations.AddField(
            model_name='salesorder',
            name='transition_history',
            field=models.JSONField(blank=True, default=list, editable=False),
        ),
        migrations.AddField(
            model_name='salesorder',
            name='updated_by',
            field=models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False),
        ),
        migrations.AddField(
            model_name='salesorderline',
            name='created_by',
            field=models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False),
        ),
        migrations.AddField(
            model_name='salesorderline',
            name='deleted_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='salesorderline',
            name='deleted_by',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='salesorderline',
            name='description',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='salesorderline',
            name='discount_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=15),
        ),
        migrations.AddField(
            model_name='salesorderline',
            name='discount_percent',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=5),
        ),
        migrations.AddField(
            model_name='salesorderline',
            name='gross_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=15),
        ),
        migrations.AddField(
            model_name='salesorderline',
            name='line_number',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='salesorderline',
            name='lock_version',
            field=models.PositiveBigIntegerField(default=1, editable=False),
        ),
        migrations.AddField(
            model_name='salesorderline',
            name='source_quotation_line_id',
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='salesorderline',
            name='tax_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=15),
        ),
        migrations.AddField(
            model_name='salesorderline',
            name='tax_rate',
            field=models.DecimalField(decimal_places=4, default=Decimal('0'), max_digits=7),
        ),
        migrations.AddField(
            model_name='salesorderline',
            name='tax_snapshot',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='salesorderline',
            name='tax_source',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='salesorderline',
            name='updated_by',
            field=models.UUIDField(default=uuid.UUID('00000000-0000-0000-0000-000000000000'), editable=False),
        ),
        migrations.AlterField(
            model_name='customer',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='customer',
            name='currency',
            field=models.CharField(default='USD', max_length=3, validators=[django.core.validators.RegexValidator('^[A-Z]{3}$', 'Use a three-letter uppercase ISO-4217 currency code.')]),
        ),
        migrations.AlterField(
            model_name='customer',
            name='customer_code',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name='customer',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='deliverynote',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='deliverynote',
            name='delivery_date',
            field=models.DateField(),
        ),
        migrations.AlterField(
            model_name='deliverynote',
            name='delivery_number',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name='deliverynote',
            name='status',
            field=models.CharField(choices=[('draft', 'Draft'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='draft', max_length=20),
        ),
        migrations.AlterField(
            model_name='deliverynote',
            name='warehouse_id',
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='deliverynoteline',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='deliverynoteline',
            name='item_id',
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='deliverynoteline',
            name='quantity_delivered',
            field=models.DecimalField(decimal_places=4, max_digits=15),
        ),
        migrations.AlterField(
            model_name='quotation',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='quotation',
            name='currency',
            field=models.CharField(default='USD', max_length=3, validators=[django.core.validators.RegexValidator('^[A-Z]{3}$', 'Use a three-letter uppercase ISO-4217 currency code.')]),
        ),
        migrations.AlterField(
            model_name='quotation',
            name='quotation_date',
            field=models.DateField(),
        ),
        migrations.AlterField(
            model_name='quotation',
            name='quotation_number',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name='quotation',
            name='status',
            field=models.CharField(choices=[('draft', 'Draft'), ('sent', 'Sent'), ('accepted', 'Accepted'), ('rejected', 'Rejected'), ('expired', 'Expired'), ('converted', 'Converted to order')], default='draft', max_length=20),
        ),
        migrations.AlterField(
            model_name='quotation',
            name='total_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=15),
        ),
        migrations.AlterField(
            model_name='quotation',
            name='valid_until',
            field=models.DateField(default=datetime.date.today),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='currency',
            field=models.CharField(default='USD', max_length=3, validators=[django.core.validators.RegexValidator('^[A-Z]{3}$', 'Use a three-letter uppercase ISO-4217 currency code.')]),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='order_date',
            field=models.DateField(),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='order_number',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='quotation',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sales_orders', to='sales_management.quotation'),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='status',
            field=models.CharField(choices=[('draft', 'Draft'), ('confirmed', 'Confirmed'), ('picking', 'Picking'), ('packing', 'Packing'), ('ready_to_ship', 'Ready to ship'), ('shipped', 'Shipped'), ('delivered', 'Delivered'), ('invoiced', 'Invoiced'), ('cancelled', 'Cancelled')], default='draft', max_length=30),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='total_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=15),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='warehouse_id',
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='salesorderline',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='salesorderline',
            name='delivered_quantity',
            field=models.DecimalField(decimal_places=4, default=Decimal('0'), editable=False, max_digits=15),
        ),
        migrations.AlterField(
            model_name='salesorderline',
            name='item_id',
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='salesorderline',
            name='quantity',
            field=models.DecimalField(decimal_places=4, max_digits=15),
        ),
        migrations.AlterField(
            model_name='salesorderline',
            name='total_price',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), editable=False, max_digits=15),
        ),
        migrations.AlterField(
            model_name='salesorderline',
            name='unit_price',
            field=models.DecimalField(decimal_places=4, max_digits=15),
        ),
        migrations.AddField(
            model_name='quotationline',
            name='quotation',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='sales_management.quotation'),
        ),
        migrations.AddField(
            model_name='salesconfigurationversion',
            name='configuration',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='versions', to='sales_management.salesconfiguration'),
        ),
    ]
