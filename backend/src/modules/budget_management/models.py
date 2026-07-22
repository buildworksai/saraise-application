"""Tenant-safe persistence models for budget planning and control.

Planning mutations belong in :mod:`services`; these models provide the final
line of defence for structural invariants and immutable audit evidence.
Cross-module identifiers deliberately remain UUID contracts rather than ORM
foreign keys so industry modules can extend the domain without coupling their
schema to the open-source core.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from src.core.tenancy import TenantScopedModel, TimestampedModel
from src.core.tenancy.models import TenantQuerySet


class BudgetType(models.TextChoices):
    OPERATING = "operating", "Operating"
    CAPITAL = "capital", "Capital"
    PROJECT = "project", "Project"
    DEPARTMENTAL = "departmental", "Departmental"


class BudgetStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING_APPROVAL = "pending_approval", "Pending approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    REVISION = "revision", "Revision"
    CLOSED = "closed", "Closed"


class PeriodType(models.TextChoices):
    ANNUAL = "annual", "Annual"
    MONTHLY = "monthly", "Monthly"
    QUARTERLY = "quarterly", "Quarterly"


class BudgetLineSource(models.TextChoices):
    MANUAL = "manual", "Manual"
    ACCOUNTING_SYNC = "accounting_sync", "Accounting sync"


class ApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class ApprovalDecisionStatus(models.TextChoices):
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class AlertType(models.TextChoices):
    OVER_BUDGET = "over_budget", "Over budget"
    APPROACHING_LIMIT = "approaching_limit", "Approaching limit"
    UNDERSPEND = "underspend", "Underspend"


class NotificationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    UNAVAILABLE = "unavailable", "Unavailable"


class CommitmentOperation(models.TextChoices):
    RECORD = "record", "Record"
    RELEASE = "release", "Release"


class AppendOnlyDomainError(ValidationError):
    """Raised when immutable budget evidence is changed or removed."""


class AppendOnlyQuerySet(TenantQuerySet):
    """Prevent bulk operations from bypassing append-only guarantees."""

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise AppendOnlyDomainError("Audit records are append-only.", code="append_only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise AppendOnlyDomainError("Audit records are append-only.", code="append_only")


class AppendOnlyTenantModel(TenantScopedModel):
    """Canonical UUID base for immutable, tenant-owned evidence."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AppendOnlyDomainError("Audit records are append-only.", code="append_only")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise AppendOnlyDomainError("Audit records are append-only.", code="append_only")


