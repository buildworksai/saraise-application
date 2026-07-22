"""Validate legacy data, then enforce Accounting v2 invariants and indexes."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations, models
from django.db.models import F, Q


INDEXES = {
    "Account": (
        models.Index(fields=("tenant_id", "code"), name="acct_account_code_idx"),
        models.Index(fields=("tenant_id", "account_type", "is_active"), name="acct_account_type_idx"),
        models.Index(fields=("tenant_id", "parent", "code"), name="acct_account_parent_idx"),
        models.Index(fields=("tenant_id", "is_deleted", "code"), name="acct_account_live_idx"),
    ),
    "PostingPeriod": (
        models.Index(fields=("tenant_id", "fiscal_year", "start_date"), name="acct_period_fy_idx"),
        models.Index(fields=("tenant_id", "status", "start_date"), name="acct_period_status_idx"),
        models.Index(fields=("tenant_id", "start_date", "end_date"), name="acct_period_dates_idx"),
    ),
    "JournalEntry": (
        models.Index(fields=("tenant_id", "posting_date", "entry_number"), name="acct_je_date_num_idx"),
        models.Index(fields=("tenant_id", "status", "posting_date"), name="acct_je_status_date_idx"),
        models.Index(fields=("tenant_id", "posting_period", "status"), name="acct_je_period_idx"),
        models.Index(fields=("tenant_id", "source_module", "source_reference"), name="acct_je_source_idx"),
    ),
    "JournalLine": (
        models.Index(fields=("tenant_id", "journal_entry", "line_number"), name="acct_jl_entry_line_idx"),
        models.Index(fields=("tenant_id", "account", "journal_entry"), name="acct_jl_account_idx"),
        models.Index(fields=("tenant_id", "cost_center"), name="acct_jl_cost_center_idx"),
    ),
    "APInvoice": (
        models.Index(fields=("tenant_id", "supplier_id", "invoice_number"), name="acct_ap_supplier_idx"),
        models.Index(fields=("tenant_id", "status", "due_date"), name="acct_ap_status_due_idx"),
        models.Index(fields=("tenant_id", "invoice_date"), name="acct_ap_date_idx"),
        models.Index(fields=("tenant_id", "journal_entry"), name="acct_ap_journal_idx"),
    ),
    "APInvoiceLine": (
        models.Index(fields=("tenant_id", "account"), name="acct_apl_account_idx"),
        models.Index(fields=("tenant_id", "invoice"), name="acct_apl_invoice_idx"),
    ),
    "ARInvoice": (
        models.Index(fields=("tenant_id", "customer_id", "invoice_number"), name="acct_ar_customer_idx"),
        models.Index(fields=("tenant_id", "status", "due_date"), name="acct_ar_status_due_idx"),
        models.Index(fields=("tenant_id", "invoice_date"), name="acct_ar_date_idx"),
        models.Index(fields=("tenant_id", "journal_entry"), name="acct_ar_journal_idx"),
    ),
    "ARInvoiceLine": (
        models.Index(fields=("tenant_id", "account"), name="acct_arl_account_idx"),
        models.Index(fields=("tenant_id", "invoice"), name="acct_arl_invoice_idx"),
    ),
    "Payment": (
        models.Index(fields=("tenant_id", "payment_date"), name="acct_payment_date_idx"),
        models.Index(fields=("tenant_id", "ap_invoice"), name="acct_payment_ap_idx"),
        models.Index(fields=("tenant_id", "ar_invoice"), name="acct_payment_ar_idx"),
        models.Index(fields=("tenant_id", "reference_number"), name="acct_payment_ref_idx"),
    ),
}


CONSTRAINTS = {
    "account": (
        models.UniqueConstraint(fields=("tenant_id", "code"), condition=Q(is_deleted=False), name="acct_account_code_uq"),
        models.CheckConstraint(condition=Q(parent__isnull=True) | ~Q(parent=F("id")), name="acct_account_parent_ck"),
        models.CheckConstraint(condition=Q(normal_balance__in=("debit", "credit")), name="acct_account_balance_ck"),
        models.UniqueConstraint(fields=("tenant_id", "creation_idempotency_key"), condition=Q(creation_idempotency_key__isnull=False), name="acct_account_idem_uq"),
        models.CheckConstraint(condition=(Q(is_deleted=False, deleted_at__isnull=True) | Q(is_deleted=True, deleted_at__isnull=False)), name="acct_account_softdel_ck"),
    ),
    "postingperiod": (
        models.UniqueConstraint(fields=("tenant_id", "period_name", "fiscal_year"), name="acct_period_name_uq"),
        models.CheckConstraint(condition=Q(start_date__lte=F("end_date")), name="acct_period_dates_ck"),
        models.UniqueConstraint(fields=("tenant_id", "creation_idempotency_key"), condition=Q(creation_idempotency_key__isnull=False), name="acct_period_idem_uq"),
    ),
    "journalentry": (
        models.UniqueConstraint(fields=("tenant_id", "entry_number"), condition=Q(is_deleted=False), name="acct_je_number_uq"),
        models.UniqueConstraint(fields=("tenant_id", "source_module", "source_idempotency_key"), condition=Q(source_idempotency_key__isnull=False), name="acct_je_source_idem_uq"),
        models.CheckConstraint(condition=Q(debit_total__gte=0), name="acct_je_debit_nonneg_ck"),
        models.CheckConstraint(condition=Q(credit_total__gte=0), name="acct_je_credit_nonneg_ck"),
        models.CheckConstraint(condition=Q(reversed_entry__isnull=True) | ~Q(reversed_entry=F("id")), name="acct_je_reversal_self_ck"),
        models.UniqueConstraint(fields=("tenant_id", "creation_idempotency_key"), condition=Q(creation_idempotency_key__isnull=False), name="acct_je_create_idem_uq"),
        models.CheckConstraint(condition=(Q(is_deleted=False, deleted_at__isnull=True) | Q(is_deleted=True, deleted_at__isnull=False)), name="acct_je_softdel_ck"),
    ),
    "journalline": (
        models.UniqueConstraint(fields=("tenant_id", "journal_entry", "line_number"), name="acct_jl_line_uq"),
        models.CheckConstraint(condition=(Q(debit_amount__gt=0, credit_amount=0) | Q(credit_amount__gt=0, debit_amount=0)), name="acct_jl_debit_credit_ck"),
        models.CheckConstraint(condition=Q(base_debit_amount__gte=0), name="acct_jl_base_debit_ck"),
        models.CheckConstraint(condition=Q(base_credit_amount__gte=0), name="acct_jl_base_credit_ck"),
        models.CheckConstraint(condition=Q(exchange_rate__gt=0), name="acct_jl_rate_ck"),
    ),
    "apinvoice": (
        models.UniqueConstraint(fields=("tenant_id", "supplier_id", "invoice_number"), condition=Q(is_deleted=False), name="acct_ap_invoice_uq"),
        models.CheckConstraint(condition=Q(invoice_date__lte=F("due_date")), name="acct_ap_dates_ck"),
        models.CheckConstraint(condition=Q(amount__gte=0), name="acct_ap_amount_ck"),
        models.CheckConstraint(condition=Q(tax_amount__gte=0), name="acct_ap_tax_ck"),
        models.CheckConstraint(condition=Q(total_amount=F("amount") + F("tax_amount")), name="acct_ap_total_ck"),
        models.CheckConstraint(condition=Q(paid_amount__gte=0, paid_amount__lte=F("total_amount")), name="acct_ap_paid_ck"),
        models.UniqueConstraint(fields=("tenant_id", "creation_idempotency_key"), condition=Q(creation_idempotency_key__isnull=False), name="acct_ap_create_idem_uq"),
        models.CheckConstraint(condition=(Q(is_deleted=False, deleted_at__isnull=True) | Q(is_deleted=True, deleted_at__isnull=False)), name="acct_ap_softdel_ck"),
    ),
    "apinvoiceline": (
        models.UniqueConstraint(fields=("tenant_id", "invoice", "line_number"), name="acct_apl_line_uq"),
        models.CheckConstraint(condition=Q(quantity__gt=0), name="acct_apl_qty_ck"),
        models.CheckConstraint(condition=Q(unit_price__gte=0), name="acct_apl_price_ck"),
        models.CheckConstraint(condition=Q(tax_amount__gte=0), name="acct_apl_tax_ck"),
        models.CheckConstraint(condition=Q(line_total__gte=0), name="acct_apl_total_ck"),
    ),
    "arinvoice": (
        models.UniqueConstraint(fields=("tenant_id", "customer_id", "invoice_number"), condition=Q(is_deleted=False), name="acct_ar_invoice_uq"),
        models.CheckConstraint(condition=Q(invoice_date__lte=F("due_date")), name="acct_ar_dates_ck"),
        models.CheckConstraint(condition=Q(amount__gte=0), name="acct_ar_amount_ck"),
        models.CheckConstraint(condition=Q(tax_amount__gte=0), name="acct_ar_tax_ck"),
        models.CheckConstraint(condition=Q(total_amount=F("amount") + F("tax_amount")), name="acct_ar_total_ck"),
        models.CheckConstraint(condition=Q(paid_amount__gte=0, paid_amount__lte=F("total_amount")), name="acct_ar_paid_ck"),
        models.UniqueConstraint(fields=("tenant_id", "creation_idempotency_key"), condition=Q(creation_idempotency_key__isnull=False), name="acct_ar_create_idem_uq"),
        models.CheckConstraint(condition=(Q(is_deleted=False, deleted_at__isnull=True) | Q(is_deleted=True, deleted_at__isnull=False)), name="acct_ar_softdel_ck"),
    ),
    "arinvoiceline": (
        models.UniqueConstraint(fields=("tenant_id", "invoice", "line_number"), name="acct_arl_line_uq"),
        models.CheckConstraint(condition=Q(quantity__gt=0), name="acct_arl_qty_ck"),
        models.CheckConstraint(condition=Q(unit_price__gte=0), name="acct_arl_price_ck"),
        models.CheckConstraint(condition=Q(tax_amount__gte=0), name="acct_arl_tax_ck"),
        models.CheckConstraint(condition=Q(line_total__gte=0), name="acct_arl_total_ck"),
    ),
    "payment": (
        models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="acct_payment_idem_uq"),
        models.CheckConstraint(condition=Q(amount__gt=0), name="acct_payment_amount_ck"),
        models.CheckConstraint(condition=(Q(ap_invoice__isnull=False, ar_invoice__isnull=True) | Q(ap_invoice__isnull=True, ar_invoice__isnull=False)), name="acct_payment_invoice_ck"),
    ),
}


def validate_rows(apps, schema_editor) -> None:
    del schema_editor
    Account = apps.get_model("accounting_finance", "Account")
    PostingPeriod = apps.get_model("accounting_finance", "PostingPeriod")
    JournalEntry = apps.get_model("accounting_finance", "JournalEntry")
    JournalLine = apps.get_model("accounting_finance", "JournalLine")
    APInvoice = apps.get_model("accounting_finance", "APInvoice")
    ARInvoice = apps.get_model("accounting_finance", "ARInvoice")
    Payment = apps.get_model("accounting_finance", "Payment")

    failures: list[str] = []
    for account in Account.objects.all().iterator():
        if account.parent_id == account.id or account.normal_balance not in {"debit", "credit"}:
            failures.append(f"account:{account.id}")
    periods_by_tenant: dict[object, list[object]] = {}
    for period in PostingPeriod.objects.order_by("tenant_id", "start_date", "end_date").iterator():
        if period.start_date > period.end_date:
            failures.append(f"period:{period.id}:dates")
        periods_by_tenant.setdefault(period.tenant_id, []).append(period)
    for periods in periods_by_tenant.values():
        for previous, current in zip(periods, periods[1:]):
            if current.start_date <= previous.end_date:
                failures.append(f"period:{current.id}:overlaps:{previous.id}")
    for entry in JournalEntry.objects.all().iterator():
        if entry.debit_total < 0 or entry.credit_total < 0 or entry.reversed_entry_id == entry.id:
            failures.append(f"journal:{entry.id}")
    for line in JournalLine.objects.all().iterator():
        rounded_debit = (line.debit_amount * line.exchange_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rounded_credit = (line.credit_amount * line.exchange_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if ((line.debit_amount > 0) == (line.credit_amount > 0)) or line.exchange_rate <= 0:
            failures.append(f"journal-line:{line.id}:amount")
        if line.base_debit_amount != rounded_debit or line.base_credit_amount != rounded_credit:
            failures.append(f"journal-line:{line.id}:base")
    for label, model in (("ap", APInvoice), ("ar", ARInvoice)):
        for invoice in model.objects.all().iterator():
            if invoice.invoice_date > invoice.due_date or min(invoice.amount, invoice.tax_amount, invoice.total_amount, invoice.paid_amount) < 0:
                failures.append(f"{label}:{invoice.id}:amount-or-date")
            if invoice.total_amount != invoice.amount + invoice.tax_amount or invoice.paid_amount > invoice.total_amount:
                failures.append(f"{label}:{invoice.id}:total")
    for payment in Payment.objects.select_related("ap_invoice", "ar_invoice").all().iterator():
        invoice = payment.ap_invoice or payment.ar_invoice
        if payment.amount <= 0 or invoice is None or payment.currency != invoice.currency or payment.payment_date < invoice.invoice_date:
            failures.append(f"payment:{payment.id}")
    if failures:
        raise RuntimeError("Accounting v2 constraints rejected records: " + ", ".join(failures[:50]))


def add_indexes(apps, schema_editor) -> None:
    for model_name, indexes in INDEXES.items():
        model = apps.get_model("accounting_finance", model_name)
        for index in indexes:
            if schema_editor.connection.vendor == "postgresql":
                sql = str(index.create_sql(model, schema_editor)).replace("CREATE INDEX", "CREATE INDEX CONCURRENTLY", 1)
                schema_editor.execute(sql)
            else:
                schema_editor.add_index(model, index)


def remove_indexes(apps, schema_editor) -> None:
    for model_name, indexes in reversed(tuple(INDEXES.items())):
        model = apps.get_model("accounting_finance", model_name)
        for index in reversed(indexes):
            if schema_editor.connection.vendor == "postgresql":
                schema_editor.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{index.name}"')
            else:
                schema_editor.remove_index(model, index)


def add_period_exclusion(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    schema_editor.execute(
        "ALTER TABLE accounting_posting_periods ADD CONSTRAINT acct_period_no_overlap_excl "
        "EXCLUDE USING gist (tenant_id WITH =, daterange(start_date, end_date, '[]') WITH &&)"
    )


def remove_period_exclusion(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "ALTER TABLE accounting_posting_periods DROP CONSTRAINT IF EXISTS acct_period_no_overlap_excl"
        )


LEGACY_INDEXES = (
    ("account", "accounting__tenant__6dd755_idx"), ("account", "accounting__tenant__edc503_idx"),
    ("postingperiod", "accounting__tenant__4a985d_idx"), ("postingperiod", "accounting__tenant__bc39fe_idx"),
    ("journalentry", "accounting__tenant__97db4c_idx"), ("journalentry", "accounting__tenant__634dd6_idx"), ("journalentry", "accounting__tenant__ac9110_idx"),
    ("journalline", "accounting__tenant__76a163_idx"), ("journalline", "accounting__tenant__a1a834_idx"),
    ("apinvoice", "accounting__tenant__600de2_idx"), ("apinvoice", "accounting__tenant__d5d212_idx"), ("apinvoice", "accounting__tenant__6dfb4e_idx"),
    ("arinvoice", "accounting__tenant__fdb465_idx"), ("arinvoice", "accounting__tenant__c79f51_idx"), ("arinvoice", "accounting__tenant__47a03f_idx"),
    ("payment", "accounting__tenant__ba3dec_idx"), ("payment", "accounting__tenant__717f13_idx"), ("payment", "accounting__tenant__f30497_idx"),
)


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("accounting_finance", "0002_v2_additive_schema")]

    operations = [
        migrations.RunPython(validate_rows, migrations.RunPython.noop),
        migrations.RemoveConstraint("account", "unique_account_code_per_tenant"),
        migrations.RemoveConstraint("postingperiod", "unique_period_per_tenant"),
        migrations.RemoveConstraint("journalentry", "accounting_unique_entry_number_per_tenant"),
        migrations.RemoveConstraint("apinvoice", "unique_ap_invoice_per_tenant"),
        migrations.RemoveConstraint("arinvoice", "unique_ar_invoice_number_per_tenant"),
        *[migrations.RemoveIndex(model_name=model, name=name) for model, name in LEGACY_INDEXES],
        migrations.AlterField("account", "created_at", models.DateTimeField(auto_now_add=True)),
        migrations.AlterField("account", "code", models.CharField(max_length=50)),
        migrations.AlterField("account", "name", models.CharField(max_length=255)),
        migrations.AlterField("account", "account_type", models.CharField(choices=(("asset", "Asset"), ("liability", "Liability"), ("equity", "Equity"), ("revenue", "Revenue"), ("expense", "Expense")), max_length=20)),
        migrations.AlterField("account", "is_active", models.BooleanField(default=True)),
        migrations.AlterField("postingperiod", "created_at", models.DateTimeField(auto_now_add=True)),
        migrations.AlterField("postingperiod", "period_name", models.CharField(max_length=50)),
        migrations.AlterField("postingperiod", "start_date", models.DateField()),
        migrations.AlterField("postingperiod", "end_date", models.DateField()),
        migrations.AlterField("journalentry", "created_at", models.DateTimeField(auto_now_add=True)),
        migrations.AlterField("journalentry", "entry_number", models.CharField(max_length=50)),
        migrations.AlterField("journalentry", "posting_date", models.DateField()),
        migrations.AlterField("journalline", "created_at", models.DateTimeField(auto_now_add=True)),
        migrations.AlterField("journalline", "debit_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=15)),
        migrations.AlterField("journalline", "credit_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=15)),
        migrations.AlterField("apinvoice", "created_at", models.DateTimeField(auto_now_add=True)),
        migrations.AlterField("apinvoice", "invoice_number", models.CharField(max_length=100)),
        migrations.AlterField("apinvoice", "supplier_id", models.UUIDField()),
        migrations.AlterField("apinvoice", "invoice_date", models.DateField()),
        migrations.AlterField("apinvoice", "due_date", models.DateField()),
        migrations.AlterField("apinvoice", "amount", models.DecimalField(decimal_places=2, max_digits=15)),
        migrations.AlterField("apinvoice", "total_amount", models.DecimalField(decimal_places=2, max_digits=15)),
        migrations.AlterField("arinvoice", "created_at", models.DateTimeField(auto_now_add=True)),
        migrations.AlterField("arinvoice", "invoice_number", models.CharField(max_length=100)),
        migrations.AlterField("arinvoice", "customer_id", models.UUIDField()),
        migrations.AlterField("arinvoice", "invoice_date", models.DateField()),
        migrations.AlterField("arinvoice", "due_date", models.DateField()),
        migrations.AlterField("arinvoice", "amount", models.DecimalField(decimal_places=2, max_digits=15)),
        migrations.AlterField("arinvoice", "total_amount", models.DecimalField(decimal_places=2, max_digits=15)),
        migrations.AlterField("payment", "created_at", models.DateTimeField(auto_now_add=True)),
        migrations.AlterField("payment", "payment_date", models.DateField()),
        migrations.AlterField("payment", "amount", models.DecimalField(decimal_places=2, max_digits=15)),
        *[
            migrations.AddConstraint(model_name=model_name, constraint=constraint)
            for model_name, constraints in CONSTRAINTS.items()
            for constraint in constraints
        ],
        migrations.RunPython(add_period_exclusion, remove_period_exclusion),
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(add_indexes, remove_indexes)],
            state_operations=[
                migrations.AddIndex(model_name=model_name.lower(), index=index)
                for model_name, indexes in INDEXES.items()
                for index in indexes
            ],
        ),
    ]
