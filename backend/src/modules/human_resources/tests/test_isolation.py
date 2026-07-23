"""Black-box CRUD isolation for every governed HR aggregate."""

from datetime import date
from typing import Any, Mapping

import pytest

from src.core.testing.tenant_contract import TenantIsolationContract

from ..models import Attendance, Department, Employee, LeaveBalance, LeaveRequest
from .factories import AttendanceFactory, DepartmentFactory, EmployeeFactory, LeaveBalanceFactory, LeaveRequestFactory

pytestmark = pytest.mark.django_db


class _GovernedIsolation:
    """Decode the canonical v2 collection envelope."""

    def get_list_items(self, response: Any) -> list[Mapping[str, Any]]:
        payload = response.json()
        assert isinstance(payload, dict) and isinstance(payload.get("data"), list)
        return payload["data"]


class TestDepartmentIsolation(_GovernedIsolation, TenantIsolationContract):
    model = Department
    list_url = "/api/v2/human-resources/departments/"
    detail_url_template = "/api/v2/human-resources/departments/{pk}/"
    create_payload = {"department_code": "SPOOF", "department_name": "Spoof attempt"}
    update_payload = {"department_name": "Cross-tenant mutation"}

    @pytest.fixture(autouse=True)
    def context(self, tenant_a: Any, tenant_b: Any, tenant_a_client: Any, allow_hr_access: Any) -> None:
        allow_hr_access(tenant_a.id)
        self.client = tenant_a_client
        self.tenant_a_row = DepartmentFactory(tenant_id=tenant_a.id)
        self.tenant_b_row = DepartmentFactory(tenant_id=tenant_b.id)


class TestEmployeeIsolation(_GovernedIsolation, TenantIsolationContract):
    model = Employee
    list_url = "/api/v2/human-resources/employees/"
    detail_url_template = "/api/v2/human-resources/employees/{pk}/"
    create_payload = {
        "employee_number": "SPOOF-EMP",
        "first_name": "Tenant",
        "last_name": "Spoof",
        "email": "spoof-employee@example.test",
        "hire_date": "2026-01-01",
        "employment_type": "full_time",
    }
    update_payload = {"first_name": "Cross-tenant mutation"}

    @pytest.fixture(autouse=True)
    def context(self, tenant_a: Any, tenant_b: Any, tenant_a_client: Any, allow_hr_access: Any) -> None:
        allow_hr_access(tenant_a.id)
        self.client = tenant_a_client
        self.tenant_a_row = EmployeeFactory(tenant_id=tenant_a.id)
        self.tenant_b_row = EmployeeFactory(tenant_id=tenant_b.id)


class TestAttendanceIsolation(_GovernedIsolation, TenantIsolationContract):
    model = Attendance
    list_url = "/api/v2/human-resources/attendances/"
    detail_url_template = "/api/v2/human-resources/attendances/{pk}/"
    update_payload = {"notes": "Cross-tenant correction", "status": "present"}

    @pytest.fixture(autouse=True)
    def context(self, tenant_a: Any, tenant_b: Any, tenant_a_client: Any, allow_hr_access: Any) -> None:
        allow_hr_access(tenant_a.id)
        employee_a = EmployeeFactory(tenant_id=tenant_a.id)
        employee_b = EmployeeFactory(tenant_id=tenant_b.id)
        self.client = tenant_a_client
        self.tenant_a_row = AttendanceFactory(tenant_id=tenant_a.id, employee=employee_a)
        self.tenant_b_row = AttendanceFactory(tenant_id=tenant_b.id, employee=employee_b)
        self.create_payload = {
            "employee_id": str(employee_a.id),
            "attendance_date": "2026-07-21",
            "status": "present",
            "notes": "Tenant-bound manual record",
        }


class TestLeaveBalanceIsolation(_GovernedIsolation, TenantIsolationContract):
    model = LeaveBalance
    list_url = "/api/v2/human-resources/leave-balances/"
    detail_url_template = "/api/v2/human-resources/leave-balances/{pk}/"
    update_payload = {
        "entitled_days": "25.00",
        "carried_days": "0.00",
        "expected_version": 1,
        "note": "Cross-tenant adjustment",
    }

    @pytest.fixture(autouse=True)
    def context(self, tenant_a: Any, tenant_b: Any, tenant_a_client: Any, allow_hr_access: Any) -> None:
        allow_hr_access(tenant_a.id)
        employee_a = EmployeeFactory(tenant_id=tenant_a.id)
        employee_b = EmployeeFactory(tenant_id=tenant_b.id)
        self.client = tenant_a_client
        self.tenant_a_row = LeaveBalanceFactory(tenant_id=tenant_a.id, employee=employee_a)
        self.tenant_b_row = LeaveBalanceFactory(tenant_id=tenant_b.id, employee=employee_b)
        self.create_payload = {
            "employee_id": str(employee_a.id),
            "leave_type": "sick",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "entitled_days": "10.00",
            "carried_days": "0.00",
        }


