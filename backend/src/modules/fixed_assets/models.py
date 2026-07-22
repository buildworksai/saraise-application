"""Tenant-safe persistence for the financial fixed-asset lifecycle."""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from src.core.state_machine import StateMachine
from src.core.tenancy import TenantQuerySet, TenantScopedModel, TimestampedModel
from src.core.tenancy.registry import TENANT_SCOPED, tenancy_scope

MONEY_QUANTUM = Decimal("0.01")
RATE_QUANTUM = Decimal("0.0001")
PRIMARY_BOOK = "corporate"


def generate_uuid() -> str:
    """Retain the legacy public callable while using UUID values for new rows."""

    return str(uuid.uuid4())


def money(value: Decimal | str | int) -> Decimal:
    """Apply the module's governed monetary rounding rule."""

    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


class DepreciationMethod(models.TextChoices):
    STRAIGHT_LINE = "straight_line", "Straight line"
    DECLINING_BALANCE = "declining_balance", "Declining balance"
    UNITS_OF_PRODUCTION = "units_of_production", "Units of production"


class AssetStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    FULLY_DEPRECIATED = "fully_depreciated", "Fully depreciated"
    DISPOSED = "disposed", "Disposed"


class ScheduleStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    CALCULATED = "calculated", "Calculated"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    SUPERSEDED = "superseded", "Superseded"


class LineStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    POSTING = "posting", "Posting"
    POSTED = "posted", "Posted"
    FAILED = "failed", "Failed"
    VOID = "void", "Void"


class TransactionType(models.TextChoices):
    CAPITALIZATION = "capitalization", "Capitalization"
    DEPRECIATION = "depreciation", "Depreciation"
    TRANSFER = "transfer", "Transfer"
    IMPAIRMENT = "impairment", "Impairment"
    DISPOSAL = "disposal", "Disposal"


class StatefulTenantModel(TenantScopedModel, TimestampedModel):
    """Prevent bypassing the state machine through direct status assignment."""

    class Meta:
        abstract = True

    def _validate_state_write(self) -> None:
        if self._state.adding or self.pk is None:
            return
        prior = type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).values(
            "status", "transition_history"
        ).first()
        if prior and prior["status"] != self.status and prior["transition_history"] == self.transition_history:
            raise ValidationError("Status changes must use the fixed-assets state machine.", code="state_machine")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._validate_state_write()
        self.full_clean()
        super().save(*args, **kwargs)


