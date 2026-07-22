"""Tenant-safe persistence for the SARAISE accounting core.

Models enforce invariants that must also hold when they are used outside DRF.
Cross-aggregate orchestration, idempotency and locking remain service concerns.
"""

from __future__ import annotations

import re
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Max, Q

from src.core.tenancy import TENANT_SCOPED, TenantQuerySet, TenantScopedModel, TimestampedModel, tenancy_scope

MONEY_QUANTUM = Decimal("0.01")
RATE_QUANTUM = Decimal("0.00000001")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
LEGACY_UNATTRIBUTED_ACTOR = "legacy:direct-orm"


def money(value: Decimal | str | int) -> Decimal:
    """Round a monetary amount using the module-wide half-up policy."""

    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _normalise_currency(instance: models.Model, field: str = "currency") -> None:
    value = str(getattr(instance, field, "") or "").strip().upper()
    setattr(instance, field, value)
    if not _CURRENCY_RE.fullmatch(value):
        raise ValidationError({field: "Currency must be an uppercase ISO-4217 three-letter code."})


def _require_same_tenant(instance: models.Model, relation: str) -> None:
    relation_id = getattr(instance, f"{relation}_id", None)
    if relation_id is None:
        return
    related = getattr(instance, relation, None)
    if related is not None and related.tenant_id != instance.tenant_id:
        raise ValidationError({relation: "Related records must belong to the same tenant."})


def _require_json_object(instance: models.Model, field: str) -> None:
    if not isinstance(getattr(instance, field), dict):
        raise ValidationError({field: "This value must be a JSON object."})


class AuditedAggregateQuerySet(TenantQuerySet):
    """Keep legacy ORM creation explicit without weakening audit columns."""

    def create(self, **kwargs: Any) -> models.Model:
        field_names = {field.name for field in self.model._meta.concrete_fields}
        if "created_by" in field_names:
            kwargs.setdefault("created_by", LEGACY_UNATTRIBUTED_ACTOR)
        if "updated_by" in field_names:
            kwargs.setdefault("updated_by", kwargs.get("created_by", LEGACY_UNATTRIBUTED_ACTOR))
        return super().create(**kwargs)


class AuditedAggregate(TenantScopedModel, TimestampedModel):
    """Audit, concurrency and create-idempotency fields for mutable roots."""

    created_by = models.CharField(max_length=255)
    updated_by = models.CharField(max_length=255)
    version = models.PositiveBigIntegerField(default=1)
    creation_idempotency_key = models.CharField(max_length=255, null=True, blank=True)
    creation_request_fingerprint = models.CharField(max_length=64, null=True, blank=True)

    objects = AuditedAggregateQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Database constraints remain the race-safe authority; model/domain
        # validation still runs before every write.
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)


class SoftDeletableAggregate(AuditedAggregate):
    """Consistent evidence for aggregates hidden rather than destroyed."""

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        abstract = True

    def clean(self) -> None:
        super().clean()
        if self.is_deleted != (self.deleted_at is not None):
            raise ValidationError({"is_deleted": "Deletion flag and deletion timestamp must change together."})
        if self.is_deleted and not self.deleted_by:
            raise ValidationError({"deleted_by": "A deletion actor is required."})


class StatefulAggregate(AuditedAggregate):
    """Reject lifecycle mutation that lacks append-only machine evidence."""

    transition_history = models.JSONField(default=list, blank=True, editable=False)
    _state_edges: ClassVar[dict[tuple[str, str], str]] = {}

    class Meta:
        abstract = True

    def _validate_state_write(self) -> None:
        if self._state.adding or self.pk is None:
            if self.transition_history:
                raise ValidationError({"transition_history": "New aggregates cannot supply transition history."})
            return
        prior = (
            type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id)
            .values("status", "transition_history")
            .first()
        )
        if not prior:
            return
        old_history = prior["transition_history"]
        new_history = self.transition_history
        if not isinstance(new_history, list) or not isinstance(old_history, list):
            raise ValidationError({"transition_history": "Transition history must be a JSON array."})
        if new_history[: len(old_history)] != old_history:
            raise ValidationError({"transition_history": "Transition history is append-only."})
        state_changed = prior["status"] != self.status
        if not state_changed and new_history != old_history:
            raise ValidationError({"transition_history": "History may change only with aggregate state."})
        if not state_changed:
            return
        if len(new_history) != len(old_history) + 1:
            raise ValidationError("Status changes must use the accounting state machine.", code="state_machine")
        record = new_history[-1]
        if not isinstance(record, dict):
            raise ValidationError({"transition_history": "Transition entries must be JSON objects."})
        command = str(record.get("command") or "")
        if (
            record.get("from_state") != prior["status"]
            or record.get("to_state") != self.status
            or self._state_edges.get((prior["status"], command)) != self.status
            or not str(record.get("transition_key") or "").strip()
            or not str(record.get("occurred_at") or "").strip()
        ):
            raise ValidationError("Status changes must use the accounting state machine.", code="state_machine")

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.transition_history, list):
            raise ValidationError({"transition_history": "Transition history must be a JSON array."})
        self._validate_state_write()


