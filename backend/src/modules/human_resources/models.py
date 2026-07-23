"""Tenant-owned persistence for the open-source Human Resources core.

The database constraints in this module protect row-local invariants. Graph,
overlap, and cross-tenant invariants are additionally checked by ``clean`` and
by the locking service layer because they span multiple rows.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

from src.core.tenancy import TenantQuerySet, TenantScopedModel, TimestampedModel


def generate_uuid() -> str:
    """Preserve the callable imported by the immutable v1 migration."""

    return str(uuid.uuid4())


class EmploymentType(models.TextChoices):
    FULL_TIME = "full_time", "Full time"
    PART_TIME = "part_time", "Part time"
    CONTRACTOR = "contractor", "Contractor"
    TEMPORARY = "temporary", "Temporary"


class EmploymentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ON_LEAVE = "on_leave", "On leave"
    INACTIVE = "inactive", "Inactive"
    TERMINATED = "terminated", "Terminated"


class AttendanceStatus(models.TextChoices):
    PRESENT = "present", "Present"
    ABSENT = "absent", "Absent"
    LATE = "late", "Late"
    HALF_DAY = "half_day", "Half day"
    ON_LEAVE = "on_leave", "On leave"


class AttendanceSource(models.TextChoices):
    MANUAL = "manual", "Manual"
    CLOCK = "clock", "Clock"
    IMPORT = "import", "Import"


class LeaveType(models.TextChoices):
    ANNUAL = "annual", "Annual leave"
    SICK = "sick", "Sick leave"
    PERSONAL = "personal", "Personal leave"
    MATERNITY = "maternity", "Maternity leave"
    PATERNITY = "paternity", "Paternity leave"
    UNPAID = "unpaid", "Unpaid leave"


class LeaveRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class HRQuerySet(TenantQuerySet):
    """Default visible HR rows, with an explicit tenant boundary."""

    def alive(self) -> "HRQuerySet":
        return self.filter(deleted_at__isnull=True)

    def for_tenant(self, tenant_id: uuid.UUID) -> "HRQuerySet":
        return self.filter(tenant_id=tenant_id, deleted_at__isnull=True)


class VisibleHRManager(models.Manager.from_queryset(HRQuerySet)):  # type: ignore[misc]
    """Hide archived rows from ordinary application reads."""

    def get_queryset(self) -> HRQuerySet:
        return super().get_queryset().filter(deleted_at__isnull=True)


class HRBaseModel(TenantScopedModel, TimestampedModel):
    """Common tenant, ownership, audit, and soft-archive contract."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.CharField(max_length=255)
    updated_by = models.CharField(max_length=255)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True, editable=False)
    deleted_by = models.CharField(max_length=255, blank=True, default="", editable=False)

    objects = VisibleHRManager()
    all_objects = TenantQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError(
            "Hard deletion is forbidden; use the tenant-scoped archive service.",
            code="hard_delete_forbidden",
        )


def _validate_same_tenant(instance: HRBaseModel, relation_name: str) -> None:
    relation_id = getattr(instance, f"{relation_name}_id", None)
    if relation_id is None or instance.tenant_id is None:
        return
    field = instance._meta.get_field(relation_name)
    related_model = field.remote_field.model
    if not related_model.objects.for_tenant(instance.tenant_id).filter(pk=relation_id).exists():
        raise ValidationError(
            {relation_name: "The referenced record was not found in this tenant."},
            code="cross_tenant_reference",
        )