@tenancy_scope(TENANT_SCOPED)
class AssetCategory(TenantScopedModel, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    default_depreciation_method = models.CharField(max_length=30, choices=DepreciationMethod.choices)
    default_useful_life_months = models.PositiveIntegerField()
    default_residual_value_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    default_declining_balance_rate = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    asset_account_id = models.UUIDField(null=True, blank=True)
    accumulated_depreciation_account_id = models.UUIDField(null=True, blank=True)
    depreciation_expense_account_id = models.UUIDField(null=True, blank=True)
    impairment_loss_account_id = models.UUIDField(null=True, blank=True)
    disposal_gain_account_id = models.UUIDField(null=True, blank=True)
    disposal_loss_account_id = models.UUIDField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    version = models.PositiveBigIntegerField(default=1)
    creation_idempotency_key = models.CharField(max_length=255, null=True, blank=True)
    creation_request_fingerprint = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "fixed_asset_categories"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "code"), name="fa_cat_tenant_code_uniq"),
            models.UniqueConstraint(
                fields=("tenant_id", "creation_idempotency_key"),
                condition=Q(creation_idempotency_key__isnull=False),
                name="fa_cat_create_idem_uniq",
            ),
            models.CheckConstraint(condition=Q(default_useful_life_months__gt=0), name="fa_cat_life_positive"),
            models.CheckConstraint(
                condition=Q(default_residual_value_percent__gte=0, default_residual_value_percent__lte=100),
                name="fa_cat_residual_pct_range",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        default_depreciation_method=DepreciationMethod.DECLINING_BALANCE,
                        default_declining_balance_rate__gt=0,
                    )
                    | (~Q(default_depreciation_method=DepreciationMethod.DECLINING_BALANCE) & Q(default_declining_balance_rate__isnull=True))
                ),
                name="fa_cat_declining_rate_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "code"), name="fa_cat_tenant_code_idx"),
            models.Index(fields=("tenant_id", "is_active", "name"), name="fa_cat_active_name_idx"),
            models.Index(fields=("tenant_id", "default_depreciation_method"), name="fa_cat_method_idx"),
        ]

    def clean(self) -> None:
        self.code = self.code.strip().upper()
        if self.default_depreciation_method == DepreciationMethod.DECLINING_BALANCE:
            if self.default_declining_balance_rate is None or self.default_declining_balance_rate <= 0:
                raise ValidationError({"default_declining_balance_rate": "A positive rate is required."})
        elif self.default_declining_balance_rate is not None:
            raise ValidationError({"default_declining_balance_rate": "A rate is only valid for declining balance."})
        if not self._state.adding and self.pk:
            previous = type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).values("code").first()
            if previous and previous["code"] != self.code and FixedAsset.objects.filter(
                tenant_id=self.tenant_id, category_id=self.pk
            ).exists():
                raise ValidationError({"code": "Category code is immutable after first asset use."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if FixedAsset.objects.filter(tenant_id=self.tenant_id, category_id=self.pk).exists():
            raise ValidationError("Referenced categories must be deactivated.", code="category_referenced")
        return super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


@tenancy_scope(TENANT_SCOPED)
class FixedAsset(StatefulTenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset_code = models.CharField(max_length=50)
    asset_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.ForeignKey(AssetCategory, on_delete=models.PROTECT, related_name="assets")
    purchase_date = models.DateField()
    purchase_cost = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3)
    residual_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    capitalization_date = models.DateField(null=True, blank=True)
    depreciation_start_date = models.DateField(null=True, blank=True)
    depreciation_method = models.CharField(max_length=30, choices=DepreciationMethod.choices)
    useful_life_months = models.PositiveIntegerField()
    declining_balance_rate = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    expected_total_units = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    accumulated_depreciation = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    accumulated_impairment = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    net_book_value = models.DecimalField(max_digits=15, decimal_places=2)
    location = models.CharField(max_length=255, blank=True)
    cost_center = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=24, choices=AssetStatus.choices, default=AssetStatus.DRAFT)
    disposal_date = models.DateField(null=True, blank=True)
    disposal_proceeds = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    disposal_gain_loss = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    version = models.PositiveBigIntegerField(default=1)
    transition_history = models.JSONField(default=list, editable=False)
    created_by = models.CharField(max_length=255)
    updated_by = models.CharField(max_length=255)
    primary_book_code = models.CharField(max_length=32, default=PRIMARY_BOOK)
    creation_idempotency_key = models.CharField(max_length=255, null=True, blank=True)
    creation_request_fingerprint = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "fixed_assets"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "asset_code"), name="unique_fixed_asset_code_per_tenant"),
            models.UniqueConstraint(
                fields=("tenant_id", "creation_idempotency_key"),
                condition=Q(creation_idempotency_key__isnull=False),
                name="fa_asset_create_idem_uniq",
            ),
            models.CheckConstraint(condition=Q(purchase_cost__gt=0), name="fa_asset_cost_positive"),
            models.CheckConstraint(condition=Q(residual_value__gte=0) & Q(residual_value__lte=F("purchase_cost")), name="fa_asset_residual_valid"),
            models.CheckConstraint(condition=Q(useful_life_months__gt=0), name="fa_asset_life_positive"),
            models.CheckConstraint(condition=Q(accumulated_depreciation__gte=0), name="fa_asset_depr_nonnegative"),
            models.CheckConstraint(condition=Q(accumulated_impairment__gte=0), name="fa_asset_impair_nonnegative"),
            models.CheckConstraint(condition=Q(net_book_value__gte=0), name="fa_asset_nbv_nonnegative"),
            models.CheckConstraint(
                condition=Q(status=AssetStatus.DISPOSED)
                | Q(net_book_value=F("purchase_cost") - F("accumulated_depreciation") - F("accumulated_impairment")),
                name="fa_asset_balance_reconciled",
            ),
            models.CheckConstraint(condition=Q(capitalization_date__isnull=True) | Q(purchase_date__lte=F("capitalization_date")), name="fa_asset_purchase_cap_order"),
            models.CheckConstraint(condition=Q(depreciation_start_date__isnull=True) | Q(capitalization_date__lte=F("depreciation_start_date")), name="fa_asset_cap_depr_order"),
            models.CheckConstraint(
                condition=(Q(depreciation_method=DepreciationMethod.DECLINING_BALANCE, declining_balance_rate__gt=0) | (~Q(depreciation_method=DepreciationMethod.DECLINING_BALANCE) & Q(declining_balance_rate__isnull=True))),
                name="fa_asset_declining_rate_valid",
            ),
            models.CheckConstraint(
                condition=(Q(depreciation_method=DepreciationMethod.UNITS_OF_PRODUCTION, expected_total_units__gt=0) | (~Q(depreciation_method=DepreciationMethod.UNITS_OF_PRODUCTION) & Q(expected_total_units__isnull=True))),
                name="fa_asset_units_valid",
            ),
            models.CheckConstraint(
                condition=Q(status=AssetStatus.DISPOSED)
                | Q(disposal_date__isnull=True, disposal_proceeds__isnull=True, disposal_gain_loss__isnull=True),
                name="fa_asset_disposal_fields_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "asset_code"), name="fa_asset_code_idx"),
            models.Index(fields=("tenant_id", "status", "asset_code"), name="fa_asset_status_code_idx"),
            models.Index(fields=("tenant_id", "category", "status"), name="fa_asset_cat_status_idx"),
            models.Index(fields=("tenant_id", "capitalization_date"), name="fa_asset_cap_date_idx"),
            models.Index(fields=("tenant_id", "depreciation_start_date"), name="fa_asset_depr_start_idx"),
            models.Index(fields=("tenant_id", "location"), name="fa_asset_location_idx"),
            models.Index(fields=("tenant_id", "cost_center"), name="fa_asset_cost_center_idx"),
        ]

    def clean(self) -> None:
        self.asset_code = self.asset_code.strip().upper()
        self.currency = self.currency.strip().upper()
        self.primary_book_code = self.primary_book_code.strip().lower()
        for field in ("purchase_cost", "residual_value", "accumulated_depreciation", "accumulated_impairment", "net_book_value"):
            value = getattr(self, field, None)
            if value is not None:
                setattr(self, field, money(value))
        if self.category_id and self.tenant_id and not AssetCategory.objects.for_tenant(self.tenant_id).filter(pk=self.category_id).exists():
            raise ValidationError({"category": "Category was not found for this tenant."}, code="cross_tenant_reference")
        if self.currency and (len(self.currency) != 3 or not self.currency.isalpha()):
            raise ValidationError({"currency": "Use a three-letter ISO-4217 currency code."})

    def __str__(self) -> str:
        return f"{self.asset_code} - {self.asset_name}"