class SoftDeletableStatefulAggregate(SoftDeletableAggregate, StatefulAggregate):
    class Meta:
        abstract = True


class AccountType(models.TextChoices):
    ASSET = "asset", "Asset"
    LIABILITY = "liability", "Liability"
    EQUITY = "equity", "Equity"
    REVENUE = "revenue", "Revenue"
    EXPENSE = "expense", "Expense"


class NormalBalance(models.TextChoices):
    DEBIT = "debit", "Debit"
    CREDIT = "credit", "Credit"


class CashFlowCategory(models.TextChoices):
    OPERATING = "operating", "Operating"
    INVESTING = "investing", "Investing"
    FINANCING = "financing", "Financing"


@tenancy_scope(TENANT_SCOPED)
class Account(SoftDeletableAggregate):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    normal_balance = models.CharField(max_length=10, choices=NormalBalance.choices, default=NormalBalance.DEBIT)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        db_column="parent_account_id",
    )
    is_group = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    currency = models.CharField(max_length=3, default="USD")
    allow_multi_currency = models.BooleanField(default=False)
    cash_flow_category = models.CharField(max_length=12, choices=CashFlowCategory.choices, null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "accounting_accounts"
        indexes = [
            models.Index(fields=("tenant_id", "code"), name="acct_account_code_idx"),
            models.Index(fields=("tenant_id", "account_type", "is_active"), name="acct_account_type_idx"),
            models.Index(fields=("tenant_id", "parent", "code"), name="acct_account_parent_idx"),
            models.Index(fields=("tenant_id", "is_deleted", "code"), name="acct_account_live_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "code"), condition=Q(is_deleted=False), name="acct_account_code_uq"
            ),
            models.CheckConstraint(condition=Q(parent__isnull=True) | ~Q(parent=F("id")), name="acct_account_parent_ck"),
            models.CheckConstraint(
                condition=Q(normal_balance__in=NormalBalance.values), name="acct_account_balance_ck"
            ),
            models.UniqueConstraint(fields=("tenant_id", "creation_idempotency_key"), condition=Q(creation_idempotency_key__isnull=False), name="acct_account_idem_uq"),
            models.CheckConstraint(condition=(Q(is_deleted=False, deleted_at__isnull=True) | Q(is_deleted=True, deleted_at__isnull=False)), name="acct_account_softdel_ck"),
        ]

    @property
    def parent_account_id(self) -> uuid.UUID | None:
        """Compatibility alias for the former unvalidated UUID field."""

        return self.parent_id

    @parent_account_id.setter
    def parent_account_id(self, value: uuid.UUID | None) -> None:
        self.parent_id = value

    def clean(self) -> None:
        super().clean()
        self.code = self.code.strip().upper()
        _normalise_currency(self)
        if self.parent_id:
            if self.parent_id == self.id:
                raise ValidationError({"parent": "An account cannot be its own parent."})
            _require_same_tenant(self, "parent")
            if not self.parent.is_group:
                raise ValidationError({"parent": "A parent account must be a group account."})
            ancestor = self.parent
            seen = {self.id}
            while ancestor is not None:
                if ancestor.id in seen:
                    raise ValidationError({"parent": "Account hierarchy cannot contain a cycle."})
                seen.add(ancestor.id)
                ancestor = ancestor.parent
        if not self._state.adding and self.pk:
            prior = type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).values(
                "account_type", "normal_balance", "currency"
            ).first()
            if prior and any(prior[field] != getattr(self, field) for field in prior):
                if JournalLine.objects.filter(
                    tenant_id=self.tenant_id, account_id=self.pk, journal_entry__status=JournalEntryStatus.POSTED
                ).exists():
                    raise ValidationError("Account accounting attributes are immutable after posting.")

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if JournalLine.objects.filter(tenant_id=self.tenant_id, account_id=self.pk).exists():
            raise ValidationError("Accounts with journal history must be deactivated.", code="account_has_history")
        return super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class PostingPeriodStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"
    LOCKED = "locked", "Locked"


