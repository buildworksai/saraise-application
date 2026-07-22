"""Persistence invariants for the five tenant-owned HR aggregates."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from src.core.tenancy import TenantScopedModel, TimestampedModel
from src.core.state_machine import IdempotencyConflictError, TerminalStateError

from ..models import Attendance, Department, Employee, LeaveBalance, LeaveRequest
from ..state_machines import EMPLOYEE_LIFECYCLE_MACHINE
from .factories import AttendanceFactory, DepartmentFactory, EmployeeFactory, LeaveBalanceFactory, LeaveRequestFactory


pytestmark = pytest.mark.django_db


def test_every_aggregate_uses_canonical_tenancy_audit_and_soft_delete_contract() -> None:
    for model in (Department, Employee, Attendance, LeaveBalance, LeaveRequest):
        assert issubclass(model, TenantScopedModel)
        assert issubclass(model, TimestampedModel)
        assert model._meta.get_field("tenant_id").db_index is True
        assert model._meta.get_field("tenant_id").get_internal_type() == "UUIDField"
        assert model._meta.get_field("deleted_at").db_index is True
        assert {"created_by", "updated_by", "deleted_by"}.issubset(
            {field.name for field in model._meta.fields}
        )


def test_department_defaults_normal_query_scope_and_partial_unique_constraint() -> None:
    tenant_id = uuid4()
    department = DepartmentFactory(tenant_id=tenant_id, department_code="ENG")
    assert department.is_active is True
    assert department.description == ""
    assert Department.objects.for_tenant(tenant_id).get() == department
    with pytest.raises(IntegrityError), transaction.atomic():
        DepartmentFactory(tenant_id=tenant_id, department_code="ENG")


def test_department_rejects_cross_tenant_parent_and_cycles() -> None:
    tenant_id = uuid4()
    other_parent = DepartmentFactory(tenant_id=uuid4())
    department = DepartmentFactory.build(tenant_id=tenant_id, parent_department=other_parent)
    with pytest.raises(ValidationError, match="not found in this tenant"):
        department.full_clean()

    parent = DepartmentFactory(tenant_id=tenant_id)
    child = DepartmentFactory(tenant_id=tenant_id, parent_department=parent)
    parent.parent_department = child
    with pytest.raises(ValidationError, match="cycle"):
        parent.full_clean()


def test_employee_enums_case_insensitive_email_and_reporting_cycle() -> None:
    tenant_id = uuid4()
    employee = EmployeeFactory(tenant_id=tenant_id, email="Case@Example.test")
    employee.full_clean()
    assert employee.employment_status == "active"
    assert employee.is_active is True
    with pytest.raises(IntegrityError), transaction.atomic():
        EmployeeFactory(tenant_id=tenant_id, email="case@example.test")

    report = EmployeeFactory(tenant_id=tenant_id, manager=employee)
    employee.manager = report
    with pytest.raises(ValidationError, match="cycle"):
        employee.full_clean()


def test_employee_termination_invariants_are_validated() -> None:
    employee = EmployeeFactory.build(
        employment_status="terminated",
        is_active=False,
        termination_date=None,
    )
    with pytest.raises(ValidationError, match="Termination date is required"):
        employee.full_clean()

    employee.termination_date = employee.hire_date - timedelta(days=1)
    with pytest.raises(ValidationError, match="cannot precede"):
        employee.full_clean()


def test_attendance_time_matrix_hours_and_same_tenant_relationship() -> None:
    tenant_id = uuid4()
    employee = EmployeeFactory(tenant_id=tenant_id)
    occurred = datetime(2026, 7, 20, 9, tzinfo=timezone.utc)
    attendance = AttendanceFactory.build(
        tenant_id=tenant_id,
        employee=employee,
        attendance_date=occurred.date(),
        check_in_time=occurred,
        check_out_time=occurred + timedelta(hours=8),
        hours_worked=Decimal("8.00"),
    )
    attendance.full_clean()
    attendance.check_out_time = occurred - timedelta(minutes=1)
    with pytest.raises(ValidationError, match="after check-in"):
        attendance.full_clean()

    attendance = AttendanceFactory.build(
        tenant_id=tenant_id,
        employee=employee,
        status="absent",
        hours_worked=Decimal("1.00"),
    )
    with pytest.raises(ValidationError, match="cannot contain worked time"):
        attendance.full_clean()

    attendance = AttendanceFactory.build(tenant_id=uuid4(), employee=employee)
    with pytest.raises(ValidationError, match="not found in this tenant"):
        attendance.full_clean()


def test_attendance_unique_live_day_allows_replacement_after_archive() -> None:
    attendance = AttendanceFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        AttendanceFactory(
            tenant_id=attendance.tenant_id,
            employee=attendance.employee,
            attendance_date=attendance.attendance_date,
        )
    Attendance.all_objects.filter(pk=attendance.pk).update(deleted_at=datetime.now(timezone.utc))
    replacement = AttendanceFactory(
        tenant_id=attendance.tenant_id,
        employee=attendance.employee,
        attendance_date=attendance.attendance_date,
    )
    assert replacement.pk != attendance.pk


def test_leave_balance_derived_remaining_period_and_capacity_validation() -> None:
    balance = LeaveBalanceFactory(
        entitled_days=Decimal("10.00"),
        carried_days=Decimal("2.00"),
        used_days=Decimal("3.00"),
        pending_days=Decimal("1.50"),
    )
    assert balance.remaining_days == Decimal("7.50")
    balance.full_clean()

    balance.used_days = Decimal("12.01")
    with pytest.raises(ValidationError, match="cannot exceed"):
        balance.full_clean()
    balance.period_end = balance.period_start - timedelta(days=1)
    with pytest.raises(ValidationError, match="cannot precede"):
        balance.full_clean()


def test_leave_balance_periods_cannot_overlap() -> None:
    balance = LeaveBalanceFactory()
    overlapping = LeaveBalanceFactory.build(
        tenant_id=balance.tenant_id,
        employee=balance.employee,
        leave_type=balance.leave_type,
        period_start=date(2026, 6, 1),
        period_end=date(2027, 5, 31),
    )
    with pytest.raises(ValidationError, match="cannot overlap"):
        overlapping.full_clean()


def test_leave_request_requires_matching_balance_metadata_and_non_overlap() -> None:
    balance = LeaveBalanceFactory()
    request = LeaveRequestFactory(
        tenant_id=balance.tenant_id,
        leave_balance=balance,
        employee=balance.employee,
    )
    request.full_clean()
    overlap = LeaveRequestFactory.build(
        tenant_id=balance.tenant_id,
        leave_balance=balance,
        employee=balance.employee,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    with pytest.raises(ValidationError, match="cannot overlap"):
        overlap.full_clean()

    rejected = LeaveRequestFactory.build(
        tenant_id=balance.tenant_id,
        leave_balance=balance,
        employee=balance.employee,
        status="rejected",
        rejection_reason="",
    )
    with pytest.raises(ValidationError, match="require a reason"):
        rejected.full_clean()


def test_hard_delete_is_forbidden_and_archived_rows_are_hidden() -> None:
    department = DepartmentFactory()
    with pytest.raises(ValidationError, match="Hard deletion is forbidden"):
        department.delete()
    Department.all_objects.filter(pk=department.pk).update(
        deleted_at=datetime.now(timezone.utc),
        deleted_by="archiver",
    )
    assert not Department.objects.for_tenant(department.tenant_id).filter(pk=department.pk).exists()
    assert Department.all_objects.filter(pk=department.pk, deleted_by="archiver").exists()


def test_required_composite_indexes_are_declared() -> None:
    expected_minimums = {Department: 5, Employee: 6, Attendance: 3, LeaveBalance: 3, LeaveRequest: 5}
    for model, minimum in expected_minimums.items():
        assert len(model._meta.indexes) >= minimum


def test_employee_state_machine_is_tenant_locked_idempotent_and_terminal() -> None:
    employee = EmployeeFactory()
    metadata = {
        "actor_id": "state-machine-test",
        "effective_date": date.today().isoformat(),
        "reason": "Employment ended",
        "correlation_id": "corr-state-machine",
    }
    terminated = EMPLOYEE_LIFECYCLE_MACHINE.apply(
        "terminate",
        aggregate_id=employee.id,
        tenant_id=employee.tenant_id,
        transition_key="terminate-once",
        metadata=metadata,
    )
    assert terminated.employment_status == "terminated"
    assert terminated.is_active is False
    assert terminated.termination_date == date.today()
    replay = EMPLOYEE_LIFECYCLE_MACHINE.apply(
        "terminate",
        aggregate_id=employee.id,
        tenant_id=employee.tenant_id,
        transition_key="terminate-once",
        metadata=metadata,
    )
    assert len(replay.transition_history) == 1
    with pytest.raises(IdempotencyConflictError):
        EMPLOYEE_LIFECYCLE_MACHINE.apply(
            "deactivate",
            aggregate_id=employee.id,
            tenant_id=employee.tenant_id,
            transition_key="terminate-once",
            metadata=metadata,
        )
    with pytest.raises(TerminalStateError):
        EMPLOYEE_LIFECYCLE_MACHINE.apply(
            "deactivate",
            aggregate_id=employee.id,
            tenant_id=employee.tenant_id,
            transition_key="new-command",
            metadata=metadata,
        )