class TestLeaveRequestIsolation(_GovernedIsolation, TenantIsolationContract):
    model = LeaveRequest
    list_url = "/api/v2/human-resources/leave-requests/"
    detail_url_template = "/api/v2/human-resources/leave-requests/{pk}/"
    update_payload = {"reason": "Cross-tenant mutation"}

    @pytest.fixture(autouse=True)
    def context(self, tenant_a: Any, tenant_b: Any, tenant_a_client: Any, allow_hr_access: Any) -> None:
        allow_hr_access(tenant_a.id)
        balance_a = LeaveBalanceFactory(tenant_id=tenant_a.id)
        balance_b = LeaveBalanceFactory(tenant_id=tenant_b.id)
        self.client = tenant_a_client
        self.tenant_a_row = LeaveRequestFactory(
            tenant_id=tenant_a.id,
            employee=balance_a.employee,
            leave_balance=balance_a,
        )
        self.tenant_b_row = LeaveRequestFactory(
            tenant_id=tenant_b.id,
            employee=balance_b.employee,
            leave_balance=balance_b,
        )
        self.create_payload = {
            "employee_id": str(balance_a.employee_id),
            "leave_balance_id": str(balance_a.id),
            "leave_type": balance_a.leave_type,
            "start_date": date(2026, 9, 7).isoformat(),
            "end_date": date(2026, 9, 8).isoformat(),
            "reason": "Tenant-bound request",
            "idempotency_key": "isolation-create-request",
        }


def test_cross_tenant_relationship_injection_is_rejected(
    tenant_a: Any,
    tenant_b: Any,
    tenant_a_client: Any,
    allow_hr_access: Any,
) -> None:
    allow_hr_access(tenant_a.id)
    foreign_department = DepartmentFactory(tenant_id=tenant_b.id)
    response = tenant_a_client.post(
        "/api/v2/human-resources/employees/",
        {
            "employee_number": "CROSS-TENANT",
            "first_name": "Cross",
            "last_name": "Tenant",
            "email": "cross-tenant@example.test",
            "department_id": str(foreign_department.id),
            "hire_date": "2026-01-01",
            "employment_type": "full_time",
        },
        format="json",
    )
    assert response.status_code in {400, 404}
    assert not Employee.objects.for_tenant(tenant_a.id).filter(employee_number="CROSS-TENANT").exists()


def test_foreign_department_tree_and_parent_assignment_are_invisible(
    tenant_a: Any,
    tenant_b: Any,
    tenant_a_client: Any,
    allow_hr_access: Any,
) -> None:
    allow_hr_access(tenant_a.id)
    local = DepartmentFactory(tenant_id=tenant_a.id, parent_department=None)
    foreign = DepartmentFactory(tenant_id=tenant_b.id, parent_department=None)

    tree = tenant_a_client.get(
        "/api/v2/human-resources/departments/tree/",
        {"root_id": str(foreign.id)},
    )
    assigned = tenant_a_client.patch(
        f"/api/v2/human-resources/departments/{local.id}/",
        {"parent_department_id": str(foreign.id)},
        format="json",
    )

    assert tree.status_code == 404
    assert assigned.status_code == 404
    local.refresh_from_db()
    assert local.parent_department_id is None