@tenancy_scope(TENANT_SCOPED)
class PostingPeriod(StatefulAggregate):
    _state_edges = {
        (PostingPeriodStatus.OPEN, "close"): PostingPeriodStatus.CLOSED,
        (PostingPeriodStatus.CLOSED, "reopen"): PostingPeriodStatus.OPEN,
        (PostingPeriodStatus.CLOSED, "lock"): PostingPeriodStatus.LOCKED,
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    period_name = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    fiscal_year = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=PostingPeriodStatus.choices, default=PostingPeriodStatus.OPEN)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.CharField(max_length=255, null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "accounting_posting_periods"
        indexes = [
            models.Index(fields=("tenant_id", "fiscal_year", "start_date"), name="acct_period_fy_idx"),
            models.Index(fields=("tenant_id", "status", "start_date"), name="acct_period_status_idx"),
            models.Index(fields=("tenant_id", "start_date", "end_date"), name="acct_period_dates_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "period_name", "fiscal_year"), name="acct_period_name_uq"
            ),
            models.CheckConstraint(condition=Q(start_date__lte=F("end_date")), name="acct_period_dates_ck"),
            models.UniqueConstraint(fields=("tenant_id", "creation_idempotency_key"), condition=Q(creation_idempotency_key__isnull=False), name="acct_period_idem_uq"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({"end_date": "End date cannot precede start date."})
        if self.start_date and self.fiscal_year != self.start_date.year:
            raise ValidationError({"fiscal_year": "Fiscal year must match the period start year."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.start_date and self.fiscal_year is None:
            self.fiscal_year = self.start_date.year
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.period_name} ({self.status})"


class JournalEntryStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    POSTED = "posted", "Posted"
    REVERSED = "reversed", "Reversed"


@tenancy_scope(TENANT_SCOPED)
class JournalEntry(SoftDeletableStatefulAggregate):
    _state_edges = {
        (JournalEntryStatus.DRAFT, "post"): JournalEntryStatus.POSTED,
        (JournalEntryStatus.POSTED, "reverse"): JournalEntryStatus.REVERSED,
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entry_number = models.CharField(max_length=50)
    posting_date = models.DateField()
    posting_period = models.ForeignKey(PostingPeriod, on_delete=models.PROTECT, related_name="journal_entries")
    reference = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=JournalEntryStatus.choices, default=JournalEntryStatus.DRAFT)
    currency = models.CharField(max_length=3, default="USD")
    debit_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    credit_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.CharField(max_length=255, null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.CharField(max_length=255, null=True, blank=True)
    reversed_entry = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversal_entries"
    )
    source_module = models.CharField(max_length=100, blank=True)
    source_reference = models.CharField(max_length=255, blank=True)
    source_idempotency_key = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "accounting_journal_entries"
        indexes = [
            models.Index(fields=("tenant_id", "posting_date", "entry_number"), name="acct_je_date_num_idx"),
            models.Index(fields=("tenant_id", "status", "posting_date"), name="acct_je_status_date_idx"),
            models.Index(fields=("tenant_id", "posting_period", "status"), name="acct_je_period_idx"),
            models.Index(fields=("tenant_id", "source_module", "source_reference"), name="acct_je_source_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "entry_number"), condition=Q(is_deleted=False), name="acct_je_number_uq"
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "source_module", "source_idempotency_key"),
                condition=Q(source_idempotency_key__isnull=False),
                name="acct_je_source_idem_uq",
            ),
            models.CheckConstraint(condition=Q(debit_total__gte=0), name="acct_je_debit_nonneg_ck"),
            models.CheckConstraint(condition=Q(credit_total__gte=0), name="acct_je_credit_nonneg_ck"),
            models.CheckConstraint(
                condition=Q(reversed_entry__isnull=True) | ~Q(reversed_entry=F("id")), name="acct_je_reversal_self_ck"
            ),
            models.UniqueConstraint(fields=("tenant_id", "creation_idempotency_key"), condition=Q(creation_idempotency_key__isnull=False), name="acct_je_create_idem_uq"),
            models.CheckConstraint(condition=(Q(is_deleted=False, deleted_at__isnull=True) | Q(is_deleted=True, deleted_at__isnull=False)), name="acct_je_softdel_ck"),
        ]

    def clean(self) -> None:
        super().clean()
        _normalise_currency(self)
        _require_same_tenant(self, "posting_period")
        _require_same_tenant(self, "reversed_entry")
        if self.reversed_entry_id == self.id:
            raise ValidationError({"reversed_entry": "An entry cannot reverse itself."})
        if self.debit_total < 0 or self.credit_total < 0:
            raise ValidationError("Journal totals cannot be negative.")
        if not self._state.adding and self.pk:
            prior = type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).first()
            if prior and prior.status in {JournalEntryStatus.POSTED, JournalEntryStatus.REVERSED}:
                # The state machine persists status=posted first, then the post command writes the
                # computed totals and posting stamp in a second save. Those fields are set AS PART
                # OF posting, so they must be writable in that window — otherwise posting an entry
                # is rejected by its own immutability guard. The fields that define the entry's
                # business content (accounts, lines, posting_date, entry_number, per-line amounts)
                # remain outside this set and stay immutable after posting.
                mutable = {
                    "status", "transition_history", "reversed_at", "reversed_by", "updated_by",
                    "version", "updated_at", "posted_at", "posted_by", "debit_total", "credit_total",
                }
                for field in self._meta.concrete_fields:
                    if field.name not in mutable and getattr(prior, field.attname) != getattr(self, field.attname):
                        raise ValidationError("Posted journal entries are immutable.", code="posted_immutable")

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.status != JournalEntryStatus.DRAFT:
            raise ValidationError("Posted journal entries cannot be deleted.", code="posted_immutable")
        return super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.entry_number} - {self.posting_date}"


@tenancy_scope(TENANT_SCOPED)
class JournalLine(TenantScopedModel, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    line_number = models.PositiveIntegerField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="journal_lines")
    debit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    credit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("1.00000000"))
    base_debit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    base_credit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    description = models.CharField(max_length=500, blank=True)
    cost_center = models.CharField(max_length=100, blank=True)
    dimension_values = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "accounting_journal_lines"
        indexes = [
            models.Index(fields=("tenant_id", "journal_entry", "line_number"), name="acct_jl_entry_line_idx"),
            models.Index(fields=("tenant_id", "account", "journal_entry"), name="acct_jl_account_idx"),
            models.Index(fields=("tenant_id", "cost_center"), name="acct_jl_cost_center_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "journal_entry", "line_number"), name="acct_jl_line_uq"
            ),
            models.CheckConstraint(
                condition=(Q(debit_amount__gt=0, credit_amount=0) | Q(credit_amount__gt=0, debit_amount=0)),
                name="acct_jl_debit_credit_ck",
            ),
            models.CheckConstraint(condition=Q(base_debit_amount__gte=0), name="acct_jl_base_debit_ck"),
            models.CheckConstraint(condition=Q(base_credit_amount__gte=0), name="acct_jl_base_credit_ck"),
            models.CheckConstraint(condition=Q(exchange_rate__gt=0), name="acct_jl_rate_ck"),
        ]

    def clean(self) -> None:
        _normalise_currency(self)
        _require_same_tenant(self, "journal_entry")
        _require_same_tenant(self, "account")
        _require_json_object(self, "dimension_values")
        if (self.debit_amount > 0) == (self.credit_amount > 0):
            raise ValidationError("Exactly one of debit or credit must be greater than zero.")
        if min(self.debit_amount, self.credit_amount, self.base_debit_amount, self.base_credit_amount) < 0:
            raise ValidationError("Journal line amounts cannot be negative.")
        if self.exchange_rate <= 0:
            raise ValidationError({"exchange_rate": "Exchange rate must be positive."})
        if self.base_debit_amount != money(self.debit_amount * self.exchange_rate):
            raise ValidationError({"base_debit_amount": "Base debit does not match the rounded exchange conversion."})
        if self.base_credit_amount != money(self.credit_amount * self.exchange_rate):
            raise ValidationError({"base_credit_amount": "Base credit does not match the rounded exchange conversion."})
        if self.account_id and self.account.is_group:
            raise ValidationError({"account": "Group accounts cannot receive journal lines."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.journal_entry_id and self.journal_entry.status != JournalEntryStatus.DRAFT:
            raise ValidationError("Posted journal lines are immutable.", code="posted_immutable")
        if self._state.adding:
            if self.line_number is None and self.journal_entry_id:
                current = (
                    type(self).objects.filter(
                        tenant_id=self.tenant_id,
                        journal_entry_id=self.journal_entry_id,
                    ).aggregate(maximum=Max("line_number"))["maximum"]
                    or 0
                )
                self.line_number = current + 1
            if not self.currency and self.journal_entry_id:
                self.currency = self.journal_entry.currency
            self.base_debit_amount = money(self.debit_amount * self.exchange_rate)
            self.base_credit_amount = money(self.credit_amount * self.exchange_rate)
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.journal_entry.status != JournalEntryStatus.DRAFT:
            raise ValidationError("Posted journal lines are immutable.", code="posted_immutable")
        return super().delete(*args, **kwargs)


class APInvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    APPROVED = "approved", "Approved"
    POSTED = "posted", "Posted"
    PARTIALLY_PAID = "partially_paid", "Partially paid"
    PAID = "paid", "Paid"
    CANCELLED = "cancelled", "Cancelled"


class ARInvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    POSTED = "posted", "Posted"
    PARTIALLY_PAID = "partially_paid", "Partially paid"
    PAID = "paid", "Paid"
    OVERDUE = "overdue", "Overdue"
    CANCELLED = "cancelled", "Cancelled"


class InvoiceAggregate(SoftDeletableStatefulAggregate):
    invoice_number = models.CharField(max_length=100)
    invoice_date = models.DateField()
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="USD")
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("1.00000000"))
    description = models.TextField(blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.CharField(max_length=255, null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.CharField(max_length=255, null=True, blank=True)
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, null=True, blank=True)
    legacy_without_lines = models.BooleanField(default=False)

    class Meta:
        abstract = True

    def clean(self) -> None:
        super().clean()
        _normalise_currency(self)
        _require_same_tenant(self, "journal_entry")
        if self.invoice_date and self.due_date and self.invoice_date > self.due_date:
            raise ValidationError({"due_date": "Due date cannot precede invoice date."})
        if min(self.amount, self.tax_amount, self.total_amount, self.paid_amount) < 0:
            raise ValidationError("Invoice amounts cannot be negative.")
        if self.total_amount != money(self.amount + self.tax_amount):
            raise ValidationError({"total_amount": "Total must equal subtotal plus tax."})
        if self.paid_amount > self.total_amount:
            raise ValidationError({"paid_amount": "Paid amount cannot exceed invoice total."})
        if self.exchange_rate <= 0:
            raise ValidationError({"exchange_rate": "Exchange rate must be positive."})


@tenancy_scope(TENANT_SCOPED)
class APInvoice(InvoiceAggregate):
    _state_edges = {
        (APInvoiceStatus.DRAFT, "submit"): APInvoiceStatus.SUBMITTED,
        (APInvoiceStatus.SUBMITTED, "approve"): APInvoiceStatus.APPROVED,
        (APInvoiceStatus.SUBMITTED, "reject"): APInvoiceStatus.DRAFT,
        (APInvoiceStatus.APPROVED, "post"): APInvoiceStatus.POSTED,
        (APInvoiceStatus.POSTED, "record_partial_payment"): APInvoiceStatus.PARTIALLY_PAID,
        (APInvoiceStatus.POSTED, "record_full_payment"): APInvoiceStatus.PAID,
        (APInvoiceStatus.PARTIALLY_PAID, "record_full_payment"): APInvoiceStatus.PAID,
        (APInvoiceStatus.DRAFT, "cancel"): APInvoiceStatus.CANCELLED,
        (APInvoiceStatus.SUBMITTED, "cancel"): APInvoiceStatus.CANCELLED,
        (APInvoiceStatus.APPROVED, "cancel"): APInvoiceStatus.CANCELLED,
    }

    supplier_id = models.UUIDField()
    status = models.CharField(max_length=20, choices=APInvoiceStatus.choices, default=APInvoiceStatus.DRAFT)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "accounting_ap_invoices"
        indexes = [
            models.Index(fields=("tenant_id", "supplier_id", "invoice_number"), name="acct_ap_supplier_idx"),
            models.Index(fields=("tenant_id", "status", "due_date"), name="acct_ap_status_due_idx"),
            models.Index(fields=("tenant_id", "invoice_date"), name="acct_ap_date_idx"),
            models.Index(fields=("tenant_id", "journal_entry"), name="acct_ap_journal_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "supplier_id", "invoice_number"),
                condition=Q(is_deleted=False),
                name="acct_ap_invoice_uq",
            ),
            models.CheckConstraint(condition=Q(invoice_date__lte=F("due_date")), name="acct_ap_dates_ck"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="acct_ap_amount_ck"),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name="acct_ap_tax_ck"),
            models.CheckConstraint(condition=Q(total_amount=F("amount") + F("tax_amount")), name="acct_ap_total_ck"),
            models.CheckConstraint(condition=Q(paid_amount__gte=0, paid_amount__lte=F("total_amount")), name="acct_ap_paid_ck"),
            models.UniqueConstraint(fields=("tenant_id", "creation_idempotency_key"), condition=Q(creation_idempotency_key__isnull=False), name="acct_ap_create_idem_uq"),
            models.CheckConstraint(condition=(Q(is_deleted=False, deleted_at__isnull=True) | Q(is_deleted=True, deleted_at__isnull=False)), name="acct_ap_softdel_ck"),
        ]

    def clean(self) -> None:
        super().clean()
        if not self._state.adding and self.pk:
            prior = type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).first()
            if prior and prior.status != APInvoiceStatus.DRAFT:
                mutable = {
                    "status", "transition_history", "approved_at", "approved_by", "posted_at", "posted_by",
                    "cancelled_at", "cancelled_by", "journal_entry", "paid_amount", "updated_by", "version", "updated_at",
                }
                for field in self._meta.concrete_fields:
                    if field.name not in mutable and getattr(prior, field.attname) != getattr(self, field.attname):
                        raise ValidationError("An AP invoice is immutable after leaving draft.", code="invoice_immutable")

    def __str__(self) -> str:
        return f"AP-{self.invoice_number} - {self.total_amount}"


