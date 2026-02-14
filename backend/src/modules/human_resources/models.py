"""
Human Resources Models.

Defines data models for employees, departments, attendance, leave, and payroll.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class TenantBaseModel(models.Model):
    """Base model for tenant-scoped models with Row-Level Multitenancy.

    CRITICAL: All tenant-scoped models MUST inherit from this base class
    and include tenant_id. All queries MUST filter explicitly by tenant_id.
    """

    tenant_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class Department(TenantBaseModel):
    """Department model - Organizational unit."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    department_code = models.CharField(max_length=50, db_index=True)
    department_name = models.CharField(max_length=255)
    parent_department_id = models.UUIDField(null=True, blank=True)
    manager_id = models.UUIDField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "hr_departments"
        indexes = [
            models.Index(fields=["tenant_id", "department_code"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "department_code"], name="unique_department_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.department_code} - {self.department_name}"


class Employee(TenantBaseModel):
    """Employee model - Staff member."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    employee_number = models.CharField(max_length=50, db_index=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=255, db_index=True)
    phone = models.CharField(max_length=50, blank=True)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="employees", null=True, blank=True
    )
    position = models.CharField(max_length=100, blank=True)
    hire_date = models.DateField(db_index=True)
    employment_type = models.CharField(max_length=50, default="full_time")  # full_time, part_time, contractor
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "hr_employees"
        indexes = [
            models.Index(fields=["tenant_id", "employee_number"]),
            models.Index(fields=["tenant_id", "email"]),
            models.Index(fields=["tenant_id", "department"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "employee_number"], name="unique_employee_number_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.employee_number} - {self.first_name} {self.last_name}"


class Attendance(TenantBaseModel):
    """Attendance model - Employee attendance records."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendances")
    attendance_date = models.DateField(db_index=True)
    check_in_time = models.DateTimeField(null=True, blank=True)
    check_out_time = models.DateTimeField(null=True, blank=True)
    hours_worked = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, default="present")  # present, absent, late, half_day

    class Meta:
        db_table = "hr_attendances"
        indexes = [
            models.Index(fields=["tenant_id", "employee", "attendance_date"]),
            models.Index(fields=["tenant_id", "attendance_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "employee", "attendance_date"], name="unique_attendance_per_employee_date"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee.employee_number} - {self.attendance_date}"


class LeaveType(models.TextChoices):
    """Leave type choices."""

    ANNUAL = "annual", "Annual Leave"
    SICK = "sick", "Sick Leave"
    PERSONAL = "personal", "Personal Leave"
    MATERNITY = "maternity", "Maternity Leave"
    PATERNITY = "paternity", "Paternity Leave"
    UNPAID = "unpaid", "Unpaid Leave"


class LeaveRequestStatus(models.TextChoices):
    """Leave request status choices."""

    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class LeaveRequest(TenantBaseModel):
    """Leave request model - Employee leave requests."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.CharField(max_length=50, choices=LeaveType.choices)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    days_requested = models.DecimalField(max_digits=5, decimal_places=2)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=LeaveRequestStatus.choices, default=LeaveRequestStatus.PENDING)
    approved_by = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "hr_leave_requests"
        indexes = [
            models.Index(fields=["tenant_id", "employee", "start_date"]),
            models.Index(fields=["tenant_id", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.employee.employee_number} - {self.leave_type} ({self.start_date} to {self.end_date})"