@tenancy_scope(TENANT_SCOPED)
class DepreciationSchedule(StatefulTenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(FixedAsset, on_delete=models.CASCADE, related_name="depreciation_schedules")
    schedule_number = models.CharField(max_length=50)
    revision = models.PositiveIntegerField(default=1)
    book_code = models.CharField(max_length=32, default=PRIMARY_BOOK)
    method = models.CharField(max_length=30, choices=DepreciationMethod.choices)
    frequency = models.CharField(max_length=20, choices=(("monthly", "Monthly"),), default="monthly")
    start_date = models.DateField()
    end_date = models.DateField()
    cost_basis = models.DecimalField(max_digits=15, decimal_places=2)
    residual_value = models.DecimalField(max_digits=15, decimal_places=2)
    depreciable_amount = models.DecimalField(max_digits=15, decimal_places=2)
    declining_balance_rate = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    expected_total_units = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    total_planned_depreciation = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=ScheduleStatus.choices, default=ScheduleStatus.DRAFT)
    calculated_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="superseded_revisions")
    transition_history = models.JSONField(default=list, editable=False)
    created_by = models.CharField(max_length=255)
    updated_by = models.CharField(max_length=255)
    version = models.PositiveBigIntegerField(default=1)
    creation_idempotency_key = models.CharField(max_length=255, null=True, blank=True)
    creation_request_fingerprint = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "fixed_asset_depreciation_schedules"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "schedule_number"), name="fa_sched_number_uniq"),
            models.UniqueConstraint(fields=("tenant_id", "asset", "book_code", "revision"), name="fa_sched_revision_uniq"),
            models.UniqueConstraint(fields=("tenant_id", "creation_idempotency_key"), condition=Q(creation_idempotency_key__isnull=False), name="fa_sched_create_idem_uniq"),
            models.UniqueConstraint(fields=("tenant_id", "asset", "book_code"), condition=Q(status=ScheduleStatus.ACTIVE), name="fa_sched_one_active_uniq"),
            models.CheckConstraint(condition=Q(start_date__lte=F("end_date")), name="fa_sched_date_order"),
            models.CheckConstraint(condition=Q(cost_basis__gt=0), name="fa_sched_cost_positive"),
            models.CheckConstraint(condition=Q(residual_value__gte=0) & Q(residual_value__lte=F("cost_basis")), name="fa_sched_residual_valid"),
            models.CheckConstraint(condition=Q(depreciable_amount=F("cost_basis") - F("residual_value")), name="fa_sched_depreciable_reconciled"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "asset", "status"), name="fa_sched_asset_status_idx"),
            models.Index(fields=("tenant_id", "status", "start_date"), name="fa_sched_status_start_idx"),
            models.Index(fields=("tenant_id", "calculated_at"), name="fa_sched_calculated_idx"),
        ]

    def clean(self) -> None:
        self.book_code = self.book_code.strip().lower()
        for field in ("cost_basis", "residual_value", "depreciable_amount", "total_planned_depreciation"):
            value = getattr(self, field, None)
            if value is not None:
                setattr(self, field, money(value))
        if self.asset_id and self.tenant_id and not FixedAsset.objects.for_tenant(self.tenant_id).filter(pk=self.asset_id).exists():
            raise ValidationError({"asset": "Asset was not found for this tenant."}, code="cross_tenant_reference")
        if self.superseded_by_id and self.tenant_id and not type(self).objects.for_tenant(self.tenant_id).filter(pk=self.superseded_by_id).exists():
            raise ValidationError({"superseded_by": "Replacement schedule was not found for this tenant."})
        if not self._state.adding and self.pk and DepreciationLine.objects.filter(
            tenant_id=self.tenant_id, schedule_id=self.pk, status=LineStatus.POSTED
        ).exists():
            immutable = ("asset_id", "book_code", "method", "frequency", "start_date", "end_date", "cost_basis", "residual_value", "declining_balance_rate", "expected_total_units")
            prior = type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).values(*immutable).first()
            if prior and any(prior[field] != getattr(self, field) for field in immutable):
                raise ValidationError("Posted schedules cannot change assumptions.", code="posted_history_immutable")

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.lines.filter(status=LineStatus.POSTED).exists():
            raise ValidationError("A schedule with posted lines cannot be deleted.", code="posted_history_immutable")
        return super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.schedule_number} r{self.revision}"


