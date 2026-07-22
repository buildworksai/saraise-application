"""Tenant-owned bank-reconciliation domain models.

The models deliberately contain structural invariants and harmless canonicalisation;
aggregate transitions and all externally visible mutations belong in ``services.py``.
Raw account identifiers must never be rendered by a model or an ordinary serializer.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from decimal import Decimal
from pathlib import PurePath
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower, Upper

from src.core.tenancy import TenantScopedModel, TimestampedModel

MONEY_ZERO = Decimal("0.0000")


def normalize_account_number(value: str) -> str:
    """Return the stable comparison form used for tenant-local identity."""
    return re.sub(r"[\s-]+", "", value or "").upper()


def account_number_digest(tenant_id: uuid.UUID, value: str) -> str:
    """Hash an account identity with its tenant namespace."""
    normalized = normalize_account_number(value)
    return hashlib.sha256(f"{tenant_id}:{normalized}".encode("utf-8")).hexdigest()


def _trimmed(value: str) -> str:
    return value.strip() if value else ""


class BankAccount(TenantScopedModel, TimestampedModel):
    """A tenant-owned bank, credit, or cash account."""

    class AccountType(models.TextChoices):
        CHECKING = "checking", "Checking"
        SAVINGS = "savings", "Savings"
        CREDIT = "credit", "Credit"
        CASH = "cash", "Cash"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account_number = models.CharField(max_length=100)
    account_number_hash = models.CharField(max_length=64, editable=False)
    account_number_last4 = models.CharField(max_length=4, editable=False)
    bank_name = models.CharField(max_length=255)
    account_name = models.CharField(max_length=255)
    account_type = models.CharField(max_length=20, choices=AccountType.choices, default=AccountType.CHECKING)
    currency = models.CharField(max_length=3, default="USD")
    bank_identifier = models.CharField(max_length=34, blank=True)
    ledger_account_id = models.UUIDField(null=True, blank=True, help_text="Soft reference to accounting_finance")
    opening_balance = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    opening_balance_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_by_id = models.UUIDField()

    class Meta:
        db_table = "bank_accounts"
        ordering = ("bank_name", "account_name", "id")
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "account_number_hash"), name="br_account_tenant_hash_uniq"),
            models.CheckConstraint(condition=models.Q(currency=Upper("currency")), name="br_account_currency_upper_ck"),
            models.CheckConstraint(
                condition=models.Q(account_number_last4__regex=r"^.{4}$"),
                name="br_account_last4_len_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "is_active", "bank_name"), name="br_account_active_bank_ix"),
            models.Index(fields=("tenant_id", "ledger_account_id"), name="br_account_ledger_ix"),
        ]

    @property
    def masked_account_number(self) -> str:
        """Return the only account-number representation safe for routine display."""
        return f"••••{self.account_number_last4}"

    def clean(self) -> None:
        super().clean()
        self.bank_name = _trimmed(self.bank_name)
        self.account_name = _trimmed(self.account_name)
        self.currency = _trimmed(self.currency).upper()
        self.bank_identifier = _trimmed(self.bank_identifier)
        normalized = normalize_account_number(self.account_number)
        if len(normalized) >= 4:
            # Derive before ``full_clean`` evaluates database constraints; save
            # repeats this harmlessly so direct ORM writes remain canonical.
            self.account_number_hash = account_number_digest(self.tenant_id, normalized)
            self.account_number_last4 = normalized[-4:]
        errors: dict[str, str] = {}
        if len(normalized) < 4:
            errors["account_number"] = "Account number must contain at least four characters."
        if not self.bank_name:
            errors["bank_name"] = "Bank name must not be blank."
        if not self.account_name:
            errors["account_name"] = "Account name must not be blank."
        if self.opening_balance != MONEY_ZERO and self.opening_balance_date is None:
            errors["opening_balance_date"] = "Opening balance date is required for a non-zero opening balance."
        if self.archived_at is not None and self.is_active:
            errors["is_active"] = "An archived account cannot remain active."
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        normalized = normalize_account_number(self.account_number)
        self.account_number_hash = account_number_digest(self.tenant_id, normalized)
        self.account_number_last4 = normalized[-4:]
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.bank_name} - {self.masked_account_number}"


class BankStatementImport(TenantScopedModel, TimestampedModel):
    """Durable and idempotent evidence of a statement-ingestion request."""

    class Source(models.TextChoices):
        FILE = "file", "File"
        MANUAL = "manual", "Manual"
        BANK_FEED = "bank_feed", "Bank feed"

    class FileFormat(models.TextChoices):
        CSV = "csv", "CSV"
        OFX = "ofx", "OFX"
        QIF = "qif", "QIF"
        BAI2 = "bai2", "BAI2"
        MT940 = "mt940", "MT940"
        CAMT053 = "camt053", "CAMT.053"
        MANUAL = "manual", "Manual"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="statement_imports")
    source = models.CharField(max_length=20, choices=Source.choices)
    file_format = models.CharField(max_length=20, choices=FileFormat.choices)
    source_document_id = models.UUIDField(null=True, blank=True)
    source_filename = models.CharField(max_length=255, blank=True)
    content_sha256 = models.CharField(max_length=64, blank=True)
    mapping = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    transition_history = models.JSONField(default=list, blank=True)
    idempotency_key = models.CharField(max_length=128)
    async_job_id = models.UUIDField(null=True, blank=True)
    rows_received = models.PositiveIntegerField(default=0)
    rows_imported = models.PositiveIntegerField(default=0)
    rows_rejected = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True)
    error_detail = models.JSONField(default=dict, blank=True)
    requested_by_id = models.UUIDField()
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "bank_statement_imports"
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="br_import_idempotency_uniq"),
            models.UniqueConstraint(
                fields=("tenant_id", "bank_account", "content_sha256"),
                condition=models.Q(source="file"),
                name="br_import_file_hash_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(rows_imported__lte=models.F("rows_received") - models.F("rows_rejected")),
                name="br_import_row_counts_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "bank_account", "created_at"), name="br_import_account_date_ix"),
            models.Index(fields=("tenant_id", "status", "created_at"), name="br_import_status_date_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        # Treat both POSIX and Windows separators as path material regardless of
        # the application host, and persist only a display-safe basename.
        self.source_filename = PurePath(self.source_filename.replace("\\", "/")).name if self.source_filename else ""
        self.idempotency_key = _trimmed(self.idempotency_key)
        self.content_sha256 = _trimmed(self.content_sha256).lower()
        errors: dict[str, str] = {}
        if self.bank_account_id and self.bank_account.tenant_id != self.tenant_id:
            errors["bank_account"] = "Bank account must belong to this tenant."
        if not self.idempotency_key:
            errors["idempotency_key"] = "Idempotency key must not be blank."
        if self.source == self.Source.FILE:
            if not self.source_document_id:
                errors["source_document_id"] = "Source document is required for file imports."
            if not re.fullmatch(r"[0-9a-f]{64}", self.content_sha256):
                errors["content_sha256"] = "A lowercase SHA-256 digest is required for file imports."
        if self.rows_imported + self.rows_rejected > self.rows_received:
            errors["rows_received"] = "Imported and rejected rows cannot exceed received rows."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"Import {self.id} ({self.status})"


class BankStatement(TenantScopedModel, TimestampedModel):
    """A statement header created from manual entry or a successful import."""

    class Status(models.TextChoices):
        IMPORTED = "imported", "Imported"
        RECONCILING = "reconciling", "Reconciling"
        RECONCILED = "reconciled", "Reconciled"
        VOID = "void", "Void"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="statements")
    statement_import = models.OneToOneField(
        BankStatementImport,
        on_delete=models.PROTECT,
        related_name="statement",
        null=True,
        blank=True,
    )
    statement_reference = models.CharField(max_length=100)
    period_start = models.DateField()
    period_end = models.DateField()
    statement_date = models.DateField()
    opening_balance = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    closing_balance = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    transaction_total = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    calculated_closing_balance = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    balance_variance = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IMPORTED)
    is_reconciled = models.BooleanField(default=False)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    created_by_id = models.UUIDField()

    class Meta:
        db_table = "bank_statements"
        ordering = ("-period_end", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "bank_account", "statement_reference"),
                name="br_statement_reference_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(period_start__lte=models.F("period_end")), name="br_statement_period_ck"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="reconciled", is_reconciled=True)
                    | (~models.Q(status="reconciled") & models.Q(is_reconciled=False))
                ),
                name="br_statement_reconciled_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "bank_account", "period_end"), name="br_statement_account_date_ix"),
            models.Index(fields=("tenant_id", "status", "period_end"), name="br_statement_status_date_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        self.statement_reference = _trimmed(self.statement_reference)
        errors: dict[str, str] = {}
        if self.bank_account_id and self.bank_account.tenant_id != self.tenant_id:
            errors["bank_account"] = "Bank account must belong to this tenant."
        if self.statement_import_id:
            if self.statement_import.tenant_id != self.tenant_id:
                errors["statement_import"] = "Statement import must belong to this tenant."
            elif self.statement_import.bank_account_id != self.bank_account_id:
                errors["statement_import"] = "Statement import must target this bank account."
        if not self.statement_reference:
            errors["statement_reference"] = "Statement reference must not be blank."
        if self.period_start and self.period_end and self.period_start > self.period_end:
            errors["period_end"] = "Period end must be on or after period start."
        if self.period_end and self.statement_date != self.period_end:
            errors["statement_date"] = "Statement date must equal period end."
        if (self.status == self.Status.RECONCILED) != self.is_reconciled:
            errors["is_reconciled"] = "Reconciled status and compatibility projection must agree."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.bank_account.masked_account_number} - {self.statement_reference}"


class BankTransaction(TenantScopedModel, TimestampedModel):
    """A normalized bank-side statement line."""

    class TransactionType(models.TextChoices):
        DEBIT = "debit", "Debit"
        CREDIT = "credit", "Credit"

    class MatchStatus(models.TextChoices):
        UNMATCHED = "unmatched", "Unmatched"
        PROPOSED = "proposed", "Proposed"
        MATCHED = "matched", "Matched"
        EXCLUDED = "excluded", "Excluded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bank_statement = models.ForeignKey(BankStatement, on_delete=models.PROTECT, related_name="transactions")
    sequence_number = models.PositiveIntegerField()
    external_id = models.CharField(max_length=128, blank=True)
    transaction_date = models.DateField()
    value_date = models.DateField(null=True, blank=True)
    description = models.CharField(max_length=500)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    running_balance = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    reference_number = models.CharField(max_length=100, blank=True)
    counterparty_name = models.CharField(max_length=255, blank=True)
    counterparty_account_masked = models.CharField(max_length=64, blank=True)
    match_status = models.CharField(max_length=20, choices=MatchStatus.choices, default=MatchStatus.UNMATCHED)
    is_reconciled = models.BooleanField(default=False)
    matched_payment_id = models.UUIDField(null=True, blank=True, help_text="External payment reference")
    source_data = models.JSONField(default=dict, blank=True)
    created_by_id = models.UUIDField()

    class Meta:
        db_table = "bank_transactions"
        ordering = ("transaction_date", "sequence_number", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "bank_statement", "sequence_number"),
                name="br_transaction_sequence_uniq",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "bank_statement", "external_id"),
                condition=~models.Q(external_id=""),
                name="br_transaction_external_uniq",
            ),
            models.CheckConstraint(condition=~models.Q(amount=MONEY_ZERO), name="br_transaction_amount_nonzero_ck"),
            models.CheckConstraint(
                condition=(
                    models.Q(transaction_type="debit", amount__lt=0) | models.Q(transaction_type="credit", amount__gt=0)
                ),
                name="br_transaction_sign_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "bank_statement", "transaction_date"), name="br_transaction_statement_ix"
            ),
            models.Index(fields=("tenant_id", "match_status", "transaction_date"), name="br_transaction_match_ix"),
            models.Index(fields=("tenant_id", "reference_number"), name="br_transaction_reference_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        self.description = _trimmed(self.description)
        self.external_id = _trimmed(self.external_id)
        self.reference_number = _trimmed(self.reference_number)
        self.counterparty_name = _trimmed(self.counterparty_name)
        self.counterparty_account_masked = _trimmed(self.counterparty_account_masked)
        errors: dict[str, str] = {}
        if self.bank_statement_id and self.bank_statement.tenant_id != self.tenant_id:
            errors["bank_statement"] = "Bank statement must belong to this tenant."
        if not self.description:
            errors["description"] = "Description must not be blank."
        if self.amount == MONEY_ZERO:
            errors["amount"] = "Amount must be non-zero."
        if self.amount:
            expected = self.TransactionType.CREDIT if self.amount > 0 else self.TransactionType.DEBIT
            if self.transaction_type != expected:
                errors["transaction_type"] = "Transaction type must agree with the amount sign."
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.amount is not None:
            self.transaction_type = self.TransactionType.CREDIT if self.amount > 0 else self.TransactionType.DEBIT
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.transaction_date} - {self.description} - {self.amount}"


class MatchingRule(TenantScopedModel, TimestampedModel):
    """A deterministic matching rule or registered paid-extension hook."""

    class RuleType(models.TextChoices):
        EXACT = "exact", "Exact"
        DATE_WINDOW = "date_window", "Date window"
        REFERENCE = "reference", "Reference"
        AMOUNT_TOLERANCE = "amount_tolerance", "Amount tolerance"
        COUNTERPARTY = "counterparty", "Counterparty"
        EXTENSION = "extension", "Extension"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    rule_type = models.CharField(max_length=20, choices=RuleType.choices)
    priority = models.PositiveSmallIntegerField()
    configuration = models.JSONField(default=dict)
    auto_confirm = models.BooleanField(default=False)
    minimum_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=(MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1"))),
    )
    extension_key = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_by_id = models.UUIDField()
    updated_by_id = models.UUIDField()

    class Meta:
        db_table = "bank_matching_rules"
        ordering = ("priority", "name", "id")
        constraints = [
            models.UniqueConstraint(Lower("name"), models.F("tenant_id"), name="br_rule_name_ci_uniq"),
            models.UniqueConstraint(fields=("tenant_id", "priority"), name="br_rule_priority_uniq"),
            models.CheckConstraint(
                condition=models.Q(minimum_score__gte=0, minimum_score__lte=1),
                name="br_rule_score_range_ck",
            ),
            models.CheckConstraint(
                condition=(models.Q(auto_confirm=False) | models.Q(rule_type="extension") | models.Q(minimum_score=1)),
                name="br_rule_autoconfirm_score_ck",
            ),
        ]
        indexes = [models.Index(fields=("tenant_id", "is_active", "priority"), name="br_rule_active_priority_ix")]

    def clean(self) -> None:
        super().clean()
        self.name = _trimmed(self.name)
        self.extension_key = _trimmed(self.extension_key)
        errors: dict[str, str] = {}
        if not self.name:
            errors["name"] = "Rule name must not be blank."
        if (self.rule_type == self.RuleType.EXTENSION) != bool(self.extension_key):
            errors["extension_key"] = "Extension key is required only for extension rules."
        if self.auto_confirm and self.rule_type != self.RuleType.EXTENSION and self.minimum_score != Decimal("1"):
            errors["minimum_score"] = "Core auto-confirm rules require a score of exactly 1."
        allowed = {"date_window_days", "amount_tolerance", "reference_normalization", "counterparty_pattern"}
        unknown = {key for key in self.configuration if key not in allowed and "." not in key}
        if unknown:
            errors["configuration"] = f"Unsupported configuration keys: {', '.join(sorted(unknown))}."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return self.name


class ReconciliationSession(TenantScopedModel, TimestampedModel):
    """The auditable reconciliation lifecycle for one statement."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        IN_PROGRESS = "in_progress", "In progress"
        REVIEW = "review", "Review"
        FINALIZED = "finalized", "Finalized"
        VOID = "void", "Void"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="reconciliation_sessions")
    bank_statement = models.OneToOneField(BankStatement, on_delete=models.PROTECT, related_name="reconciliation")
    reconciliation_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    statement_balance = models.DecimalField(max_digits=19, decimal_places=4)
    ledger_balance = models.DecimalField(max_digits=19, decimal_places=4)
    matched_amount = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    unmatched_amount = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    difference = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    tolerance = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    notes = models.TextField(blank=True)
    transition_history = models.JSONField(default=list, blank=True)
    started_by_id = models.UUIDField()
    reviewed_by_id = models.UUIDField(null=True, blank=True)
    finalized_by_id = models.UUIDField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "bank_reconciliation_sessions"
        ordering = ("-reconciliation_date", "-id")
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "bank_statement"), name="br_session_statement_uniq"),
            models.CheckConstraint(condition=models.Q(tolerance__gte=0), name="br_session_tolerance_ck"),
            models.CheckConstraint(
                condition=(
                    models.Q(status="finalized", finalized_by_id__isnull=False, finalized_at__isnull=False)
                    | (
                        ~models.Q(status="finalized")
                        & models.Q(finalized_by_id__isnull=True, finalized_at__isnull=True)
                    )
                ),
                name="br_session_finalized_fields_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "bank_account", "reconciliation_date"), name="br_session_account_date_ix"
            ),
            models.Index(fields=("tenant_id", "status", "reconciliation_date"), name="br_session_status_date_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.bank_account_id and self.bank_account.tenant_id != self.tenant_id:
            errors["bank_account"] = "Bank account must belong to this tenant."
        if self.bank_statement_id:
            if self.bank_statement.tenant_id != self.tenant_id:
                errors["bank_statement"] = "Bank statement must belong to this tenant."
            elif self.bank_statement.bank_account_id != self.bank_account_id:
                errors["bank_statement"] = "Bank statement must belong to this bank account."
        if self.tolerance < MONEY_ZERO:
            errors["tolerance"] = "Tolerance must be non-negative."
        if self.status == self.Status.FINALIZED:
            if not self.finalized_by_id or not self.finalized_at:
                errors["status"] = "Finalized sessions require actor and timestamp evidence."
        elif self.finalized_by_id or self.finalized_at:
            errors["status"] = "Finalization evidence is valid only for finalized sessions."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"Reconciliation {self.id} ({self.status})"


class ReconciliationMatch(TenantScopedModel, TimestampedModel):
    """A match allocation group."""

    class MatchType(models.TextChoices):
        AUTO = "auto", "Automatic"
        MANUAL = "manual", "Manual"
        ONE_TO_MANY = "one_to_many", "One to many"
        MANY_TO_ONE = "many_to_one", "Many to one"
        ADJUSTMENT = "adjustment", "Adjustment"

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"
        REVERSED = "reversed", "Reversed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reconciliation = models.ForeignKey(ReconciliationSession, on_delete=models.PROTECT, related_name="matches")
    match_type = models.CharField(max_length=20, choices=MatchType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)
    score = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    rule = models.ForeignKey(MatchingRule, on_delete=models.SET_NULL, related_name="matches", null=True, blank=True)
    explanation = models.JSONField(default=dict, blank=True)
    matched_at = models.DateTimeField(null=True, blank=True)
    matched_by_id = models.UUIDField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by_id = models.UUIDField(null=True, blank=True)
    reversal_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "bank_reconciliation_matches"
        ordering = ("created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(score__isnull=True) | models.Q(score__gte=0, score__lte=1),
                name="br_match_score_range_ck",
            ),
            models.CheckConstraint(
                condition=~models.Q(match_type="auto") | models.Q(score__isnull=False),
                name="br_match_auto_score_ck",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="confirmed")
                | models.Q(matched_at__isnull=False, matched_by_id__isnull=False),
                name="br_match_confirmed_evidence_ck",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status="reversed")
                    | models.Q(reversed_at__isnull=False, reversed_by_id__isnull=False) & ~models.Q(reversal_reason="")
                ),
                name="br_match_reversed_evidence_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "reconciliation", "status"), name="br_match_session_status_ix"),
            models.Index(fields=("tenant_id", "rule", "score"), name="br_match_rule_score_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        self.reversal_reason = _trimmed(self.reversal_reason)
        errors: dict[str, str] = {}
        if self.reconciliation_id and self.reconciliation.tenant_id != self.tenant_id:
            errors["reconciliation"] = "Reconciliation must belong to this tenant."
        if self.rule_id and self.rule.tenant_id != self.tenant_id:
            errors["rule"] = "Matching rule must belong to this tenant."
        if self.match_type == self.MatchType.AUTO and self.score is None:
            errors["score"] = "Automatic proposals require a score."
        if self.score is not None and not Decimal("0") <= self.score <= Decimal("1"):
            errors["score"] = "Score must be between zero and one."
        if self.status == self.Status.CONFIRMED and (not self.matched_by_id or not self.matched_at):
            errors["status"] = "Confirmed matches require actor and timestamp evidence."
        if self.status == self.Status.REVERSED and (
            not self.reversed_by_id or not self.reversed_at or not self.reversal_reason
        ):
            errors["status"] = "Reversed matches require actor, timestamp, and reason evidence."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"Match {self.id} ({self.status})"


class ReconciliationMatchLine(TenantScopedModel, TimestampedModel):
    """One bank- or ledger-side allocation within a match group."""

    class Side(models.TextChoices):
        BANK = "bank", "Bank"
        LEDGER = "ledger", "Ledger"

    class LedgerEntryType(models.TextChoices):
        PAYMENT = "payment", "Payment"
        JOURNAL_LINE = "journal_line", "Journal line"
        DEPOSIT = "deposit", "Deposit"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(ReconciliationMatch, on_delete=models.CASCADE, related_name="lines")
    side = models.CharField(max_length=10, choices=Side.choices)
    bank_transaction = models.ForeignKey(
        BankTransaction,
        on_delete=models.PROTECT,
        related_name="match_lines",
        null=True,
        blank=True,
    )
    ledger_entry_id = models.UUIDField(null=True, blank=True)
    ledger_entry_type = models.CharField(max_length=40, choices=LedgerEntryType.choices, blank=True)
    allocated_amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3)

    class Meta:
        db_table = "bank_reconciliation_match_lines"
        ordering = ("side", "created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(side="bank", bank_transaction__isnull=False, ledger_entry_id__isnull=True)
                    | models.Q(side="ledger", bank_transaction__isnull=True, ledger_entry_id__isnull=False)
                ),
                name="br_match_line_side_reference_ck",
            ),
            models.CheckConstraint(
                condition=~models.Q(allocated_amount=MONEY_ZERO), name="br_match_line_amount_nonzero_ck"
            ),
            models.CheckConstraint(
                condition=models.Q(currency=Upper("currency")), name="br_match_line_currency_upper_ck"
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "match", "bank_transaction"),
                condition=models.Q(side="bank"),
                name="br_match_line_bank_uniq",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "match", "ledger_entry_id", "ledger_entry_type"),
                condition=models.Q(side="ledger"),
                name="br_match_line_ledger_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "bank_transaction"), name="br_match_line_bank_ix"),
            models.Index(fields=("tenant_id", "ledger_entry_id", "ledger_entry_type"), name="br_match_line_ledger_ix"),
        ]

    def clean(self) -> None:
        super().clean()
        self.currency = _trimmed(self.currency).upper()
        errors: dict[str, str] = {}
        if self.match_id and self.match.tenant_id != self.tenant_id:
            errors["match"] = "Match must belong to this tenant."
        if self.side == self.Side.BANK:
            if not self.bank_transaction_id or self.ledger_entry_id:
                errors["side"] = "Bank lines require only a bank transaction."
            elif self.bank_transaction.tenant_id != self.tenant_id:
                errors["bank_transaction"] = "Bank transaction must belong to this tenant."
        elif self.side == self.Side.LEDGER:
            if self.bank_transaction_id or not self.ledger_entry_id:
                errors["side"] = "Ledger lines require only a ledger entry."
            if not self.ledger_entry_type:
                errors["ledger_entry_type"] = "Ledger entry type is required for ledger lines."
        if self.allocated_amount == MONEY_ZERO:
            errors["allocated_amount"] = "Allocated amount must be non-zero."
        if self.match_id and self.currency != self.match.reconciliation.bank_account.currency:
            errors["currency"] = "Allocation currency must equal the account currency."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.side} allocation {self.allocated_amount} {self.currency}"