class MutableBudgetModel(TenantScopedModel, TimestampedModel):
    """Audit and soft-delete contract shared by mutable budget records."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.UUIDField()
    updated_by = models.UUIDField()
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.UUIDField(null=True, blank=True)

    class Meta:
        abstract = True


class Budget(MutableBudgetModel):
    """A governed budget container for one tenant-local fiscal period."""

    budget_code = models.CharField(max_length=50)
    budget_name = models.CharField(max_length=255)
    fiscal_year = models.PositiveSmallIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    budget_type = models.CharField(max_length=20, choices=BudgetType.choices, default=BudgetType.OPERATING)
    department_id = models.UUIDField(null=True, blank=True, db_index=True)
    project_id = models.UUIDField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=24, choices=BudgetStatus.choices, default=BudgetStatus.DRAFT)
    currency = models.CharField(max_length=3, default="USD")
    budget_ceiling = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    total_budget = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.UUIDField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.UUIDField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    class Meta:
        db_table = "budget_budgets"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "budget_code"),
                condition=Q(is_deleted=False),
                name="budget_tenant_code_live_uniq",
            ),
            models.UniqueConstraint(
                F("tenant_id"),
                F("fiscal_year"),
                Lower("budget_name"),
                condition=Q(is_deleted=False),
                name="budget_tenant_year_name_live_uniq",
            ),
            models.CheckConstraint(condition=Q(start_date__lte=F("end_date")), name="budget_date_order_ck"),
            models.CheckConstraint(
                condition=Q(budget_type__in=BudgetType.values),
                name="budget_type_valid_ck",
            ),
            models.CheckConstraint(
                condition=Q(status__in=BudgetStatus.values),
                name="budget_status_valid_ck",
            ),
            models.CheckConstraint(condition=Q(total_budget__gte=0), name="budget_total_nonnegative_ck"),
            models.CheckConstraint(
                condition=Q(budget_ceiling__isnull=True) | Q(budget_ceiling__gte=0),
                name="budget_ceiling_nonnegative_ck",
            ),
            models.CheckConstraint(
                condition=~Q(budget_type=BudgetType.DEPARTMENTAL) | Q(department_id__isnull=False),
                name="budget_department_required_ck",
            ),
            models.CheckConstraint(
                condition=~Q(budget_type=BudgetType.PROJECT) | Q(project_id__isnull=False),
                name="budget_project_required_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status__in=[BudgetStatus.APPROVED, BudgetStatus.CLOSED],
                        approved_at__isnull=False,
                        approved_by__isnull=False,
                    )
                    | Q(
                        ~Q(status__in=[BudgetStatus.APPROVED, BudgetStatus.CLOSED]),
                        approved_at__isnull=True,
                        approved_by__isnull=True,
                    )
                ),
                name="budget_approval_metadata_ck",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status=BudgetStatus.REJECTED)
                    | (
                        Q(rejected_at__isnull=False, rejected_by__isnull=False)
                        & ~Q(rejection_reason="")
                    )
                ),
                name="budget_rejection_metadata_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_deleted=False, deleted_at__isnull=True, deleted_by__isnull=True)
                    | Q(is_deleted=True, deleted_at__isnull=False, deleted_by__isnull=False)
                ),
                name="budget_soft_delete_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "fiscal_year", "status"], name="budget_tenant_year_status_idx"),
            models.Index(fields=["tenant_id", "budget_type", "fiscal_year"], name="budget_tenant_type_year_idx"),
            models.Index(fields=["tenant_id", "start_date", "end_date"], name="budget_tenant_dates_idx"),
            models.Index(fields=["tenant_id", "department_id", "fiscal_year"], name="budget_tenant_dept_year_idx"),
            models.Index(fields=["tenant_id", "project_id", "fiscal_year"], name="budget_tenant_proj_year_idx"),
            models.Index(fields=["tenant_id", "is_deleted", "updated_at"], name="budget_tenant_deleted_upd_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.budget_code} - {self.budget_name}"


class BudgetLine(MutableBudgetModel):
    """An account and period allocation within a budget."""

    budget = models.ForeignKey(Budget, on_delete=models.PROTECT, related_name="lines")
    account_id = models.UUIDField(null=True, blank=True, db_index=True)
    account_code = models.CharField(max_length=50)
    account_name = models.CharField(max_length=255, blank=True)
    period_type = models.CharField(max_length=12, choices=PeriodType.choices, default=PeriodType.ANNUAL)
    period_number = models.PositiveSmallIntegerField(default=1)
    budget_amount = models.DecimalField(max_digits=15, decimal_places=2)
    committed_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    actual_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    variance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    actuals_as_of = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=16, choices=BudgetLineSource.choices, default=BudgetLineSource.MANUAL)

    class Meta:
        db_table = "budget_lines"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "budget", "account_code", "period_type", "period_number"),
                condition=Q(is_deleted=False),
                name="budget_line_allocation_live_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(budget_amount__gte=0)
                    & Q(committed_amount__gte=0)
                    & Q(actual_amount__gte=0)
                ),
                name="budget_line_amounts_nonnegative_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(period_type=PeriodType.ANNUAL, period_number=1)
                    | Q(period_type=PeriodType.MONTHLY, period_number__gte=1, period_number__lte=12)
                    | Q(period_type=PeriodType.QUARTERLY, period_number__gte=1, period_number__lte=4)
                ),
                name="budget_line_period_number_ck",
            ),
            models.CheckConstraint(condition=Q(period_type__in=PeriodType.values), name="budget_line_period_type_ck"),
            models.CheckConstraint(condition=Q(source__in=BudgetLineSource.values), name="budget_line_source_ck"),
            models.CheckConstraint(
                condition=(
                    Q(is_deleted=False, deleted_at__isnull=True, deleted_by__isnull=True)
                    | Q(is_deleted=True, deleted_at__isnull=False, deleted_by__isnull=False)
                ),
                name="budget_line_soft_delete_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "budget", "is_deleted"], name="bud_line_tenant_budget_idx"),
            models.Index(
                fields=["tenant_id", "account_code", "period_type", "period_number"],
                name="bud_line_tenant_acct_per_idx",
            ),
            models.Index(fields=["tenant_id", "account_id"], name="budget_line_tenant_acct_id_idx"),
            models.Index(fields=["tenant_id", "actuals_as_of"], name="budget_line_tenant_actuals_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.budget.budget_code} - {self.account_code}"


class BudgetApproval(AppendOnlyTenantModel):
    """Append-only approval assignment and decision evidence."""

    budget = models.ForeignKey(Budget, on_delete=models.PROTECT, related_name="approvals")
    workflow_request_id = models.UUIDField(null=True, blank=True)
    approver_id = models.UUIDField(db_index=True)
    approval_level = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    decision_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    created_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "budget_approvals"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "budget", "approval_level", "approver_id"),
                name="budget_approval_assignment_uniq",
            ),
            models.CheckConstraint(condition=Q(approval_level__gte=1), name="budget_approval_level_ck"),
            models.CheckConstraint(condition=Q(status__in=ApprovalStatus.values), name="budget_approval_status_ck"),
            models.CheckConstraint(
                condition=(
                    ~Q(status__in=[ApprovalStatus.APPROVED, ApprovalStatus.REJECTED])
                    | Q(decision_at__isnull=False)
                ),
                name="budget_approval_decision_at_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status=ApprovalStatus.REJECTED) | ~Q(rejection_reason=""),
                name="budget_approval_rejection_reason_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "status", "approval_level", "created_at"],
                name="bud_appr_tenant_status_lvl_idx",
            ),
            models.Index(fields=["tenant_id", "approver_id", "status"], name="budget_appr_tenant_actor_idx"),
            models.Index(fields=["tenant_id", "budget", "approval_level"], name="budget_appr_tenant_budget_idx"),
        ]


class BudgetTransition(AppendOnlyTenantModel):
    """Append-only state-machine transition evidence."""

    budget = models.ForeignKey(Budget, on_delete=models.PROTECT, related_name="transitions")
    transition_key = models.CharField(max_length=255)
    command = models.CharField(max_length=32)
    from_state = models.CharField(max_length=24)
    to_state = models.CharField(max_length=24)
    actor_id = models.UUIDField()
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "budget_transitions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "budget", "transition_key"),
                name="budget_transition_key_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["tenant_id", "budget", "occurred_at"], name="budget_trans_tenant_budget_idx")
        ]


class BudgetApprovalDecision(AppendOnlyTenantModel):
    """Append-only terminal outcome for an immutable approval assignment."""

    approval = models.ForeignKey(BudgetApproval, on_delete=models.PROTECT, related_name="decisions")
    budget = models.ForeignKey(Budget, on_delete=models.PROTECT, related_name="approval_decisions")
    actor_id = models.UUIDField(db_index=True)
    status = models.CharField(max_length=16, choices=ApprovalDecisionStatus.choices)
    idempotency_key = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "budget_approval_decisions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "approval"),
                name="budget_approval_one_decision_uniq",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "budget", "idempotency_key"),
                name="budget_approval_decision_key_uniq",
            ),
            models.CheckConstraint(
                condition=Q(status__in=ApprovalDecisionStatus.values),
                name="budget_approval_decision_status_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status=ApprovalDecisionStatus.REJECTED) | ~Q(rejection_reason=""),
                name="budget_approval_decision_reason_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "budget", "decided_at"], name="bud_appr_dec_tenant_budget_idx"),
            models.Index(fields=["tenant_id", "actor_id", "decided_at"], name="bud_appr_dec_tenant_actor_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.approval_id:
            approval = self.approval
            if approval.tenant_id != self.tenant_id or approval.budget_id != self.budget_id:
                raise ValidationError("Approval decisions must use an assignment from the same tenant and budget.")
        if self.budget_id and self.budget.tenant_id != self.tenant_id:
            raise ValidationError("Approval decisions must use a budget from the same tenant.")


class BudgetCommitment(AppendOnlyTenantModel):
    """Idempotency evidence for commitment record and release operations.

    The source UUID plus provider idempotency key is the stable extension
    contract used by procurement and expense modules. Keeping this ledger
    append-only prevents an at-least-once delivery from double-counting.
    """

    budget_line = models.ForeignKey(BudgetLine, on_delete=models.PROTECT, related_name="commitment_events")
    source_id = models.UUIDField()
    idempotency_key = models.CharField(max_length=255)
    operation = models.CharField(max_length=12, choices=CommitmentOperation.choices)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "budget_commitments"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "budget_line", "source_id", "idempotency_key"),
                name="budget_commitment_idempotency_uniq",
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="budget_commitment_amount_positive_ck"),
            models.CheckConstraint(
                condition=Q(operation__in=CommitmentOperation.values),
                name="budget_commitment_operation_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "budget_line", "created_at"],
                name="budget_commit_tenant_line_idx",
            ),
            models.Index(fields=["tenant_id", "source_id"], name="bud_commit_tenant_source_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.budget_line_id and self.budget_line.tenant_id != self.tenant_id:
            raise ValidationError("Commitment evidence must use a line from the same tenant.")


class VarianceAlertQuerySet(TenantQuerySet):
    """Allow only the explicitly mutable alert delivery/acknowledgement fields."""

    _MUTABLE_FIELDS = {
        "notification_status",
        "notification_job_id",
        "acknowledged_at",
        "acknowledged_by",
    }

    def update(self, **kwargs: Any) -> int:
        if set(kwargs) - self._MUTABLE_FIELDS:
            raise AppendOnlyDomainError("Variance alert snapshots are immutable.", code="immutable_alert")
        return super().update(**kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        raise AppendOnlyDomainError("Variance alerts cannot be deleted.", code="immutable_alert")


class VarianceAlert(TenantScopedModel):
    """Immutable variance snapshot with mutable notification/ack state."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    budget = models.ForeignKey(Budget, on_delete=models.PROTECT, related_name="variance_alerts")
    budget_line = models.ForeignKey(BudgetLine, on_delete=models.PROTECT, related_name="variance_alerts")
    alert_type = models.CharField(max_length=24, choices=AlertType.choices)
    threshold_percentage = models.DecimalField(max_digits=7, decimal_places=2)
    variance_percentage = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    budget_amount = models.DecimalField(max_digits=15, decimal_places=2)
    actual_amount = models.DecimalField(max_digits=15, decimal_places=2)
    committed_amount = models.DecimalField(max_digits=15, decimal_places=2)
    alert_date = models.DateField()
    notification_status = models.CharField(
        max_length=16,
        choices=NotificationStatus.choices,
        default=NotificationStatus.PENDING,
    )
    notification_job_id = models.UUIDField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = VarianceAlertQuerySet.as_manager()

    class Meta:
        db_table = "budget_variance_alerts"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "budget_line", "alert_type", "threshold_percentage", "alert_date"),
                name="budget_alert_dedup_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(threshold_percentage__gte=0)
                    & Q(budget_amount__gte=0)
                    & Q(actual_amount__gte=0)
                    & Q(committed_amount__gte=0)
                ),
                name="budget_alert_amounts_nonnegative_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(acknowledged_at__isnull=True, acknowledged_by__isnull=True)
                    | Q(acknowledged_at__isnull=False, acknowledged_by__isnull=False)
                ),
                name="budget_alert_ack_pair_ck",
            ),
            models.CheckConstraint(condition=Q(alert_type__in=AlertType.values), name="budget_alert_type_ck"),
            models.CheckConstraint(
                condition=Q(notification_status__in=NotificationStatus.values),
                name="budget_alert_notify_status_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "alert_type", "alert_date"], name="bud_alert_tenant_type_date_idx"),
            models.Index(fields=["tenant_id", "budget", "alert_date"], name="budget_alert_tenant_budget_idx"),
            models.Index(
                fields=["tenant_id", "notification_status", "created_at"],
                name="budget_alert_tenant_notify_idx",
            ),
            models.Index(fields=["tenant_id", "acknowledged_at"], name="budget_alert_tenant_ack_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            original = type(self).objects.only(
                "budget_id",
                "budget_line_id",
                "alert_type",
                "threshold_percentage",
                "variance_percentage",
                "budget_amount",
                "actual_amount",
                "committed_amount",
                "alert_date",
                "created_at",
            ).get(pk=self.pk)
            immutable = (
                "budget_id",
                "budget_line_id",
                "alert_type",
                "threshold_percentage",
                "variance_percentage",
                "budget_amount",
                "actual_amount",
                "committed_amount",
                "alert_date",
                "created_at",
            )
            if any(getattr(self, field) != getattr(original, field) for field in immutable):
                raise AppendOnlyDomainError("Variance alert snapshots are immutable.", code="immutable_alert")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise AppendOnlyDomainError("Variance alerts cannot be deleted.", code="immutable_alert")