@tenancy_scope(TENANT_SCOPED)
class ARInvoice(InvoiceAggregate):
    _state_edges = {
        (ARInvoiceStatus.DRAFT, "post"): ARInvoiceStatus.POSTED,
        (ARInvoiceStatus.POSTED, "record_partial_payment"): ARInvoiceStatus.PARTIALLY_PAID,
        (ARInvoiceStatus.POSTED, "record_full_payment"): ARInvoiceStatus.PAID,
        (ARInvoiceStatus.PARTIALLY_PAID, "record_full_payment"): ARInvoiceStatus.PAID,
        (ARInvoiceStatus.OVERDUE, "record_full_payment"): ARInvoiceStatus.PAID,
        (ARInvoiceStatus.POSTED, "mark_overdue"): ARInvoiceStatus.OVERDUE,
        (ARInvoiceStatus.PARTIALLY_PAID, "mark_overdue"): ARInvoiceStatus.OVERDUE,
        (ARInvoiceStatus.DRAFT, "cancel"): ARInvoiceStatus.CANCELLED,
    }

    customer_id = models.UUIDField()
    status = models.CharField(max_length=20, choices=ARInvoiceStatus.choices, default=ARInvoiceStatus.DRAFT)

    class Meta:
        db_table = "accounting_ar_invoices"
        indexes = [
            models.Index(fields=("tenant_id", "customer_id", "invoice_number"), name="acct_ar_customer_idx"),
            models.Index(fields=("tenant_id", "status", "due_date"), name="acct_ar_status_due_idx"),
            models.Index(fields=("tenant_id", "invoice_date"), name="acct_ar_date_idx"),
            models.Index(fields=("tenant_id", "journal_entry"), name="acct_ar_journal_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "customer_id", "invoice_number"),
                condition=Q(is_deleted=False),
                name="acct_ar_invoice_uq",
            ),
            models.CheckConstraint(condition=Q(invoice_date__lte=F("due_date")), name="acct_ar_dates_ck"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="acct_ar_amount_ck"),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name="acct_ar_tax_ck"),
            models.CheckConstraint(condition=Q(total_amount=F("amount") + F("tax_amount")), name="acct_ar_total_ck"),
            models.CheckConstraint(condition=Q(paid_amount__gte=0, paid_amount__lte=F("total_amount")), name="acct_ar_paid_ck"),
            models.UniqueConstraint(fields=("tenant_id", "creation_idempotency_key"), condition=Q(creation_idempotency_key__isnull=False), name="acct_ar_create_idem_uq"),
            models.CheckConstraint(condition=(Q(is_deleted=False, deleted_at__isnull=True) | Q(is_deleted=True, deleted_at__isnull=False)), name="acct_ar_softdel_ck"),
        ]

    def clean(self) -> None:
        super().clean()
        if not self._state.adding and self.pk:
            prior = type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).first()
            if prior and prior.status != ARInvoiceStatus.DRAFT:
                mutable = {
                    "status", "transition_history", "posted_at", "posted_by", "cancelled_at", "cancelled_by",
                    "journal_entry", "paid_amount", "updated_by", "version", "updated_at",
                }
                for field in self._meta.concrete_fields:
                    if field.name not in mutable and getattr(prior, field.attname) != getattr(self, field.attname):
                        raise ValidationError("An AR invoice is immutable after posting.", code="invoice_immutable")

    def __str__(self) -> str:
        return f"AR-{self.invoice_number} - {self.total_amount}"


