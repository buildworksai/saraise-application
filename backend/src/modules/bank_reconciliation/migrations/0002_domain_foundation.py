"""Build the complete reconciliation domain and preserve the 0001 data."""

from __future__ import annotations

import hashlib
import re
import uuid
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError

LEGACY_ACTOR_ID = uuid.UUID(int=0)
ZERO = Decimal("0.0000")


def _normalise(value):
    return re.sub(r"[\s-]+", "", value or "").upper()


def backfill_domain(apps, schema_editor):
    """Derive every required projection without replacing legacy identities."""
    del schema_editor
    Account = apps.get_model("bank_reconciliation", "BankAccount")
    Statement = apps.get_model("bank_reconciliation", "BankStatement")
    Transaction = apps.get_model("bank_reconciliation", "BankTransaction")

    seen_hashes = set()
    for account in Account.objects.order_by("tenant_id", "id").iterator():
        normalised = _normalise(account.account_number)
        if len(normalised) < 4:
            raise RuntimeError(
                f"Cannot migrate bank account {account.pk}: normalized identifier is shorter than four characters."
            )
        digest = hashlib.sha256(f"{account.tenant_id}:{normalised}".encode("utf-8")).hexdigest()
        identity = (account.tenant_id, digest)
        if identity in seen_hashes:
            raise RuntimeError(
                f"Cannot migrate bank account {account.pk}: normalized account identifier collides within its tenant."
            )
        seen_hashes.add(identity)
        account.account_number_hash = digest
        account.account_number_last4 = normalised[-4:]
        account.created_by_id = LEGACY_ACTOR_ID
        account.save(update_fields=("account_number_hash", "account_number_last4", "created_by_id"))

    for statement in Statement.objects.order_by("tenant_id", "id").iterator():
        transaction_total = ZERO
        transactions = Transaction.objects.filter(bank_statement_id=statement.pk).order_by(
            "transaction_date", "created_at", "id"
        )
        for sequence, transaction in enumerate(transactions.iterator(), start=1):
            if transaction.amount == ZERO:
                raise RuntimeError(f"Cannot migrate bank transaction {transaction.pk}: zero amounts are invalid.")
            transaction.sequence_number = sequence
            transaction.transaction_type = "credit" if transaction.amount > 0 else "debit"
            transaction.match_status = "matched" if transaction.is_reconciled else "unmatched"
            transaction.created_by_id = LEGACY_ACTOR_ID
            transaction.source_data = {}
            transaction.save(
                update_fields=("sequence_number", "transaction_type", "match_status", "created_by_id", "source_data")
            )
            transaction_total += transaction.amount

        statement.statement_reference = f"legacy-{statement.pk}"
        statement.period_start = statement.statement_date
        statement.period_end = statement.statement_date
        statement.transaction_total = transaction_total
        statement.calculated_closing_balance = statement.opening_balance + transaction_total
        statement.balance_variance = statement.closing_balance - statement.calculated_closing_balance
        statement.status = "reconciled" if statement.is_reconciled else "imported"
        statement.reconciled_at = statement.updated_at if statement.is_reconciled else None
        statement.created_by_id = LEGACY_ACTOR_ID
        statement.save(
            update_fields=(
                "statement_reference",
                "period_start",
                "period_end",
                "transaction_total",
                "calculated_closing_balance",
                "balance_variance",
                "status",
                "reconciled_at",
                "created_by_id",
            )
        )