class PostedLineMutationError(ValidationError):
    pass


class DepreciationLineQuerySet(TenantQuerySet):
    def update(self, **kwargs: Any) -> int:
        if self.filter(status=LineStatus.POSTED).exists():
            raise PostedLineMutationError("Posted depreciation lines are immutable.", code="posted_line_immutable")
        return super().update(**kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        if self.filter(status=LineStatus.POSTED).exists():
            raise PostedLineMutationError("Posted depreciation lines are immutable.", code="posted_line_immutable")
        return super().delete()


@tenancy_scope(TENANT_SCOPED)
class DepreciationLine(StatefulTenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    schedule = models.ForeignKey(DepreciationSchedule, on_delete=models.CASCADE, related_name="lines")
    asset = models.ForeignKey(FixedAsset, on_delete=models.CASCADE, related_name="depreciation_lines")
    book_code = models.CharField(max_length=32, default=PRIMARY_BOOK)
    sequence = models.PositiveIntegerField()
    period_start = models.DateField()
    period_end = models.DateField()
    opening_net_book_value = models.DecimalField(max_digits=15, decimal_places=2)
    units_consumed = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    depreciation_amount = models.DecimalField(max_digits=15, decimal_places=2)
    accumulated_depreciation = models.DecimalField(max_digits=15, decimal_places=2)
    closing_net_book_value = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=20, choices=LineStatus.choices, default=LineStatus.PLANNED)
    journal_entry_id = models.UUIDField(null=True, blank=True)
    posting_job_id = models.UUIDField(null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    posting_error_code = models.CharField(max_length=64, blank=True)
    transition_history = models.JSONField(default=list, editable=False)
    asset_version_snapshot = models.PositiveBigIntegerField(default=1)
    posting_idempotency_key = models.CharField(max_length=255, null=True, blank=True)
    posting_request_fingerprint = models.CharField(max_length=64, null=True, blank=True)

    objects = DepreciationLineQuerySet.as_manager()

    class Meta:
        db_table = "fixed_asset_depreciation_lines"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "schedule", "sequence"), name="fa_line_sequence_uniq"),
            models.UniqueConstraint(fields=("tenant_id", "asset", "period_start", "period_end", "schedule"), name="fa_line_period_uniq"),
            models.UniqueConstraint(fields=("tenant_id", "journal_entry_id"), condition=Q(journal_entry_id__isnull=False), name="fa_line_journal_uniq"),
            models.CheckConstraint(condition=Q(period_start__lte=F("period_end")), name="fa_line_period_order"),
            models.CheckConstraint(condition=Q(opening_net_book_value__gte=0, depreciation_amount__gte=0, accumulated_depreciation__gte=0, closing_net_book_value__gte=0), name="fa_line_money_nonnegative"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "asset", "period_end", "status"), name="fa_line_asset_period_idx"),
            models.Index(fields=("tenant_id", "schedule", "sequence"), name="fa_line_sched_seq_idx"),
            models.Index(fields=("tenant_id", "status", "period_end"), name="fa_line_status_period_idx"),
            models.Index(fields=("tenant_id", "journal_entry_id"), name="fa_line_journal_idx"),
        ]

    def clean(self) -> None:
        self.book_code = self.book_code.strip().lower()
        for field in ("opening_net_book_value", "depreciation_amount", "accumulated_depreciation", "closing_net_book_value"):
            value = getattr(self, field, None)
            if value is not None:
                setattr(self, field, money(value))
        if self.schedule_id and self.tenant_id and not DepreciationSchedule.objects.for_tenant(self.tenant_id).filter(pk=self.schedule_id).exists():
            raise ValidationError({"schedule": "Schedule was not found for this tenant."}, code="cross_tenant_reference")
        if self.asset_id and self.tenant_id and not FixedAsset.objects.for_tenant(self.tenant_id).filter(pk=self.asset_id).exists():
            raise ValidationError({"asset": "Asset was not found for this tenant."}, code="cross_tenant_reference")
        if self.schedule_id and self.asset_id:
            schedule = DepreciationSchedule.objects.filter(pk=self.schedule_id, tenant_id=self.tenant_id).only("asset_id", "residual_value", "book_code").first()
            if schedule and (schedule.asset_id != self.asset_id or schedule.book_code != self.book_code):
                raise ValidationError("Line, schedule, asset, and book must match.", code="cross_tenant_reference")
            if schedule and self.closing_net_book_value < schedule.residual_value:
                raise ValidationError({"closing_net_book_value": "Closing value cannot fall below residual value."})
        if not self._state.adding and self.pk:
            prior = type(self)._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).first()
            if prior and prior.status == LineStatus.POSTED:
                raise PostedLineMutationError("Posted depreciation lines are immutable.", code="posted_line_immutable")

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.status == LineStatus.POSTED:
            raise PostedLineMutationError("Posted depreciation lines are immutable.", code="posted_line_immutable")
        return super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.schedule_id} #{self.sequence}"