class Department(HRBaseModel):
    """An organizational unit in a tenant-bounded acyclic hierarchy."""

    department_code = models.CharField(max_length=50)
    department_name = models.CharField(max_length=255)
    parent_department = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    manager = models.ForeignKey(
        "Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_departments",
    )
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "hr_departments"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "department_code"),
                condition=Q(deleted_at__isnull=True),
                name="hr_dept_live_code_uniq",
            ),
            models.CheckConstraint(
                condition=Q(parent_department__isnull=True) | ~Q(parent_department=F("id")),
                name="hr_dept_not_self_parent_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "department_code"), name="hr_dept_t_code_idx"),
            models.Index(fields=("tenant_id", "department_name"), name="hr_dept_t_name_idx"),
            models.Index(fields=("tenant_id", "parent_department"), name="hr_dept_t_parent_idx"),
            models.Index(fields=("tenant_id", "manager"), name="hr_dept_t_manager_idx"),
            models.Index(fields=("tenant_id", "is_active", "deleted_at"), name="hr_dept_t_active_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_same_tenant(self, "parent_department")
        _validate_same_tenant(self, "manager")
        if self.manager_id:
            manager = Employee.objects.for_tenant(self.tenant_id).filter(pk=self.manager_id).first()
            if manager is None or manager.employment_status not in {
                EmploymentStatus.ACTIVE,
                EmploymentStatus.ON_LEAVE,
            }:
                raise ValidationError({"manager": "The department manager must be an active employee."})
        seen = {self.pk}
        parent_id = self.parent_department_id
        for _ in range(100):
            if parent_id is None:
                break
            if parent_id in seen:
                raise ValidationError({"parent_department": "Department hierarchy cannot contain a cycle."})
            seen.add(parent_id)
            parent_id = (
                Department.objects.for_tenant(self.tenant_id)
                .filter(pk=parent_id)
                .values_list("parent_department_id", flat=True)
                .first()
            )
        else:
            raise ValidationError({"parent_department": "Department hierarchy exceeds the supported depth."})

    def __str__(self) -> str:
        return f"{self.department_code} - {self.department_name}"


class Employee(HRBaseModel):
    """A worker record with a governed, auditable lifecycle."""

    employee_number = models.CharField(max_length=50)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=255)
    phone = models.CharField(max_length=50, blank=True, default="")
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="employees",
    )
    manager = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="direct_reports",
    )
    position = models.CharField(max_length=100, blank=True, default="")
    hire_date = models.DateField()
    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME,
    )
    employment_status = models.CharField(
        max_length=20,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
        editable=False,
    )
    is_active = models.BooleanField(default=True, editable=False)
    termination_date = models.DateField(null=True, blank=True, editable=False)
    termination_reason = models.TextField(blank=True, default="", editable=False)
    transition_history = models.JSONField(default=list, blank=True, editable=False)

    class Meta:
        db_table = "hr_employees"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "employee_number"),
                condition=Q(deleted_at__isnull=True),
                name="hr_emp_live_number_uniq",
            ),
            models.UniqueConstraint(
                Lower("email"),
                F("tenant_id"),
                condition=Q(deleted_at__isnull=True),
                name="hr_emp_live_email_ci_uniq",
            ),
            models.CheckConstraint(
                condition=Q(manager__isnull=True) | ~Q(manager=F("id")),
                name="hr_emp_not_self_manager_ck",
            ),
            models.CheckConstraint(
                condition=(Q(employment_status=EmploymentStatus.TERMINATED, termination_date__isnull=False))
                | (~Q(employment_status=EmploymentStatus.TERMINATED) & Q(termination_date__isnull=True)),
                name="hr_emp_termination_state_ck",
            ),
            models.CheckConstraint(
                condition=Q(termination_date__isnull=True) | Q(termination_date__gte=F("hire_date")),
                name="hr_emp_termination_date_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(employment_status__in=(EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE), is_active=True)
                    | Q(employment_status__in=(EmploymentStatus.INACTIVE, EmploymentStatus.TERMINATED), is_active=False)
                ),
                name="hr_emp_active_sync_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "employee_number"), name="hr_emp_t_number_idx"),
            models.Index(fields=("tenant_id", "email"), name="hr_emp_t_email_idx"),
            models.Index(fields=("tenant_id", "department", "employment_status"), name="hr_emp_t_dept_status_idx"),
            models.Index(fields=("tenant_id", "manager", "employment_status"), name="hr_emp_t_mgr_status_idx"),
            models.Index(fields=("tenant_id", "hire_date"), name="hr_emp_t_hire_idx"),
            models.Index(fields=("tenant_id", "employment_status", "deleted_at"), name="hr_emp_t_status_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_same_tenant(self, "department")
        _validate_same_tenant(self, "manager")
        expected_active = self.employment_status in {EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE}
        if self.is_active != expected_active:
            raise ValidationError({"is_active": "is_active must match employment_status."})
        if self.employment_status == EmploymentStatus.TERMINATED:
            if self.termination_date is None:
                raise ValidationError({"termination_date": "Termination date is required."})
        elif self.termination_date is not None:
            raise ValidationError({"termination_date": "Only terminated employees can have a termination date."})
        if self.termination_date and self.hire_date and self.termination_date < self.hire_date:
            raise ValidationError({"termination_date": "Termination date cannot precede hire date."})
        seen = {self.pk}
        manager_id = self.manager_id
        for _ in range(100):
            if manager_id is None:
                break
            if manager_id in seen:
                raise ValidationError({"manager": "Reporting lines cannot contain a cycle."})
            seen.add(manager_id)
            manager_id = (
                Employee.objects.for_tenant(self.tenant_id)
                .filter(pk=manager_id)
                .values_list("manager_id", flat=True)
                .first()
            )
        else:
            raise ValidationError({"manager": "Reporting line exceeds the supported depth."})

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self) -> str:
        return f"{self.employee_number} - {self.full_name}"


