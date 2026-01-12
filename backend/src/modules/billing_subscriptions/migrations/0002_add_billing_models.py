# Generated migration for Billing Subscriptions models

import src.modules.billing_subscriptions.models
from django.db import migrations, models
import django.db.models.deletion
from django.core.validators import MinValueValidator
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ("billing_subscriptions", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SubscriptionPlan",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=src.modules.billing_subscriptions.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(db_index=True, max_length=255, unique=True)),
                ("description", models.TextField(blank=True)),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Price in default currency",
                        max_digits=10,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "billing_cycle",
                    models.CharField(
                        choices=[
                            ("monthly", "Monthly"),
                            ("quarterly", "Quarterly"),
                            ("yearly", "Yearly"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("features", models.JSONField(default=list)),
                ("limits", models.JSONField(default=dict)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "billing_subscriptions_plans",
                "indexes": [
                    models.Index(fields=["billing_cycle", "is_active"], name="billing_subsc_billing__active_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.billing_subscriptions.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("cancelled", "Cancelled"),
                            ("expired", "Expired"),
                            ("trial", "Trial"),
                            ("past_due", "Past Due"),
                        ],
                        db_index=True,
                        default="trial",
                        max_length=20,
                    ),
                ),
                ("start_date", models.DateField(db_index=True)),
                ("end_date", models.DateField(blank=True, db_index=True, null=True)),
                ("trial_start_date", models.DateField(blank=True, null=True)),
                ("trial_end_date", models.DateField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("cancellation_reason", models.TextField(blank=True)),
                (
                    "plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="subscriptions",
                        to="billing_subscriptions.subscriptionplan",
                    ),
                ),
            ],
            options={
                "db_table": "billing_subscriptions_subscriptions",
                "indexes": [
                    models.Index(fields=["tenant_id", "status"], name="billing_subsc_sub_tenant__status_idx"),
                    models.Index(fields=["tenant_id", "end_date"], name="billing_subsc_sub_tenant__end_date_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Invoice",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.billing_subscriptions.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("invoice_number", models.CharField(db_index=True, max_length=50, unique=True)),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "tax_amount",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=10,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "total_amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("pending", "Pending"),
                            ("paid", "Paid"),
                            ("overdue", "Overdue"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("due_date", models.DateField(db_index=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                (
                    "subscription",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="invoices",
                        to="billing_subscriptions.subscription",
                    ),
                ),
            ],
            options={
                "db_table": "billing_subscriptions_invoices",
                "indexes": [
                    models.Index(fields=["tenant_id", "status"], name="billing_subsc_inv_tenant__status_idx"),
                    models.Index(fields=["tenant_id", "due_date"], name="billing_subsc_inv_tenant__due_date_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="InvoiceLineItem",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=src.modules.billing_subscriptions.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("description", models.CharField(max_length=500)),
                (
                    "quantity",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("1.00"),
                        max_digits=10,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "unit_price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "total_price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="line_items",
                        to="billing_subscriptions.invoice",
                    ),
                ),
            ],
            options={
                "db_table": "billing_subscriptions_invoice_line_items",
            },
        ),
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.billing_subscriptions.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "payment_method",
                    models.CharField(
                        choices=[
                            ("credit_card", "Credit Card"),
                            ("bank_transfer", "Bank Transfer"),
                            ("paypal", "PayPal"),
                            ("stripe", "Stripe"),
                            ("other", "Other"),
                        ],
                        max_length=50,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("refunded", "Refunded"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("transaction_id", models.CharField(blank=True, max_length=255)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payments",
                        to="billing_subscriptions.invoice",
                    ),
                ),
            ],
            options={
                "db_table": "billing_subscriptions_payments",
                "indexes": [
                    models.Index(fields=["tenant_id", "status"], name="billing_subsc_pay_tenant__status_idx"),
                    models.Index(fields=["invoice"], name="billing_subsc_payment_invoice_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="UsageRecord",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.billing_subscriptions.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "resource_type",
                    models.CharField(
                        choices=[
                            ("api_calls", "API Calls"),
                            ("storage_gb", "Storage (GB)"),
                            ("users", "Users"),
                            ("compute_hours", "Compute Hours"),
                        ],
                        db_index=True,
                        max_length=50,
                    ),
                ),
                (
                    "quantity",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=15,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                ("recorded_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "db_table": "billing_subscriptions_usage_records",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "resource_type", "recorded_at"],
                        name="billing_subsc_tenant__resource__recorded_idx",
                    ),
                ],
            },
        ),
    ]
