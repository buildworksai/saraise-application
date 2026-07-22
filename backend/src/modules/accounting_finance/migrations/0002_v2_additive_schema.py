"""Add and safely backfill the Accounting v2 persistence surface."""

from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


LEGACY_ACTOR = "legacy:migration"


def validate_legacy_references(apps, schema_editor) -> None:
    """Stop rather than inventing ownership for invalid legacy references."""

    del schema_editor
    Account = apps.get_model("accounting_finance", "Account")
    PostingPeriod = apps.get_model("accounting_finance", "PostingPeriod")
    JournalEntry = apps.get_model("accounting_finance", "JournalEntry")
    JournalLine = apps.get_model("accounting_finance", "JournalLine")
    APInvoice = apps.get_model("accounting_finance", "APInvoice")
    ARInvoice = apps.get_model("accounting_finance", "ARInvoice")
    Payment = apps.get_model("accounting_finance", "Payment")

    invalid: list[str] = []
    accounts = {row["id"]: row["tenant_id"] for row in Account.objects.values("id", "tenant_id")}
    for row in Account.objects.exclude(parent_account_id__isnull=True).values("id", "tenant_id", "parent_account_id"):
        if accounts.get(row["parent_account_id"]) != row["tenant_id"]:
            invalid.append(f"account:{row['id']}:parent:{row['parent_account_id']}")

    periods = {row["id"]: row["tenant_id"] for row in PostingPeriod.objects.values("id", "tenant_id")}
    entries = {row["id"]: row["tenant_id"] for row in JournalEntry.objects.values("id", "tenant_id")}
    for row in JournalEntry.objects.values("id", "tenant_id", "posting_period_id"):
        if periods.get(row["posting_period_id"]) != row["tenant_id"]:
            invalid.append(f"journal:{row['id']}:period:{row['posting_period_id']}")
    for row in JournalLine.objects.values("id", "tenant_id", "journal_entry_id", "account_id"):
        if entries.get(row["journal_entry_id"]) != row["tenant_id"]:
            invalid.append(f"journal-line:{row['id']}:entry:{row['journal_entry_id']}")
        if accounts.get(row["account_id"]) != row["tenant_id"]:
            invalid.append(f"journal-line:{row['id']}:account:{row['account_id']}")

    ap = {row["id"]: row["tenant_id"] for row in APInvoice.objects.values("id", "tenant_id")}
    ar = {row["id"]: row["tenant_id"] for row in ARInvoice.objects.values("id", "tenant_id")}
    for row in Payment.objects.values("id", "tenant_id", "ap_invoice_id", "ar_invoice_id"):
        linked = int(row["ap_invoice_id"] is not None) + int(row["ar_invoice_id"] is not None)
        if linked != 1:
            invalid.append(f"payment:{row['id']}:invoice-link-count:{linked}")
        if row["ap_invoice_id"] and ap.get(row["ap_invoice_id"]) != row["tenant_id"]:
            invalid.append(f"payment:{row['id']}:ap:{row['ap_invoice_id']}")
        if row["ar_invoice_id"] and ar.get(row["ar_invoice_id"]) != row["tenant_id"]:
            invalid.append(f"payment:{row['id']}:ar:{row['ar_invoice_id']}")

    if invalid:
        raise RuntimeError("Accounting v2 migration rejected invalid references: " + ", ".join(invalid[:50]))


def backfill_v2_fields(apps, schema_editor) -> None:
    del schema_editor
    Account = apps.get_model("accounting_finance", "Account")
    PostingPeriod = apps.get_model("accounting_finance", "PostingPeriod")
    JournalEntry = apps.get_model("accounting_finance", "JournalEntry")
    JournalLine = apps.get_model("accounting_finance", "JournalLine")
    APInvoice = apps.get_model("accounting_finance", "APInvoice")
    ARInvoice = apps.get_model("accounting_finance", "ARInvoice")
    Payment = apps.get_model("accounting_finance", "Payment")

    credit_types = {"liability", "equity", "revenue"}
    for account in Account.objects.all().iterator():
        account.normal_balance = "credit" if account.account_type in credit_types else "debit"
        account.save(update_fields=("normal_balance",))
    for period in PostingPeriod.objects.all().iterator():
        period.fiscal_year = period.start_date.year
        period.save(update_fields=("fiscal_year",))
    for entry in JournalEntry.objects.all().iterator():
        entry.currency = "USD"
        entry.save(update_fields=("currency",))
        for number, line in enumerate(JournalLine.objects.filter(journal_entry_id=entry.id).order_by("created_at", "id"), 1):
            line.line_number = number
            line.currency = entry.currency
            line.base_debit_amount = line.debit_amount
            line.base_credit_amount = line.credit_amount
            line.save(
                update_fields=("line_number", "currency", "base_debit_amount", "base_credit_amount")
            )
    APInvoice.objects.update(legacy_without_lines=True)
    ARInvoice.objects.update(legacy_without_lines=True)
    for payment in Payment.objects.all().iterator():
        payment.idempotency_key = f"legacy:{payment.id}"
        payment.request_fingerprint = hashlib.sha256(str(payment.id).encode("ascii")).hexdigest()
        payment.save(update_fields=("idempotency_key", "request_fingerprint"))