class Attendance(HRBaseModel):
    """One employee's attendance facts for one tenant-local calendar date."""

    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="attendances")
    attendance_date = models.DateField()
    check_in_time = models.DateTimeField(null=True, blank=True)
    check_out_time = models.DateTimeField(null=True, blank=True)
    hours_worked = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    source = models.CharField(max_length=20, choices=AttendanceSource.choices, default=AttendanceSource.MANUAL)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "hr_attendances"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "employee", "attendance_date"),
                condition=Q(deleted_at__isnull=True),
                name="hr_att_live_employee_date_uq",
            ),
            models.CheckConstraint(
                condition=Q(hours_worked__gte=0) & Q(hours_worked__lte=24),
                name="hr_att_hours_range_ck",
            ),
            models.CheckConstraint(
                condition=Q(check_in_time__isnull=True)
                | Q(check_out_time__isnull=True)
                | Q(check_out_time__gt=F("check_in_time")),
                name="hr_att_clock_order_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=(AttendanceStatus.ABSENT, AttendanceStatus.ON_LEAVE))
                | (Q(hours_worked=0) & Q(check_in_time__isnull=True) & Q(check_out_time__isnull=True)),
                name="hr_att_nonwork_zero_ck",
            ),
            models.CheckConstraint(
                condition=~Q(source=AttendanceSource.CLOCK) | Q(check_in_time__isnull=False),
                name="hr_att_clock_has_in_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "employee", "attendance_date"), name="hr_att_t_emp_date_idx"),
            models.Index(fields=("tenant_id", "attendance_date", "status"), name="hr_att_t_date_status_idx"),
            models.Index(fields=("tenant_id", "status", "deleted_at"), name="hr_att_t_status_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_same_tenant(self, "employee")
        if self.hours_worked < 0 or self.hours_worked > 24:
            raise ValidationError({"hours_worked": "Hours worked must be between 0 and 24."})
        if self.check_in_time and self.check_out_time and self.check_out_time <= self.check_in_time:
            raise ValidationError({"check_out_time": "Check-out must be after check-in."})
        for field_name in ("check_in_time", "check_out_time"):
            value = getattr(self, field_name)
            if value is not None:
                if timezone.is_naive(value):
                    raise ValidationError({field_name: "Clock timestamps must include a timezone offset."})
                if timezone.localtime(value).date() != self.attendance_date:
                    raise ValidationError({field_name: "Clock timestamp does not match attendance date."})
        if self.status in {AttendanceStatus.ABSENT, AttendanceStatus.ON_LEAVE}:
            if self.hours_worked != 0 or self.check_in_time or self.check_out_time:
                raise ValidationError({"status": "Absent and on-leave records cannot contain worked time."})
        if self.source == AttendanceSource.CLOCK and self.check_in_time is None:
            raise ValidationError({"check_in_time": "Clock-sourced attendance requires check-in."})

    def __str__(self) -> str:
        return f"{self.employee_id} - {self.attendance_date}"


class LeaveBalance(HRBaseModel):
    """An explicit, versioned leave allocation for a bounded period."""

    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="leave_balances")
    leave_type = models.CharField(max_length=20, choices=LeaveType.choices)
    period_start = models.DateField()
    period_end = models.DateField()
    entitled_days = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))
    carried_days = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))
    used_days = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"), editable=False)
    pending_days = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"), editable=False)
    adjustment_version = models.PositiveIntegerField(default=1, editable=False)
    last_adjusted_by = models.CharField(max_length=255, blank=True, default="", editable=False)
    adjustment_note = models.TextField(blank=True, default="", editable=False)

    class Meta:
        db_table = "hr_leave_balances"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "employee", "leave_type", "period_start", "period_end"),
                condition=Q(deleted_at__isnull=True),
                name="hr_bal_live_period_uniq",
            ),
            models.CheckConstraint(condition=Q(period_end__gte=F("period_start")), name="hr_bal_period_order_ck"),
            models.CheckConstraint(
                condition=Q(entitled_days__gte=0)
                & Q(carried_days__gte=0)
                & Q(used_days__gte=0)
                & Q(pending_days__gte=0),
                name="hr_bal_amounts_nonneg_ck",
            ),
            models.CheckConstraint(
                condition=Q(used_days__lte=F("entitled_days") + F("carried_days") - F("pending_days")),
                name="hr_bal_capacity_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "employee", "leave_type", "period_start"), name="hr_bal_t_emp_type_idx"),
            models.Index(fields=("tenant_id", "period_end"), name="hr_bal_t_end_idx"),
            models.Index(fields=("tenant_id", "leave_type", "deleted_at"), name="hr_bal_t_type_idx"),
        ]

    @property
    def remaining_days(self) -> Decimal:
        return self.entitled_days + self.carried_days - self.used_days - self.pending_days

    def clean(self) -> None:
        super().clean()
        _validate_same_tenant(self, "employee")
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValidationError({"period_end": "Period end cannot precede period start."})
        amounts = (self.entitled_days, self.carried_days, self.used_days, self.pending_days)
        if any(value < 0 for value in amounts):
            raise ValidationError("Leave balance amounts cannot be negative.")
        if self.used_days + self.pending_days > self.entitled_days + self.carried_days:
            raise ValidationError("Used and pending leave cannot exceed the allocation.")
        if self.employee_id and self.period_start and self.period_end:
            overlap = LeaveBalance.objects.for_tenant(self.tenant_id).filter(
                employee_id=self.employee_id,
                leave_type=self.leave_type,
                period_start__lte=self.period_end,
                period_end__gte=self.period_start,
            )
            if self.pk:
                overlap = overlap.exclude(pk=self.pk)
            if overlap.exists():
                raise ValidationError({"period_start": "Leave balance periods cannot overlap."})

    def __str__(self) -> str:
        return f"{self.employee_id} - {self.leave_type} ({self.period_start} to {self.period_end})"