def ensure_safe_reverse(apps, schema_editor):
    """Fail closed rather than discard post-0001 financial information."""
    del schema_editor
    for model_name in (
        "BankStatementImport",
        "MatchingRule",
        "ReconciliationSession",
        "ReconciliationMatch",
        "ReconciliationMatchLine",
    ):
        model = apps.get_model("bank_reconciliation", model_name)
        if model.objects.exists():
            raise IrreversibleError(f"Cannot reverse bank reconciliation domain: {model_name} contains financial data.")

    Account = apps.get_model("bank_reconciliation", "BankAccount")
    for account in Account.objects.iterator():
        normalised = _normalise(account.account_number)
        expected_hash = hashlib.sha256(f"{account.tenant_id}:{normalised}".encode("utf-8")).hexdigest()
        if (
            account.account_number_hash != expected_hash
            or account.account_number_last4 != normalised[-4:]
            or account.bank_identifier
            or account.opening_balance != ZERO
            or account.opening_balance_date is not None
            or account.archived_at is not None
            or account.created_by_id != LEGACY_ACTOR_ID
        ):
            raise IrreversibleError(
                f"Cannot reverse bank reconciliation domain: account {account.pk} has new domain data."
            )

    Statement = apps.get_model("bank_reconciliation", "BankStatement")
    for statement in Statement.objects.iterator():
        total = sum(
            (row.amount for row in statement.transactions.all()),
            ZERO,
        )
        expected_status = "reconciled" if statement.is_reconciled else "imported"
        if (
            statement.statement_import_id is not None
            or statement.statement_reference != f"legacy-{statement.pk}"
            or statement.period_start != statement.statement_date
            or statement.period_end != statement.statement_date
            or statement.transaction_total != total
            or statement.calculated_closing_balance != statement.opening_balance + total
            or statement.balance_variance != statement.closing_balance - statement.calculated_closing_balance
            or statement.status != expected_status
            or (statement.is_reconciled and statement.reconciled_at is None)
            or (not statement.is_reconciled and statement.reconciled_at is not None)
            or statement.created_by_id != LEGACY_ACTOR_ID
        ):
            raise IrreversibleError(
                f"Cannot reverse bank reconciliation domain: statement {statement.pk} has new domain data."
            )

    Transaction = apps.get_model("bank_reconciliation", "BankTransaction")
    expected_sequences = {}
    statement_ids = Transaction.objects.values_list("bank_statement_id", flat=True).distinct()
    for statement_id in statement_ids:
        ordered_ids = (
            Transaction.objects.filter(bank_statement_id=statement_id)
            .order_by("transaction_date", "created_at", "id")
            .values_list("id", flat=True)
        )
        expected_sequences.update({transaction_id: sequence for sequence, transaction_id in enumerate(ordered_ids, 1)})
    for transaction in Transaction.objects.iterator():
        expected_type = "credit" if transaction.amount > 0 else "debit"
        expected_status = "matched" if transaction.is_reconciled else "unmatched"
        if (
            transaction.external_id
            or transaction.value_date is not None
            or transaction.running_balance is not None
            or transaction.counterparty_name
            or transaction.counterparty_account_masked
            or transaction.source_data
            or transaction.match_status != expected_status
            or transaction.transaction_type != expected_type
            or transaction.sequence_number != expected_sequences[transaction.pk]
            or transaction.created_by_id != LEGACY_ACTOR_ID
        ):
            raise IrreversibleError(
                f"Cannot reverse bank reconciliation domain: transaction {transaction.pk} has new domain data."
            )


