"""Deterministic tenant-safe factories for all five HR aggregates."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import factory

from ..models import Attendance, Department, Employee, LeaveBalance, LeaveRequest


class HRFactory(factory.django.DjangoModelFactory):
    tenant_id = factory.LazyFunction(uuid4)
    created_by = "hr-test-actor"
    updated_by = "hr-test-actor"

    class Meta:
        abstract = True


class DepartmentFactory(HRFactory):
    department_code = factory.Sequence(lambda value: f"DEPT-{value:04d}")
    department_name = factory.Sequence(lambda value: f"Department {value}")

    class Meta:
        model = Department


class EmployeeFactory(HRFactory):
    employee_number = factory.Sequence(lambda value: f"EMP-{value:05d}")
    first_name = "Taylor"
    last_name = factory.Sequence(lambda value: f"Person {value}")
    email = factory.Sequence(lambda value: f"employee-{value}@example.test")
    hire_date = date(2024, 1, 1)
    employment_type = "full_time"

    class Meta:
        model = Employee


class AttendanceFactory(HRFactory):
    employee = factory.SubFactory(EmployeeFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    attendance_date = date(2026, 7, 20)
    status = "present"
    source = "manual"
    hours_worked = Decimal("8.00")

    class Meta:
        model = Attendance


class LeaveBalanceFactory(HRFactory):
    employee = factory.SubFactory(EmployeeFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    leave_type = "annual"
    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    entitled_days = Decimal("20.00")
    carried_days = Decimal("0.00")

    class Meta:
        model = LeaveBalance


class LeaveRequestFactory(HRFactory):
    leave_balance = factory.SubFactory(LeaveBalanceFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    employee = factory.SelfAttribute("leave_balance.employee")
    leave_type = factory.SelfAttribute("leave_balance.leave_type")
    start_date = date(2026, 8, 3)
    end_date = date(2026, 8, 4)
    days_requested = Decimal("2.00")
    status = "pending"

    class Meta:
        model = LeaveRequest