class ImmutableTransactionError(ValidationError):
    pass


class AssetTransactionQuerySet(TenantQuerySet):
    def update(self, **kwargs: Any) -> int:
        raise ImmutableTransactionError("Asset transactions are append-only.", code="append_only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableTransactionError("Asset transactions are append-only.", code="append_only")


@tenancy_scope(TENANT_SCOPED)
class AssetTransaction(TenantScopedModel, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(FixedAsset, on_delete=models.PROTECT, related_name="transactions")
    book_code = models.CharField(max_length=32, default=PRIMARY_BOOK)
    transaction_type = models.CharField(max_length=24, choices=TransactionType.choices)
    effective_date = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3)
    opening_net_book_value = models.DecimalField(max_digits=15, decimal_places=2)
    closing_net_book_value = models.DecimalField(max_digits=15, decimal_places=2)
    from_location = models.CharField(max_length=255, blank=True)
    to_location = models.CharField(max_length=255, blank=True)
    from_cost_center = models.CharField(max_length=100, blank=True)
    to_cost_center = models.CharField(max_length=100, blank=True)
    journal_entry_id = models.UUIDField(null=True, blank=True)
    source_type = models.CharField(max_length=64)
    source_id = models.UUIDField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255)
    request_fingerprint = models.CharField(max_length=64)
    actor_id = models.CharField(max_length=255)
    correlation_id = models.CharField(max_length=64)
    metadata = models.JSONField(default=dict, blank=True)

    objects = AssetTransactionQuerySet.as_manager()

    class Meta:
        db_table = "fixed_asset_transactions"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="fa_txn_idempotency_uniq"),
            models.CheckConstraint(condition=Q(amount__gte=0, opening_net_book_value__gte=0, closing_net_book_value__gte=0), name="fa_txn_money_nonnegative"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "asset", "effective_date", "created_at"), name="fa_txn_asset_date_idx"),
            models.Index(fields=("tenant_id", "transaction_type", "effective_date"), name="fa_txn_type_date_idx"),
            models.Index(fields=("tenant_id", "correlation_id"), name="fa_txn_correlation_idx"),
            models.Index(fields=("tenant_id", "journal_entry_id"), name="fa_txn_journal_idx"),
            models.Index(fields=("tenant_id", "asset", "book_code"), name="fa_txn_asset_book_idx"),
        ]

    def clean(self) -> None:
        self.currency = self.currency.strip().upper()
        self.book_code = self.book_code.strip().lower()
        for field in ("amount", "opening_net_book_value", "closing_net_book_value"):
            value = getattr(self, field, None)
            if value is not None:
                setattr(self, field, money(value))
        if self.asset_id and self.tenant_id and not FixedAsset.objects.for_tenant(self.tenant_id).filter(pk=self.asset_id).exists():
            raise ValidationError({"asset": "Asset was not found for this tenant."}, code="cross_tenant_reference")

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableTransactionError("Asset transactions are append-only.", code="append_only")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableTransactionError("Asset transactions are append-only.", code="append_only")

    def __str__(self) -> str:
        return f"{self.asset_id} {self.transaction_type} {self.effective_date}"