def noop_reverse(apps, schema_editor) -> None:
    del apps, schema_editor


AUDIT_FIELDS = (
    ("created_by", models.CharField(default=LEGACY_ACTOR, max_length=255)),
    ("updated_by", models.CharField(default=LEGACY_ACTOR, max_length=255)),
    ("version", models.PositiveBigIntegerField(default=1)),
    ("creation_idempotency_key", models.CharField(blank=True, max_length=255, null=True)),
    ("creation_request_fingerprint", models.CharField(blank=True, max_length=64, null=True)),
)
SOFT_DELETE_FIELDS = (
    ("is_deleted", models.BooleanField(db_index=True, default=False)),
    ("deleted_at", models.DateTimeField(blank=True, null=True)),
    ("deleted_by", models.CharField(blank=True, max_length=255, null=True)),
)


class Migration(migrations.Migration):
    dependencies = [("accounting_finance", "0001_initial")]

    operations = [
        migrations.RunPython(validate_legacy_references, noop_reverse),
        # Convert the legacy UUID parent column to a protected relationship.
        migrations.RenameField("account", "parent_account_id", "parent"),
        migrations.AlterField(
            "account",
            "parent",
            models.ForeignKey(
                blank=True,
                db_column="parent_account_id",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="children",
                to="accounting_finance.account",
            ),
        ),
        *[
            migrations.AddField(model_name=model, name=name, field=field)
            for model in ("account", "postingperiod", "journalentry", "apinvoice", "arinvoice")
            for name, field in AUDIT_FIELDS
        ],
        *[
            migrations.AddField(model_name=model, name=name, field=field)
            for model in ("account", "journalentry", "apinvoice", "arinvoice")
            for name, field in SOFT_DELETE_FIELDS
        ],
        *[
            migrations.AddField(model_name=model, name="transition_history", field=models.JSONField(blank=True, default=list, editable=False))
            for model in ("postingperiod", "journalentry", "apinvoice", "arinvoice")
        ],
        migrations.AddField("account", "normal_balance", models.CharField(blank=True, choices=(("debit", "Debit"), ("credit", "Credit")), max_length=10)),
        migrations.AddField("account", "is_group", models.BooleanField(default=False)),
        migrations.AddField("account", "currency", models.CharField(default="USD", max_length=3)),
        migrations.AddField("account", "allow_multi_currency", models.BooleanField(default=False)),
        migrations.AddField("account", "cash_flow_category", models.CharField(blank=True, choices=(("operating", "Operating"), ("investing", "Investing"), ("financing", "Financing")), max_length=12, null=True)),
        migrations.AddField("postingperiod", "fiscal_year", models.PositiveIntegerField(null=True)),
        migrations.AddField("postingperiod", "closed_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("postingperiod", "closed_by", models.CharField(blank=True, max_length=255, null=True)),
        migrations.AddField("postingperiod", "locked_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("postingperiod", "locked_by", models.CharField(blank=True, max_length=255, null=True)),
        migrations.AlterField("postingperiod", "status", models.CharField(choices=(("open", "Open"), ("closed", "Closed"), ("locked", "Locked")), default="open", max_length=20)),
        migrations.AddField("journalentry", "reference", models.CharField(blank=True, max_length=255)),
        migrations.AddField("journalentry", "currency", models.CharField(blank=True, max_length=3)),
        migrations.AddField("journalentry", "reversed_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("journalentry", "reversed_by", models.CharField(blank=True, max_length=255, null=True)),
        migrations.AddField("journalentry", "reversed_entry", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reversal_entries", to="accounting_finance.journalentry")),
        migrations.AddField("journalentry", "source_module", models.CharField(blank=True, max_length=100)),
        migrations.AddField("journalentry", "source_reference", models.CharField(blank=True, max_length=255)),
        migrations.AddField("journalentry", "source_idempotency_key", models.CharField(blank=True, max_length=255, null=True)),
        migrations.AlterField("journalentry", "posted_by", models.CharField(blank=True, max_length=255, null=True)),
        migrations.AddField("journalline", "line_number", models.PositiveIntegerField(null=True)),
        migrations.AddField("journalline", "currency", models.CharField(blank=True, max_length=3)),
        migrations.AddField("journalline", "exchange_rate", models.DecimalField(decimal_places=8, default=Decimal("1.00000000"), max_digits=18)),
        migrations.AddField("journalline", "base_debit_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=15)),
        migrations.AddField("journalline", "base_credit_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=15)),
        migrations.AddField("journalline", "dimension_values", models.JSONField(blank=True, default=dict)),
        migrations.AddField("apinvoice", "exchange_rate", models.DecimalField(decimal_places=8, default=Decimal("1.00000000"), max_digits=18)),
        migrations.AddField("apinvoice", "approved_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("apinvoice", "approved_by", models.CharField(blank=True, max_length=255, null=True)),
        migrations.AddField("apinvoice", "posted_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("apinvoice", "posted_by", models.CharField(blank=True, max_length=255, null=True)),
        migrations.AddField("apinvoice", "cancelled_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("apinvoice", "cancelled_by", models.CharField(blank=True, max_length=255, null=True)),
        migrations.AddField("apinvoice", "journal_entry", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="accounting_finance.journalentry")),
        migrations.AddField("apinvoice", "legacy_without_lines", models.BooleanField(default=False)),
        migrations.AlterField("apinvoice", "status", models.CharField(choices=(("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"), ("posted", "Posted"), ("partially_paid", "Partially paid"), ("paid", "Paid"), ("cancelled", "Cancelled")), default="draft", max_length=20)),
        migrations.AddField("arinvoice", "exchange_rate", models.DecimalField(decimal_places=8, default=Decimal("1.00000000"), max_digits=18)),
        migrations.AddField("arinvoice", "posted_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("arinvoice", "posted_by", models.CharField(blank=True, max_length=255, null=True)),
        migrations.AddField("arinvoice", "cancelled_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("arinvoice", "cancelled_by", models.CharField(blank=True, max_length=255, null=True)),
        migrations.AddField("arinvoice", "journal_entry", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="accounting_finance.journalentry")),
        migrations.AddField("arinvoice", "legacy_without_lines", models.BooleanField(default=False)),
        migrations.AlterField("arinvoice", "status", models.CharField(choices=(("draft", "Draft"), ("posted", "Posted"), ("partially_paid", "Partially paid"), ("paid", "Paid"), ("overdue", "Overdue"), ("cancelled", "Cancelled")), default="draft", max_length=20)),
        migrations.AddField("payment", "created_by", models.CharField(default=LEGACY_ACTOR, max_length=255)),
        migrations.AddField("payment", "status", models.CharField(choices=(("recorded", "Recorded"), ("voided", "Voided")), default="recorded", max_length=20)),
        migrations.AddField("payment", "voided_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("payment", "voided_by", models.CharField(blank=True, max_length=255, null=True)),
        migrations.AddField("payment", "void_reason", models.TextField(blank=True)),
        migrations.AddField("payment", "transition_history", models.JSONField(blank=True, default=list, editable=False)),
        migrations.AddField("payment", "idempotency_key", models.CharField(blank=True, max_length=255, null=True)),
        migrations.AddField("payment", "request_fingerprint", models.CharField(blank=True, max_length=64, null=True)),
        migrations.RunPython(backfill_v2_fields, noop_reverse),
        *[
            migrations.AlterField(model_name=model, name=name, field=models.CharField(max_length=255))
            for model in ("account", "postingperiod", "journalentry", "apinvoice", "arinvoice")
            for name in ("created_by", "updated_by")
        ],
        migrations.AlterField("payment", "created_by", models.CharField(max_length=255)),
        migrations.AlterField("account", "normal_balance", models.CharField(choices=(("debit", "Debit"), ("credit", "Credit")), default="debit", max_length=10)),
        migrations.AlterField("postingperiod", "fiscal_year", models.PositiveIntegerField()),
        migrations.AlterField("journalentry", "currency", models.CharField(default="USD", max_length=3)),
        migrations.AlterField("journalline", "line_number", models.PositiveIntegerField()),
        migrations.AlterField("journalline", "currency", models.CharField(max_length=3)),
        migrations.AlterField("payment", "idempotency_key", models.CharField(max_length=255)),
        migrations.AlterField("payment", "request_fingerprint", models.CharField(max_length=64)),
        migrations.CreateModel(
            name="APInvoiceLine",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant_id", models.UUIDField(db_index=True)),
                ("line_number", models.PositiveIntegerField()),
                ("description", models.CharField(max_length=500)),
                ("quantity", models.DecimalField(decimal_places=4, default=Decimal("1.0000"), max_digits=18)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=15)),
                ("tax_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=15)),
                ("line_total", models.DecimalField(decimal_places=2, max_digits=15)),
                ("cost_center", models.CharField(blank=True, max_length=100)),
                ("dimension_values", models.JSONField(blank=True, default=dict)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="accounting_finance.account")),
                ("invoice", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="accounting_finance.apinvoice")),
            ],
            options={"db_table": "accounting_ap_invoice_lines"},
        ),
        migrations.CreateModel(
            name="ARInvoiceLine",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant_id", models.UUIDField(db_index=True)),
                ("line_number", models.PositiveIntegerField()),
                ("description", models.CharField(max_length=500)),
                ("quantity", models.DecimalField(decimal_places=4, default=Decimal("1.0000"), max_digits=18)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=15)),
                ("tax_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=15)),
                ("line_total", models.DecimalField(decimal_places=2, max_digits=15)),
                ("cost_center", models.CharField(blank=True, max_length=100)),
                ("dimension_values", models.JSONField(blank=True, default=dict)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="accounting_finance.account")),
                ("invoice", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="accounting_finance.arinvoice")),
            ],
            options={"db_table": "accounting_ar_invoice_lines"},
        ),
    ]
