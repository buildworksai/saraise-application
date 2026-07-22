"""Harden the backfilled reconciliation domain with relational invariants."""

from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models
from django.db.models.functions import Lower, Upper

ZERO = Decimal("0.0000")


class Migration(migrations.Migration):
    dependencies = [("bank_reconciliation", "0002_domain_foundation")]

    operations = [
        migrations.AlterModelOptions(name="bankaccount", options={"ordering": ("bank_name", "account_name", "id")}),
        migrations.AlterModelOptions(name="bankstatement", options={"ordering": ("-period_end", "-id")}),
        migrations.AlterModelOptions(
            name="banktransaction", options={"ordering": ("transaction_date", "sequence_number", "id")}
        ),
        migrations.RemoveConstraint(model_name="bankaccount", name="unique_account_number_per_tenant"),
        migrations.RemoveIndex(model_name="bankaccount", name="bank_accoun_tenant__5b603c_idx"),
        migrations.RemoveIndex(model_name="bankstatement", name="bank_statem_tenant__26e7bc_idx"),
        migrations.RemoveIndex(model_name="bankstatement", name="bank_statem_tenant__2de13b_idx"),
        migrations.RemoveIndex(model_name="banktransaction", name="bank_transa_tenant__dec9d0_idx"),
        migrations.RemoveIndex(model_name="banktransaction", name="bank_transa_tenant__d71a26_idx"),
        migrations.RemoveIndex(model_name="banktransaction", name="bank_transa_tenant__6bd979_idx"),
        migrations.AlterField(
            model_name="bankaccount", name="created_at", field=models.DateTimeField(auto_now_add=True)
        ),
        migrations.AlterField(model_name="bankaccount", name="account_number", field=models.CharField(max_length=100)),
        migrations.AlterField(
            model_name="bankaccount",
            name="account_type",
            field=models.CharField(
                choices=[
                    ("checking", "Checking"),
                    ("savings", "Savings"),
                    ("credit", "Credit"),
                    ("cash", "Cash"),
                    ("other", "Other"),
                ],
                default="checking",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="bankaccount",
            name="ledger_account_id",
            field=models.UUIDField(blank=True, help_text="Soft reference to accounting_finance", null=True),
        ),
        migrations.AlterField(model_name="bankaccount", name="is_active", field=models.BooleanField(default=True)),
        migrations.AlterField(
            model_name="bankstatement", name="created_at", field=models.DateTimeField(auto_now_add=True)
        ),
        migrations.AlterField(model_name="bankstatement", name="statement_date", field=models.DateField()),
        migrations.AlterField(
            model_name="bankstatement",
            name="opening_balance",
            field=models.DecimalField(decimal_places=4, default=ZERO, max_digits=19),
        ),
        migrations.AlterField(
            model_name="bankstatement",
            name="closing_balance",
            field=models.DecimalField(decimal_places=4, default=ZERO, max_digits=19),
        ),
        migrations.AlterField(
            model_name="bankstatement", name="is_reconciled", field=models.BooleanField(default=False)
        ),
        migrations.AlterField(
            model_name="bankstatement",
            name="bank_account",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="statements",
                to="bank_reconciliation.bankaccount",
            ),
        ),
        migrations.AlterField(
            model_name="banktransaction", name="created_at", field=models.DateTimeField(auto_now_add=True)
        ),
        migrations.AlterField(model_name="banktransaction", name="transaction_date", field=models.DateField()),
        migrations.AlterField(
            model_name="banktransaction", name="amount", field=models.DecimalField(decimal_places=4, max_digits=19)
        ),
        migrations.AlterField(
            model_name="banktransaction",
            name="transaction_type",
            field=models.CharField(choices=[("debit", "Debit"), ("credit", "Credit")], max_length=20),
        ),
        migrations.AlterField(
            model_name="banktransaction", name="is_reconciled", field=models.BooleanField(default=False)
        ),
        migrations.AlterField(
            model_name="banktransaction",
            name="matched_payment_id",
            field=models.UUIDField(blank=True, help_text="External payment reference", null=True),
        ),
        migrations.AlterField(
            model_name="banktransaction",
            name="bank_statement",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="transactions",
                to="bank_reconciliation.bankstatement",
            ),
        ),
        migrations.AlterField(
            model_name="matchingrule",
            name="minimum_score",
            field=models.DecimalField(
                decimal_places=4,
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0")),
                    django.core.validators.MaxValueValidator(Decimal("1")),
                ],
            ),
        ),
        migrations.AddConstraint(
            model_name="bankaccount",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "account_number_hash"), name="br_account_tenant_hash_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="bankaccount",
            constraint=models.CheckConstraint(
                condition=models.Q(("currency", Upper("currency"))), name="br_account_currency_upper_ck"
            ),
        ),
        migrations.AddConstraint(
            model_name="bankaccount",
            constraint=models.CheckConstraint(
                condition=models.Q(("account_number_last4__regex", "^.{4}$")), name="br_account_last4_len_ck"
            ),
        ),
        migrations.AddIndex(
            model_name="bankaccount",
            index=models.Index(fields=["tenant_id", "is_active", "bank_name"], name="br_account_active_bank_ix"),
        ),
        migrations.AddIndex(
            model_name="bankaccount",
            index=models.Index(fields=["tenant_id", "ledger_account_id"], name="br_account_ledger_ix"),
        ),
        migrations.AddConstraint(
            model_name="bankstatementimport",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"), name="br_import_idempotency_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="bankstatementimport",
            constraint=models.UniqueConstraint(
                condition=models.Q(("source", "file")),
                fields=("tenant_id", "bank_account", "content_sha256"),
                name="br_import_file_hash_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="bankstatementimport",
            constraint=models.CheckConstraint(
                condition=models.Q(("rows_imported__lte", models.F("rows_received") - models.F("rows_rejected"))),
                name="br_import_row_counts_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="bankstatementimport",
            index=models.Index(fields=["tenant_id", "bank_account", "created_at"], name="br_import_account_date_ix"),
        ),
        migrations.AddIndex(
            model_name="bankstatementimport",
            index=models.Index(fields=["tenant_id", "status", "created_at"], name="br_import_status_date_ix"),
        ),
        migrations.AddConstraint(
            model_name="bankstatement",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "bank_account", "statement_reference"), name="br_statement_reference_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="bankstatement",
            constraint=models.CheckConstraint(
                condition=models.Q(("period_start__lte", models.F("period_end"))), name="br_statement_period_ck"
            ),
        ),
        migrations.AddConstraint(
            model_name="bankstatement",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("is_reconciled", True), ("status", "reconciled")),
                    models.Q(models.Q(("status", "reconciled"), _negated=True), ("is_reconciled", False)),
                    _connector="OR",
                ),
                name="br_statement_reconciled_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="bankstatement",
            index=models.Index(fields=["tenant_id", "bank_account", "period_end"], name="br_statement_account_date_ix"),
        ),
        migrations.AddIndex(
            model_name="bankstatement",
            index=models.Index(fields=["tenant_id", "status", "period_end"], name="br_statement_status_date_ix"),
        ),
        migrations.AddConstraint(
            model_name="banktransaction",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "bank_statement", "sequence_number"), name="br_transaction_sequence_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="banktransaction",
            constraint=models.UniqueConstraint(
                condition=models.Q(("external_id", ""), _negated=True),
                fields=("tenant_id", "bank_statement", "external_id"),
                name="br_transaction_external_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="banktransaction",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount", ZERO), _negated=True), name="br_transaction_amount_nonzero_ck"
            ),
        ),
        migrations.AddConstraint(
            model_name="banktransaction",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("amount__lt", 0), ("transaction_type", "debit")),
                    models.Q(("amount__gt", 0), ("transaction_type", "credit")),
                    _connector="OR",
                ),
                name="br_transaction_sign_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="banktransaction",
            index=models.Index(
                fields=["tenant_id", "bank_statement", "transaction_date"], name="br_transaction_statement_ix"
            ),
        ),
        migrations.AddIndex(
            model_name="banktransaction",
            index=models.Index(
                fields=["tenant_id", "match_status", "transaction_date"], name="br_transaction_match_ix"
            ),
        ),
        migrations.AddIndex(
            model_name="banktransaction",
            index=models.Index(fields=["tenant_id", "reference_number"], name="br_transaction_reference_ix"),
        ),
        migrations.AddConstraint(
            model_name="matchingrule",
            constraint=models.UniqueConstraint(Lower("name"), models.F("tenant_id"), name="br_rule_name_ci_uniq"),
        ),
        migrations.AddConstraint(
            model_name="matchingrule",
            constraint=models.UniqueConstraint(fields=("tenant_id", "priority"), name="br_rule_priority_uniq"),
        ),
        migrations.AddConstraint(
            model_name="matchingrule",
            constraint=models.CheckConstraint(
                condition=models.Q(("minimum_score__gte", 0), ("minimum_score__lte", 1)), name="br_rule_score_range_ck"
            ),
        ),
        migrations.AddConstraint(
            model_name="matchingrule",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("auto_confirm", False), ("rule_type", "extension"), ("minimum_score", 1), _connector="OR"
                ),
                name="br_rule_autoconfirm_score_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="matchingrule",
            index=models.Index(fields=["tenant_id", "is_active", "priority"], name="br_rule_active_priority_ix"),
        ),
        migrations.AddConstraint(
            model_name="reconciliationsession",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "bank_statement"), name="br_session_statement_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="reconciliationsession",
            constraint=models.CheckConstraint(
                condition=models.Q(("tolerance__gte", 0)), name="br_session_tolerance_ck"
            ),
        ),
        migrations.AddConstraint(
            model_name="reconciliationsession",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("finalized_at__isnull", False), ("finalized_by_id__isnull", False), ("status", "finalized")
                    ),
                    models.Q(
                        models.Q(("status", "finalized"), _negated=True),
                        ("finalized_at__isnull", True),
                        ("finalized_by_id__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="br_session_finalized_fields_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="reconciliationsession",
            index=models.Index(
                fields=["tenant_id", "bank_account", "reconciliation_date"], name="br_session_account_date_ix"
            ),
        ),
        migrations.AddIndex(
            model_name="reconciliationsession",
            index=models.Index(fields=["tenant_id", "status", "reconciliation_date"], name="br_session_status_date_ix"),
        ),
        migrations.AddConstraint(
            model_name="reconciliationmatch",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("score__isnull", True), models.Q(("score__gte", 0), ("score__lte", 1)), _connector="OR"
                ),
                name="br_match_score_range_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="reconciliationmatch",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("match_type", "auto"), _negated=True), ("score__isnull", False), _connector="OR"
                ),
                name="br_match_auto_score_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="reconciliationmatch",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status", "confirmed"), _negated=True),
                    models.Q(("matched_at__isnull", False), ("matched_by_id__isnull", False)),
                    _connector="OR",
                ),
                name="br_match_confirmed_evidence_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="reconciliationmatch",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status", "reversed"), _negated=True),
                    models.Q(
                        ("reversed_at__isnull", False),
                        ("reversed_by_id__isnull", False),
                        models.Q(("reversal_reason", ""), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="br_match_reversed_evidence_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="reconciliationmatch",
            index=models.Index(fields=["tenant_id", "reconciliation", "status"], name="br_match_session_status_ix"),
        ),
        migrations.AddIndex(
            model_name="reconciliationmatch",
            index=models.Index(fields=["tenant_id", "rule", "score"], name="br_match_rule_score_ix"),
        ),
        migrations.AddConstraint(
            model_name="reconciliationmatchline",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("bank_transaction__isnull", False), ("ledger_entry_id__isnull", True), ("side", "bank")),
                    models.Q(
                        ("bank_transaction__isnull", True), ("ledger_entry_id__isnull", False), ("side", "ledger")
                    ),
                    _connector="OR",
                ),
                name="br_match_line_side_reference_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="reconciliationmatchline",
            constraint=models.CheckConstraint(
                condition=models.Q(("allocated_amount", ZERO), _negated=True), name="br_match_line_amount_nonzero_ck"
            ),
        ),
        migrations.AddConstraint(
            model_name="reconciliationmatchline",
            constraint=models.CheckConstraint(
                condition=models.Q(("currency", Upper("currency"))), name="br_match_line_currency_upper_ck"
            ),
        ),
        migrations.AddConstraint(
            model_name="reconciliationmatchline",
            constraint=models.UniqueConstraint(
                condition=models.Q(("side", "bank")),
                fields=("tenant_id", "match", "bank_transaction"),
                name="br_match_line_bank_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="reconciliationmatchline",
            constraint=models.UniqueConstraint(
                condition=models.Q(("side", "ledger")),
                fields=("tenant_id", "match", "ledger_entry_id", "ledger_entry_type"),
                name="br_match_line_ledger_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="reconciliationmatchline",
            index=models.Index(fields=["tenant_id", "bank_transaction"], name="br_match_line_bank_ix"),
        ),
        migrations.AddIndex(
            model_name="reconciliationmatchline",
            index=models.Index(
                fields=["tenant_id", "ledger_entry_id", "ledger_entry_type"], name="br_match_line_ledger_ix"
            ),
        ),
    ]