class InvoiceLine(TenantScopedModel, TimestampedModel):
    line_number = models.PositiveIntegerField()
    description = models.CharField(max_length=500)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("1.0000"))
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=15, decimal_places=2)
    cost_center = models.CharField(max_length=100, blank=True)
    dimension_values = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True

    def clean(self) -> None:
        _require_same_tenant(self, "invoice")
        _require_same_tenant(self, "account")
        _require_json_object(self, "dimension_values")
        if self.quantity <= 0:
            raise ValidationError({"quantity": "Quantity must be positive."})
        if self.unit_price < 0 or self.tax_amount < 0 or self.line_total < 0:
            raise ValidationError("Invoice line amounts cannot be negative.")
        if self.line_total != money(self.quantity * self.unit_price):
            raise ValidationError({"line_total": "Line total must equal rounded quantity times unit price."})
        if self.account_id and self.account.is_group:
            raise ValidationError({"account": "Group accounts cannot receive invoice lines."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.invoice_id and self.invoice.status != "draft":
            raise ValidationError("Invoice lines are immutable after draft.", code="invoice_immutable")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.invoice.status != "draft":
            raise ValidationError("Invoice lines are immutable after draft.", code="invoice_immutable")
        return super().delete(*args, **kwargs)


@tenancy_scope(TENANT_SCOPED)
class APInvoiceLine(InvoiceLine):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(APInvoice, on_delete=models.CASCADE, related_name="lines")

    class Meta:
        db_table = "accounting_ap_invoice_lines"
        indexes = [
            models.Index(fields=("tenant_id", "account"), name="acct_apl_account_idx"),
            models.Index(fields=("tenant_id", "invoice"), name="acct_apl_invoice_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "invoice", "line_number"), name="acct_apl_line_uq"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="acct_apl_qty_ck"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="acct_apl_price_ck"),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name="acct_apl_tax_ck"),
            models.CheckConstraint(condition=Q(line_total__gte=0), name="acct_apl_total_ck"),
        ]


@tenancy_scope(TENANT_SCOPED)
class ARInvoiceLine(InvoiceLine):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(ARInvoice, on_delete=models.CASCADE, related_name="lines")

    class Meta:
        db_table = "accounting_ar_invoice_lines"
        indexes = [
            models.Index(fields=("tenant_id", "account"), name="acct_arl_account_idx"),
            models.Index(fields=("tenant_id", "invoice"), name="acct_arl_invoice_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "invoice", "line_number"), name="acct_arl_line_uq"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="acct_arl_qty_ck"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="acct_arl_price_ck"),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name="acct_arl_tax_ck"),
            models.CheckConstraint(condition=Q(line_total__gte=0), name="acct_arl_total_ck"),
        ]


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    CHECK = "check", "Check"
    WIRE_TRANSFER = "wire_transfer", "Wire transfer"
    ACH = "ach", "ACH"
    CREDIT_CARD = "credit_card", "Credit card"
    OTHER = "other", "Other"


class PaymentStatus(models.TextChoices):
    RECORDED = "recorded", "Recorded"
    VOIDED = "voided", "Voided"


@tenancy_scope(TENANT_SCOPED)
class Payment(TenantScopedModel, TimestampedModel):
    _state_edges: ClassVar[dict[tuple[str, str], str]] = {
        (PaymentStatus.RECORDED, "void"): PaymentStatus.VOIDED
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.CharField(max_length=255)
    payment_date = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    currency = models.CharField(max_length=3, default="USD")
    reference_number = models.CharField(max_length=100, blank=True)
    ap_invoice = models.ForeignKey(APInvoice, on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    ar_invoice = models.ForeignKey(ARInvoice, on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.RECORDED)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.CharField(max_length=255, null=True, blank=True)
    void_reason = models.TextField(blank=True)
    transition_history = models.JSONField(default=list, blank=True, editable=False)
    idempotency_key = models.CharField(max_length=255)
    request_fingerprint = models.CharField(max_length=64)

    class Meta:
        db_table = "accounting_payments"
        indexes = [
            models.Index(fields=("tenant_id", "payment_date"), name="acct_payment_date_idx"),
            models.Index(fields=("tenant_id", "ap_invoice"), name="acct_payment_ap_idx"),
            models.Index(fields=("tenant_id", "ar_invoice"), name="acct_payment_ar_idx"),
            models.Index(fields=("tenant_id", "reference_number"), name="acct_payment_ref_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="acct_payment_idem_uq"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="acct_payment_amount_ck"),
            models.CheckConstraint(
                condition=(Q(ap_invoice__isnull=False, ar_invoice__isnull=True) | Q(ap_invoice__isnull=True, ar_invoice__isnull=False)),
                name="acct_payment_invoice_ck",
            ),
        ]

    def _validate_state_write(self) -> None:
        if self._state.adding or self.pk is None:
            if self.transition_history:
                raise ValidationError({"transition_history": "New payments cannot supply transition history."})
            return
        prior = type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).first()
        if not prior:
            return
        allowed_mutable = {"reference_number", "description", "status", "voided_at", "voided_by", "void_reason", "transition_history", "updated_at"}
        for field in self._meta.concrete_fields:
            if field.name not in allowed_mutable and getattr(prior, field.attname) != getattr(self, field.attname):
                raise ValidationError("Payment financial evidence is append-only.", code="payment_immutable")
        old_history = prior.transition_history
        if self.status == prior.status:
            if self.transition_history != old_history:
                raise ValidationError({"transition_history": "History may change only when voiding."})
            return
        if len(self.transition_history) != len(old_history) + 1 or self.transition_history[: len(old_history)] != old_history:
            raise ValidationError("Payment state changes must use the accounting state machine.", code="state_machine")
        record = self.transition_history[-1]
        if not isinstance(record, dict) or (
            record.get("from_state") != prior.status
            or record.get("to_state") != self.status
            or record.get("command") != "void"
            or not record.get("transition_key")
        ):
            raise ValidationError("Payment state changes must use the accounting state machine.", code="state_machine")

    def clean(self) -> None:
        _normalise_currency(self)
        _require_same_tenant(self, "ap_invoice")
        _require_same_tenant(self, "ar_invoice")
        if self.amount <= 0:
            raise ValidationError({"amount": "Payment amount must be positive."})
        if (self.ap_invoice_id is None) == (self.ar_invoice_id is None):
            raise ValidationError("Exactly one AP or AR invoice is required.")
        invoice = self.ap_invoice or self.ar_invoice
        if invoice and self.currency != invoice.currency:
            raise ValidationError({"currency": "Payment and invoice currency must match."})
        if invoice and self.payment_date < invoice.invoice_date:
            raise ValidationError({"payment_date": "Payment cannot predate its invoice."})
        if not isinstance(self.transition_history, list):
            raise ValidationError({"transition_history": "Transition history must be a JSON array."})
        self._validate_state_write()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Payments are append-only; void the payment instead.", code="payment_append_only")

    def __str__(self) -> str:
        return f"Payment {self.amount} - {self.payment_date}"


__all__ = [
    "APInvoice", "APInvoiceLine", "APInvoiceStatus", "ARInvoice", "ARInvoiceLine", "ARInvoiceStatus",
    "Account", "AccountType", "CashFlowCategory", "JournalEntry", "JournalEntryStatus", "JournalLine",
    "MONEY_QUANTUM", "NormalBalance", "Payment", "PaymentMethod", "PaymentStatus", "PostingPeriod",
    "PostingPeriodStatus", "money",
]