def test_foreign_employee_relationships_and_every_lifecycle_action_are_invisible(
    tenant_a: Any,
    tenant_b: Any,
    tenant_a_client: Any,
    allow_hr_access: Any,
) -> None:
    allow_hr_access(tenant_a.id)
    local = EmployeeFactory(tenant_id=tenant_a.id, manager=None, department=None)
    foreign = EmployeeFactory(tenant_id=tenant_b.id)
    foreign_department = DepartmentFactory(tenant_id=tenant_b.id)

    for payload in (
        {"manager_id": str(foreign.id)},
        {"department_id": str(foreign_department.id)},
    ):
        response = tenant_a_client.patch(
            f"/api/v2/human-resources/employees/{local.id}/",
            payload,
            format="json",
        )
        assert response.status_code == 404

    for action in ("activate", "deactivate", "place-on-leave", "return-from-leave", "terminate"):
        transition_key = f"foreign-{action}"
        response = tenant_a_client.post(
            f"/api/v2/human-resources/employees/{foreign.id}/{action}/",
            {
                "transition_key": transition_key,
                "effective_date": date.today().isoformat(),
                "reason": "Required only to pass command-shape validation",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=transition_key,
        )
        assert response.status_code == 404

    local.refresh_from_db()
    foreign.refresh_from_db()
    assert local.manager_id is None
    assert local.department_id is None
    assert foreign.employment_status == "active"
    assert foreign.transition_history == []


def test_foreign_attendance_injection_and_clock_actions_are_invisible(
    tenant_a: Any,
    tenant_b: Any,
    tenant_a_client: Any,
    allow_hr_access: Any,
) -> None:
    allow_hr_access(tenant_a.id)
    foreign_employee = EmployeeFactory(tenant_id=tenant_b.id)
    foreign_attendance = AttendanceFactory(tenant_id=tenant_b.id, employee=foreign_employee)

    injected = tenant_a_client.post(
        "/api/v2/human-resources/attendances/",
        {
            "employee_id": str(foreign_employee.id),
            "attendance_date": "2026-07-22",
            "status": "present",
        },
        format="json",
    )
    clock_in = tenant_a_client.post(
        "/api/v2/human-resources/attendances/clock-in/",
        {"employee_id": str(foreign_employee.id), "idempotency_key": "foreign-clock-in"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="foreign-clock-in",
    )
    clock_out = tenant_a_client.post(
        f"/api/v2/human-resources/attendances/{foreign_attendance.id}/clock-out/",
        {"idempotency_key": "foreign-clock-out"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="foreign-clock-out",
    )

    assert injected.status_code == 404
    assert clock_in.status_code == 404
    assert clock_out.status_code == 404
    foreign_attendance.refresh_from_db()
    assert foreign_attendance.check_out_time is None


def test_foreign_leave_balance_injection_and_adjustment_are_invisible(
    tenant_a: Any,
    tenant_b: Any,
    tenant_a_client: Any,
    allow_hr_access: Any,
) -> None:
    allow_hr_access(tenant_a.id)
    foreign_employee = EmployeeFactory(tenant_id=tenant_b.id)
    foreign_balance = LeaveBalanceFactory(tenant_id=tenant_b.id, employee=foreign_employee)

    injected = tenant_a_client.post(
        "/api/v2/human-resources/leave-balances/",
        {
            "employee_id": str(foreign_employee.id),
            "leave_type": "annual",
            "period_start": "2027-01-01",
            "period_end": "2027-12-31",
            "entitled_days": "20.00",
        },
        format="json",
    )
    adjusted = tenant_a_client.patch(
        f"/api/v2/human-resources/leave-balances/{foreign_balance.id}/",
        {
            "entitled_days": "99.00",
            "carried_days": "0.00",
            "expected_version": foreign_balance.adjustment_version,
            "note": "Foreign mutation attempt",
        },
        format="json",
    )

    assert injected.status_code == 404
    assert adjusted.status_code == 404
    foreign_balance.refresh_from_db()
    assert foreign_balance.entitled_days != 99
    assert foreign_balance.adjustment_version == 1


def test_foreign_leave_relationships_and_every_action_are_invisible(
    tenant_a: Any,
    tenant_b: Any,
    tenant_a_client: Any,
    allow_hr_access: Any,
) -> None:
    allow_hr_access(tenant_a.id)
    local_balance = LeaveBalanceFactory(tenant_id=tenant_a.id)
    foreign_balance = LeaveBalanceFactory(tenant_id=tenant_b.id)
    foreign_request = LeaveRequestFactory(
        tenant_id=tenant_b.id,
        employee=foreign_balance.employee,
        leave_balance=foreign_balance,
    )
    original_pending_days = foreign_balance.pending_days

    for employee_id, balance_id in (
        (foreign_balance.employee_id, local_balance.id),
        (local_balance.employee_id, foreign_balance.id),
    ):
        response = tenant_a_client.post(
            "/api/v2/human-resources/leave-requests/",
            {
                "employee_id": str(employee_id),
                "leave_balance_id": str(balance_id),
                "leave_type": "annual",
                "start_date": "2026-10-01",
                "end_date": "2026-10-02",
                "idempotency_key": f"foreign-request-{employee_id}",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=f"foreign-request-{employee_id}",
        )
        assert response.status_code == 404

    for action, payload in (
        ("approve", {"transition_key": "foreign-approve"}),
        (
            "reject",
            {"transition_key": "foreign-reject", "rejection_reason": "Foreign attempt"},
        ),
        ("cancel", {"transition_key": "foreign-cancel"}),
    ):
        transition_key = str(payload["transition_key"])
        response = tenant_a_client.post(
            f"/api/v2/human-resources/leave-requests/{foreign_request.id}/{action}/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=transition_key,
        )
        assert response.status_code == 404

    archived = tenant_a_client.delete(
        f"/api/v2/human-resources/leave-requests/{foreign_request.id}/",
        HTTP_IDEMPOTENCY_KEY="foreign-archive",
    )
    assert archived.status_code == 404
    foreign_request.refresh_from_db()
    foreign_balance.refresh_from_db()
    assert foreign_request.status == "pending"
    assert foreign_request.deleted_at is None
    assert foreign_balance.pending_days == original_pending_days