ASSET_STATE_MACHINE = StateMachine(
    name="fixed_assets.asset",
    model=FixedAsset,
    states=AssetStatus.values,
    terminal_states=(AssetStatus.DISPOSED,),
    transitions=(
        {"command": "capitalize", "source": AssetStatus.DRAFT, "target": AssetStatus.ACTIVE},
        {"command": "fully_depreciate", "source": AssetStatus.ACTIVE, "target": AssetStatus.FULLY_DEPRECIATED},
        {"command": "dispose", "source": AssetStatus.ACTIVE, "target": AssetStatus.DISPOSED},
        {"command": "dispose", "source": AssetStatus.FULLY_DEPRECIATED, "target": AssetStatus.DISPOSED},
    ),
)

SCHEDULE_STATE_MACHINE = StateMachine(
    name="fixed_assets.schedule",
    model=DepreciationSchedule,
    states=ScheduleStatus.values,
    terminal_states=(ScheduleStatus.COMPLETED, ScheduleStatus.SUPERSEDED),
    transitions=(
        {"command": "calculate", "source": ScheduleStatus.DRAFT, "target": ScheduleStatus.CALCULATED},
        {"command": "activate", "source": ScheduleStatus.CALCULATED, "target": ScheduleStatus.ACTIVE},
        {"command": "complete", "source": ScheduleStatus.ACTIVE, "target": ScheduleStatus.COMPLETED},
        {"command": "supersede", "source": ScheduleStatus.DRAFT, "target": ScheduleStatus.SUPERSEDED},
        {"command": "supersede", "source": ScheduleStatus.CALCULATED, "target": ScheduleStatus.SUPERSEDED},
        {"command": "supersede", "source": ScheduleStatus.ACTIVE, "target": ScheduleStatus.SUPERSEDED},
    ),
)

LINE_STATE_MACHINE = StateMachine(
    name="fixed_assets.depreciation_line",
    model=DepreciationLine,
    states=LineStatus.values,
    terminal_states=(LineStatus.POSTED, LineStatus.VOID),
    transitions=(
        {"command": "post", "source": LineStatus.PLANNED, "target": LineStatus.POSTING},
        {"command": "confirm", "source": LineStatus.POSTING, "target": LineStatus.POSTED},
        {"command": "fail", "source": LineStatus.POSTING, "target": LineStatus.FAILED},
        {"command": "retry", "source": LineStatus.FAILED, "target": LineStatus.POSTING},
        {"command": "void", "source": LineStatus.PLANNED, "target": LineStatus.VOID},
        {"command": "void", "source": LineStatus.FAILED, "target": LineStatus.VOID},
    ),
)


__all__ = [
    "ASSET_STATE_MACHINE",
    "LINE_STATE_MACHINE",
    "SCHEDULE_STATE_MACHINE",
    "AssetCategory",
    "AssetStatus",
    "AssetTransaction",
    "DepreciationLine",
    "DepreciationMethod",
    "DepreciationSchedule",
    "FixedAsset",
    "ImmutableTransactionError",
    "LineStatus",
    "MONEY_QUANTUM",
    "PRIMARY_BOOK",
    "PostedLineMutationError",
    "ScheduleStatus",
    "TransactionType",
    "money",
]