class Migration(migrations.Migration):
    dependencies = [("bank_reconciliation", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="BankStatementImport",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "source",
                    models.CharField(
                        choices=[("file", "File"), ("manual", "Manual"), ("bank_feed", "Bank feed")], max_length=20
                    ),
                ),
                (
                    "file_format",
                    models.CharField(
                        choices=[
                            ("csv", "CSV"),
                            ("ofx", "OFX"),
                            ("qif", "QIF"),
                            ("bai2", "BAI2"),
                            ("mt940", "MT940"),
                            ("camt053", "CAMT.053"),
                            ("manual", "Manual"),
                        ],
                        max_length=20,
                    ),
                ),
                ("source_document_id", models.UUIDField(blank=True, null=True)),
                ("source_filename", models.CharField(blank=True, max_length=255)),
                ("content_sha256", models.CharField(blank=True, max_length=64)),
                ("mapping", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("transition_history", models.JSONField(blank=True, default=list)),
                ("idempotency_key", models.CharField(max_length=128)),
                ("async_job_id", models.UUIDField(blank=True, null=True)),
                ("rows_received", models.PositiveIntegerField(default=0)),
                ("rows_imported", models.PositiveIntegerField(default=0)),
                ("rows_rejected", models.PositiveIntegerField(default=0)),
                ("error_code", models.CharField(blank=True, max_length=64)),
                ("error_detail", models.JSONField(blank=True, default=dict)),
                ("requested_by_id", models.UUIDField()),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "bank_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="statement_imports",
                        to="bank_reconciliation.bankaccount",
                    ),
                ),
            ],
            options={"db_table": "bank_statement_imports", "ordering": ("-created_at", "-id")},
        ),
        migrations.CreateModel(
            name="MatchingRule",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                (
                    "rule_type",
                    models.CharField(
                        choices=[
                            ("exact", "Exact"),
                            ("date_window", "Date window"),
                            ("reference", "Reference"),
                            ("amount_tolerance", "Amount tolerance"),
                            ("counterparty", "Counterparty"),
                            ("extension", "Extension"),
                        ],
                        max_length=20,
                    ),
                ),
                ("priority", models.PositiveSmallIntegerField()),
                ("configuration", models.JSONField(default=dict)),
                ("auto_confirm", models.BooleanField(default=False)),
                ("minimum_score", models.DecimalField(decimal_places=4, max_digits=5)),
                ("extension_key", models.CharField(blank=True, max_length=100)),
                ("is_active", models.BooleanField(default=True)),
                ("created_by_id", models.UUIDField()),
                ("updated_by_id", models.UUIDField()),
            ],
            options={"db_table": "bank_matching_rules", "ordering": ("priority", "name", "id")},
        ),
        migrations.CreateModel(
            name="ReconciliationSession",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reconciliation_date", models.DateField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("in_progress", "In progress"),
                            ("review", "Review"),
                            ("finalized", "Finalized"),
                            ("void", "Void"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("statement_balance", models.DecimalField(decimal_places=4, max_digits=19)),
                ("ledger_balance", models.DecimalField(decimal_places=4, max_digits=19)),
                ("matched_amount", models.DecimalField(decimal_places=4, default=ZERO, max_digits=19)),
                ("unmatched_amount", models.DecimalField(decimal_places=4, default=ZERO, max_digits=19)),
                ("difference", models.DecimalField(decimal_places=4, default=ZERO, max_digits=19)),
                ("tolerance", models.DecimalField(decimal_places=4, default=ZERO, max_digits=19)),
                ("notes", models.TextField(blank=True)),
                ("transition_history", models.JSONField(blank=True, default=list)),
                ("started_by_id", models.UUIDField()),
                ("reviewed_by_id", models.UUIDField(blank=True, null=True)),
                ("finalized_by_id", models.UUIDField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("finalized_at", models.DateTimeField(blank=True, null=True)),
                (
                    "bank_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reconciliation_sessions",
                        to="bank_reconciliation.bankaccount",
                    ),
                ),
                (
                    "bank_statement",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reconciliation",
                        to="bank_reconciliation.bankstatement",
                    ),
                ),
            ],
            options={"db_table": "bank_reconciliation_sessions", "ordering": ("-reconciliation_date", "-id")},
        ),
        migrations.CreateModel(
            name="ReconciliationMatch",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "match_type",
                    models.CharField(
                        choices=[
                            ("auto", "Automatic"),
                            ("manual", "Manual"),
                            ("one_to_many", "One to many"),
                            ("many_to_one", "Many to one"),
                            ("adjustment", "Adjustment"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("proposed", "Proposed"),
                            ("confirmed", "Confirmed"),
                            ("rejected", "Rejected"),
                            ("reversed", "Reversed"),
                        ],
                        default="proposed",
                        max_length=20,
                    ),
                ),
                ("score", models.DecimalField(blank=True, decimal_places=4, max_digits=5, null=True)),
                ("explanation", models.JSONField(blank=True, default=dict)),
                ("matched_at", models.DateTimeField(blank=True, null=True)),
                ("matched_by_id", models.UUIDField(blank=True, null=True)),
                ("reversed_at", models.DateTimeField(blank=True, null=True)),
                ("reversed_by_id", models.UUIDField(blank=True, null=True)),
                ("reversal_reason", models.CharField(blank=True, max_length=500)),
                (
                    "reconciliation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="matches",
                        to="bank_reconciliation.reconciliationsession",
                    ),
                ),
                (
                    "rule",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="matches",
                        to="bank_reconciliation.matchingrule",
                    ),
                ),
            ],
            options={"db_table": "bank_reconciliation_matches", "ordering": ("created_at", "id")},
        ),
        migrations.CreateModel(
            name="ReconciliationMatchLine",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("side", models.CharField(choices=[("bank", "Bank"), ("ledger", "Ledger")], max_length=10)),
                ("ledger_entry_id", models.UUIDField(blank=True, null=True)),
                (
                    "ledger_entry_type",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("payment", "Payment"),
                            ("journal_line", "Journal line"),
                            ("deposit", "Deposit"),
                            ("other", "Other"),
                        ],
                        max_length=40,
                    ),
                ),
                ("allocated_amount", models.DecimalField(decimal_places=4, max_digits=19)),
                ("currency", models.CharField(max_length=3)),
                (
                    "bank_transaction",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="match_lines",
                        to="bank_reconciliation.banktransaction",
                    ),
                ),
                (
                    "match",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="bank_reconciliation.reconciliationmatch",
                    ),
                ),
            ],
            options={"db_table": "bank_reconciliation_match_lines", "ordering": ("side", "created_at", "id")},
        ),
        migrations.AddField(
            model_name="bankaccount",
            name="account_number_hash",
            field=models.CharField(max_length=64, null=True, editable=False),
        ),
        migrations.AddField(
            model_name="bankaccount",
            name="account_number_last4",
            field=models.CharField(max_length=4, null=True, editable=False),
        ),
        migrations.AddField(
            model_name="bankaccount", name="bank_identifier", field=models.CharField(blank=True, max_length=34)
        ),
        migrations.AddField(
            model_name="bankaccount",
            name="opening_balance",
            field=models.DecimalField(decimal_places=4, default=ZERO, max_digits=19),
        ),
        migrations.AddField(
            model_name="bankaccount", name="opening_balance_date", field=models.DateField(blank=True, null=True)
        ),
        migrations.AddField(
            model_name="bankaccount", name="archived_at", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.AddField(model_name="bankaccount", name="created_by_id", field=models.UUIDField(null=True)),
        migrations.AddField(
            model_name="bankstatement",
            name="statement_import",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="statement",
                to="bank_reconciliation.bankstatementimport",
            ),
        ),
        migrations.AddField(
            model_name="bankstatement", name="statement_reference", field=models.CharField(max_length=100, null=True)
        ),
        migrations.AddField(model_name="bankstatement", name="period_start", field=models.DateField(null=True)),
        migrations.AddField(model_name="bankstatement", name="period_end", field=models.DateField(null=True)),
        migrations.AddField(
            model_name="bankstatement",
            name="transaction_total",
            field=models.DecimalField(decimal_places=4, default=ZERO, max_digits=19),
        ),
        migrations.AddField(
            model_name="bankstatement",
            name="calculated_closing_balance",
            field=models.DecimalField(decimal_places=4, default=ZERO, max_digits=19),
        ),
        migrations.AddField(
            model_name="bankstatement",
            name="balance_variance",
            field=models.DecimalField(decimal_places=4, default=ZERO, max_digits=19),
        ),
        migrations.AddField(
            model_name="bankstatement",
            name="status",
            field=models.CharField(
                choices=[
                    ("imported", "Imported"),
                    ("reconciling", "Reconciling"),
                    ("reconciled", "Reconciled"),
                    ("void", "Void"),
                ],
                default="imported",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="bankstatement", name="reconciled_at", field=models.DateTimeField(blank=True, null=True)
        ),
        migrations.AddField(model_name="bankstatement", name="created_by_id", field=models.UUIDField(null=True)),
        migrations.AddField(
            model_name="banktransaction", name="sequence_number", field=models.PositiveIntegerField(null=True)
        ),
        migrations.AddField(
            model_name="banktransaction", name="external_id", field=models.CharField(blank=True, max_length=128)
        ),
        migrations.AddField(
            model_name="banktransaction", name="value_date", field=models.DateField(blank=True, null=True)
        ),
        migrations.AddField(
            model_name="banktransaction",
            name="running_balance",
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=19, null=True),
        ),
        migrations.AddField(
            model_name="banktransaction", name="counterparty_name", field=models.CharField(blank=True, max_length=255)
        ),
        migrations.AddField(
            model_name="banktransaction",
            name="counterparty_account_masked",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="banktransaction",
            name="match_status",
            field=models.CharField(
                choices=[
                    ("unmatched", "Unmatched"),
                    ("proposed", "Proposed"),
                    ("matched", "Matched"),
                    ("excluded", "Excluded"),
                ],
                default="unmatched",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="banktransaction", name="source_data", field=models.JSONField(blank=True, default=dict)
        ),
        migrations.AddField(model_name="banktransaction", name="created_by_id", field=models.UUIDField(null=True)),
        migrations.RunPython(backfill_domain, ensure_safe_reverse),
        migrations.AlterField(
            model_name="bankaccount", name="account_number_hash", field=models.CharField(editable=False, max_length=64)
        ),
        migrations.AlterField(
            model_name="bankaccount", name="account_number_last4", field=models.CharField(editable=False, max_length=4)
        ),
        migrations.AlterField(model_name="bankaccount", name="created_by_id", field=models.UUIDField()),
        migrations.AlterField(
            model_name="bankstatement", name="statement_reference", field=models.CharField(max_length=100)
        ),
        migrations.AlterField(model_name="bankstatement", name="period_start", field=models.DateField()),
        migrations.AlterField(model_name="bankstatement", name="period_end", field=models.DateField()),
        migrations.AlterField(model_name="bankstatement", name="created_by_id", field=models.UUIDField()),
        migrations.AlterField(
            model_name="banktransaction", name="sequence_number", field=models.PositiveIntegerField()
        ),
        migrations.AlterField(model_name="banktransaction", name="created_by_id", field=models.UUIDField()),
    ]