class LeaveRequest(HRBaseModel):
    """A balance-backed, governed request for inclusive calendar-day leave."""

    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="leave_requests")
    leave_balance = models.ForeignKey(LeaveBalance, on_delete=models.PROTECT, related_name="requests")
    leave_type = models.CharField(max_length=20, choices=LeaveType.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    days_requested = models.DecimalField(max_digits=7, decimal_places=2)
    reason = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=LeaveRequestStatus.choices,
        default=LeaveRequestStatus.PENDING,
        editable=False,
    )
    approved_by = models.CharField(max_length=255, blank=True, default="", editable=False)
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)
    rejection_reason = models.TextField(blank=True, default="", editable=False)
    cancelled_by = models.CharField(max_length=255, blank=True, default="", editable=False)
    cancelled_at = models.DateTimeField(null=True, blank=True, editable=False)
    transition_history = models.JSONField(default=list, blank=True, editable=False)

    class Meta:
        db_table = "hr_leave_requests"
        constraints = [
            models.CheckConstraint(condition=Q(end_date__gte=F("start_date")), name="hr_req_date_order_ck"),
            models.CheckConstraint(condition=Q(days_requested__gt=0), name="hr_req_days_positive_ck"),
            models.CheckConstraint(
                condition=~Q(status=LeaveRequestStatus.APPROVED)
                | (Q(approved_by__gt="") & Q(approved_at__isnull=False)),
                name="hr_req_approved_meta_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status=LeaveRequestStatus.REJECTED) | Q(rejection_reason__gt=""),
                name="hr_req_rejected_meta_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status=LeaveRequestStatus.CANCELLED)
                | (Q(cancelled_by__gt="") & Q(cancelled_at__isnull=False)),
                name="hr_req_cancelled_meta_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "employee", "start_date"), name="hr_req_t_emp_start_idx"),
            models.Index(fields=("tenant_id", "employee", "status"), name="hr_req_t_emp_status_idx"),
            models.Index(fields=("tenant_id", "status", "start_date"), name="hr_req_t_status_start_idx"),
            models.Index(fields=("tenant_id", "leave_type", "start_date", "end_date"), name="hr_req_t_type_dates_idx"),
            models.Index(fields=("tenant_id", "created_at"), name="hr_req_t_created_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_same_tenant(self, "employee")
        _validate_same_tenant(self, "leave_balance")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date cannot precede start date."})
        if self.days_requested <= 0:
            raise ValidationError({"days_requested": "Requested days must be positive."})
        if self.leave_balance_id:
            balance = LeaveBalance.objects.for_tenant(self.tenant_id).filter(pk=self.leave_balance_id).first()
            if balance and (
                balance.employee_id != self.employee_id
                or balance.leave_type != self.leave_type
                or self.start_date < balance.period_start
                or self.end_date > balance.period_end
            ):
                raise ValidationError({"leave_balance": "Balance does not cover this employee, type, and period."})
        if self.status == LeaveRequestStatus.APPROVED and (not self.approved_by or not self.approved_at):
            raise ValidationError({"approved_by": "Approved requests require approval metadata."})
        if self.status == LeaveRequestStatus.REJECTED and not self.rejection_reason.strip():
            raise ValidationError({"rejection_reason": "Rejected requests require a reason."})
        if self.status == LeaveRequestStatus.CANCELLED and (not self.cancelled_by or not self.cancelled_at):
            raise ValidationError({"cancelled_by": "Cancelled requests require cancellation metadata."})
        if (
            self.employee_id
            and self.start_date
            and self.end_date
            and self.status
            in {
                LeaveRequestStatus.PENDING,
                LeaveRequestStatus.APPROVED,
            }
        ):
            overlap = LeaveRequest.objects.for_tenant(self.tenant_id).filter(
                employee_id=self.employee_id,
                status__in=(LeaveRequestStatus.PENDING, LeaveRequestStatus.APPROVED),
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            )
            if self.pk:
                overlap = overlap.exclude(pk=self.pk)
            if overlap.exists():
                raise ValidationError({"start_date": "Leave requests cannot overlap."})

    def __str__(self) -> str:
        return f"{self.employee_id} - {self.leave_type} ({self.start_date} to {self.end_date})"


class HumanResourcesConfiguration(TenantScopedModel, TimestampedModel):
    """The active, tenant-owned HR policy document for one environment."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.CharField(max_length=32, default="default")
    version = models.PositiveIntegerField(default=1, editable=False)
    document = models.JSONField()
    updated_by = models.CharField(max_length=255, editable=False)
    actor_identifier_max_length = models.PositiveSmallIntegerField(editable=False)
    idempotency_key_max_length = models.PositiveSmallIntegerField(editable=False)
    hierarchy_max_depth = models.PositiveSmallIntegerField(editable=False)
    reporting_tree_max_depth = models.PositiveSmallIntegerField(editable=False)
    department_tree_max_nodes = models.PositiveIntegerField(editable=False)
    max_hours_per_day = models.DecimalField(max_digits=4, decimal_places=2, editable=False)

    objects = TenantQuerySet.as_manager()

    class Meta:
        db_table = "hr_configurations"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "environment"),
                name="hr_config_tenant_environment_uq",
            ),
            models.CheckConstraint(condition=Q(version__gte=1), name="hr_config_version_positive_ck"),
            models.CheckConstraint(condition=~Q(environment=""), name="hr_config_environment_nonempty_ck"),
            models.CheckConstraint(
                condition=Q(actor_identifier_max_length__gte=32) & Q(actor_identifier_max_length__lte=1024),
                name="hr_config_actor_limit_safe_ck",
            ),
            models.CheckConstraint(
                condition=Q(idempotency_key_max_length__gte=16) & Q(idempotency_key_max_length__lte=1024),
                name="hr_config_idem_limit_safe_ck",
            ),
            models.CheckConstraint(
                condition=Q(hierarchy_max_depth__gte=1) & Q(hierarchy_max_depth__lte=500),
                name="hr_config_hierarchy_depth_safe_ck",
            ),
            models.CheckConstraint(
                condition=Q(reporting_tree_max_depth__gte=1) & Q(reporting_tree_max_depth__lte=100),
                name="hr_config_reporting_depth_safe_ck",
            ),
            models.CheckConstraint(
                condition=Q(department_tree_max_nodes__gte=1) & Q(department_tree_max_nodes__lte=10000),
                name="hr_config_tree_nodes_safe_ck",
            ),
            models.CheckConstraint(
                condition=Q(max_hours_per_day__gt=0) & Q(max_hours_per_day__lte=24),
                name="hr_config_hours_safe_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "environment"), name="hr_config_t_env_idx"),
            models.Index(fields=("tenant_id", "version"), name="hr_config_t_version_idx"),
        ]


class HumanResourcesConfigurationVersion(TenantScopedModel):
    """Immutable configuration snapshot used for history and rollback."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(
        HumanResourcesConfiguration,
        on_delete=models.PROTECT,
        related_name="versions",
    )
    environment = models.CharField(max_length=32)
    version = models.PositiveIntegerField()
    document = models.JSONField()
    created_by = models.CharField(max_length=255)
    correlation_id = models.CharField(max_length=255)
    change_reason = models.CharField(max_length=500)
    rolled_back_from_version = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantQuerySet.as_manager()

    class Meta:
        db_table = "hr_configuration_versions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "environment", "version"),
                name="hr_config_version_t_env_version_uq",
            ),
            models.CheckConstraint(condition=Q(version__gte=1), name="hr_config_snapshot_version_positive_ck"),
            models.CheckConstraint(
                condition=Q(rolled_back_from_version__isnull=True) | Q(rolled_back_from_version__gte=1),
                name="hr_config_rollback_version_positive_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "environment", "-version"), name="hr_cfgver_t_env_ver_idx"),
            models.Index(fields=("tenant_id", "created_at"), name="hr_cfgver_t_created_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Configuration versions are immutable.", code="immutable_configuration_version")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Configuration versions are immutable.", code="immutable_configuration_version")


class HumanResourcesConfigurationAudit(TenantScopedModel):
    """Append-only who/what/when record for every configuration mutation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(
        HumanResourcesConfiguration,
        on_delete=models.PROTECT,
        related_name="audit_records",
    )
    environment = models.CharField(max_length=32)
    version = models.PositiveIntegerField()
    action = models.CharField(max_length=32)
    actor_id = models.CharField(max_length=255)
    correlation_id = models.CharField(max_length=255)
    idempotency_key = models.CharField(max_length=1024)
    request_fingerprint = models.CharField(max_length=64)
    before_document = models.JSONField(null=True)
    after_document = models.JSONField()
    change_reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantQuerySet.as_manager()

    class Meta:
        db_table = "hr_configuration_audits"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "environment", "idempotency_key"),
                name="hr_cfgaudit_t_env_idempotency_uq",
            ),
            models.CheckConstraint(condition=Q(version__gte=1), name="hr_cfgaudit_version_positive_ck"),
            models.CheckConstraint(condition=~Q(action=""), name="hr_cfgaudit_action_nonempty_ck"),
            models.CheckConstraint(condition=~Q(actor_id=""), name="hr_cfgaudit_actor_nonempty_ck"),
            models.CheckConstraint(condition=~Q(correlation_id=""), name="hr_cfgaudit_correlation_nonempty_ck"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "environment", "-version"), name="hr_cfgaudit_t_env_ver_idx"),
            models.Index(fields=("tenant_id", "correlation_id"), name="hr_cfgaudit_t_corr_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Configuration audit records are immutable.", code="immutable_configuration_audit")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Configuration audit records are immutable.", code="immutable_configuration_audit")


class HumanResourcesMutationCommand(TenantScopedModel):
    """Durable tenant-scoped replay record for every successful API mutation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(max_length=1024)
    request_fingerprint = models.CharField(max_length=64)
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=512)
    actor_id = models.CharField(max_length=255)
    correlation_id = models.CharField(max_length=255)
    response_status = models.PositiveSmallIntegerField(null=True, editable=False)
    response_body = models.JSONField(null=True, editable=False)
    completed_at = models.DateTimeField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantQuerySet.as_manager()

    class Meta:
        db_table = "hr_mutation_commands"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"),
                name="hr_mutcmd_tenant_idempotency_uq",
            ),
            models.CheckConstraint(condition=~Q(idempotency_key=""), name="hr_mutcmd_key_nonempty_ck"),
            models.CheckConstraint(condition=~Q(request_fingerprint=""), name="hr_mutcmd_fingerprint_nonempty_ck"),
            models.CheckConstraint(condition=~Q(actor_id=""), name="hr_mutcmd_actor_nonempty_ck"),
            models.CheckConstraint(condition=~Q(correlation_id=""), name="hr_mutcmd_correlation_nonempty_ck"),
            models.CheckConstraint(
                condition=(
                    Q(response_status__isnull=True, completed_at__isnull=True)
                    | Q(response_status__isnull=False, completed_at__isnull=False)
                ),
                name="hr_mutcmd_completion_consistent_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "created_at"), name="hr_mutcmd_t_created_idx"),
            models.Index(fields=("tenant_id", "correlation_id"), name="hr_mutcmd_t_corr_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError(
                "Mutation command records may only be completed by the command service.",
                code="immutable_mutation_command",
            )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Mutation command records are immutable.", code="immutable_mutation_command")


class AttendanceRevision(TenantScopedModel):
    """Immutable correction evidence; the original attendance fact remains reconstructable."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attendance = models.ForeignKey(Attendance, on_delete=models.PROTECT, related_name="revisions")
    revision = models.PositiveIntegerField()
    before_values = models.JSONField()
    after_values = models.JSONField()
    reason = models.TextField()
    actor_id = models.CharField(max_length=255)
    correlation_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantQuerySet.as_manager()

    class Meta:
        db_table = "hr_attendance_revisions"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "attendance", "revision"),
                name="hr_attrev_t_att_revision_uq",
            ),
            models.CheckConstraint(condition=Q(revision__gte=1), name="hr_attrev_revision_positive_ck"),
            models.CheckConstraint(condition=~Q(reason=""), name="hr_attrev_reason_nonempty_ck"),
            models.CheckConstraint(condition=~Q(actor_id=""), name="hr_attrev_actor_nonempty_ck"),
            models.CheckConstraint(condition=~Q(correlation_id=""), name="hr_attrev_correlation_nonempty_ck"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "attendance", "-revision"), name="hr_attrev_t_att_rev_idx"),
            models.Index(fields=("tenant_id", "correlation_id"), name="hr_attrev_t_corr_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Attendance revisions are immutable.", code="immutable_attendance_revision")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Attendance revisions are immutable.", code="immutable_attendance_revision")


__all__ = [
    "Attendance",
    "AttendanceRevision",
    "AttendanceSource",
    "AttendanceStatus",
    "Department",
    "Employee",
    "EmploymentStatus",
    "EmploymentType",
    "HRBaseModel",
    "HumanResourcesConfiguration",
    "HumanResourcesConfigurationAudit",
    "HumanResourcesConfigurationVersion",
    "LeaveBalance",
    "LeaveRequest",
    "LeaveRequestStatus",
    "LeaveType",
]
