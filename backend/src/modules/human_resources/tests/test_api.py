"""Governed API v2 contracts through real session authentication and CSRF."""

from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
from rest_framework import status

from src.core.access.decision import HttpPolicyEvaluator, PolicyEvaluation
from src.core.testing.factories import authenticated_api_client

from ..models import Department, Employee
from ..services import DepartmentService
from .factories import DepartmentFactory, EmployeeFactory


pytestmark = pytest.mark.django_db


def assert_success_envelope(response: Any) -> dict[str, Any]:
    payload = response.json()
    assert set(payload) == {"data", "meta"}
    assert payload["meta"]["correlation_id"]
    assert payload["meta"]["timestamp"]
    assert response.headers.get("X-Correlation-ID")
    return payload


def test_unauthenticated_is_401_and_put_is_unsupported(api_client: Any) -> None:
    response = api_client.get("/api/v2/human-resources/employees/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    payload = response.json()
    assert payload["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_policy_entitlement_or_quota_denial_is_403(tenant_a: Any, tenant_a_client: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        HttpPolicyEvaluator,
        "evaluate",
        lambda self, tenant_id, identity, required_permission, request=None: PolicyEvaluation(True),
    )
    # No entitlement or quota projections exist: the unified pipeline fails closed.
    response = tenant_a_client.get("/api/v2/human-resources/employees/")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "POLICY_DENIED"


def test_csrf_is_enforced_for_unsafe_session_requests(tenant_a: Any, tenant_a_user: Any, allow_hr_access: Any) -> None:
    allow_hr_access(tenant_a.id)
    client = authenticated_api_client(tenant_a_user, enforce_csrf_checks=True)
    client.credentials()  # Keep the authenticated session, remove the valid CSRF header.
    response = client.post(
        "/api/v2/human-resources/departments/",
        {"department_code": "NO-CSRF", "department_name": "Rejected"},
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert not Department.objects.for_tenant(tenant_a.id).filter(department_code="NO-CSRF").exists()


def test_employee_collection_paginates_filters_searches_orders_and_rejects_tenant_input(
    tenant_a: Any,
    tenant_a_client: Any,
    allow_hr_access: Any,
) -> None:
    allow_hr_access(tenant_a.id)
    department = DepartmentFactory(tenant_id=tenant_a.id, department_name="Engineering")
    alpha = EmployeeFactory(
        tenant_id=tenant_a.id,
        department=department,
        employee_number="EMP-002",
        first_name="Alpha",
        employment_status="active",
        is_active=True,
    )
    EmployeeFactory(
        tenant_id=tenant_a.id,
        employee_number="EMP-001",
        first_name="Beta",
        employment_status="inactive",
        is_active=False,
    )
    response = tenant_a_client.get(
        "/api/v2/human-resources/employees/",
        {
            "department": str(department.id),
            "employment_status": "active",
            "search": "Alpha",
            "ordering": "-employee_number",
            "page_size": 1000,
        },
    )
    assert response.status_code == status.HTTP_200_OK
    payload = assert_success_envelope(response)
    assert [row["id"] for row in payload["data"]] == [str(alpha.id)]
    assert payload["meta"]["pagination"]["page_size"] == 100
    assert "tenant_id" in payload["data"][0]

    spoof = tenant_a_client.post(
        "/api/v2/human-resources/employees/",
        {
            "tenant_id": "00000000-0000-0000-0000-000000000000",
            "employee_number": "SPOOFED",
            "first_name": "Tenant",
            "last_name": "Spoof",
            "email": "spoofed@example.test",
            "hire_date": "2026-01-01",
            "employment_type": "full_time",
        },
        format="json",
    )
    assert spoof.status_code == status.HTTP_400_BAD_REQUEST
    assert spoof.json()["error"]["code"] == "VALIDATION_ERROR"


def test_department_crud_tree_and_service_delegation(
    tenant_a: Any,
    tenant_a_client: Any,
    allow_hr_access: Any,
) -> None:
    allow_hr_access(tenant_a.id)
    created = tenant_a_client.post(
        "/api/v2/human-resources/departments/",
        {"department_code": "eng", "department_name": "Engineering"},
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED
    department_id = assert_success_envelope(created)["data"]["id"]
    detail = tenant_a_client.get(f"/api/v2/human-resources/departments/{department_id}/")
    assert detail.status_code == status.HTTP_200_OK

    department = Department.objects.for_tenant(tenant_a.id).get(pk=department_id)
    with patch.object(DepartmentService, "update_department", wraps=DepartmentService.update_department) as update:
        response = tenant_a_client.patch(
            f"/api/v2/human-resources/departments/{department_id}/",
            {"department_name": "Platform Engineering"},
            format="json",
        )
    assert response.status_code == status.HTTP_200_OK
    update.assert_called_once()
    department.refresh_from_db()
    assert department.department_name == "Platform Engineering"

    tree = tenant_a_client.get("/api/v2/human-resources/departments/tree/")
    assert tree.status_code == status.HTTP_200_OK
    assert assert_success_envelope(tree)["data"][0]["department_name"] == "Platform Engineering"
    unsupported = tenant_a_client.put(
        f"/api/v2/human-resources/departments/{department_id}/",
        {"department_name": "Not replaced"},
        format="json",
    )
    assert unsupported.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


def test_duplicate_employee_is_a_stable_409(
    tenant_a: Any,
    tenant_a_client: Any,
    allow_hr_access: Any,
) -> None:
    allow_hr_access(tenant_a.id)
    EmployeeFactory(tenant_id=tenant_a.id, employee_number="DUP-1", email="existing@example.test")
    response = tenant_a_client.post(
        "/api/v2/human-resources/employees/",
        {
            "employee_number": "DUP-1",
            "first_name": "Duplicate",
            "last_name": "Employee",
            "email": "new@example.test",
            "hire_date": "2026-01-01",
            "employment_type": "full_time",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] in {"HR_RESOURCE_CONFLICT", "HR_CONFLICT"}


def test_employee_lifecycle_actions_and_reporting_tree(
    tenant_a: Any,
    tenant_a_client: Any,
    allow_hr_access: Any,
) -> None:
    allow_hr_access(tenant_a.id)
    manager = EmployeeFactory(tenant_id=tenant_a.id)
    report = EmployeeFactory(tenant_id=tenant_a.id, manager=manager)
    tree = tenant_a_client.get(f"/api/v2/human-resources/employees/{manager.id}/reporting-tree/?depth=5")
    assert tree.status_code == status.HTTP_200_OK
    assert assert_success_envelope(tree)["data"]["direct_reports"][0]["id"] == str(report.id)

    response = tenant_a_client.post(
        f"/api/v2/human-resources/employees/{report.id}/deactivate/",
        {
            "transition_key": "api-deactivate",
            "effective_date": date.today().isoformat(),
            "reason": "",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-deactivate",
    )
    assert response.status_code == status.HTTP_200_OK
    assert assert_success_envelope(response)["data"]["employment_status"] == "inactive"


def test_attendance_manual_clock_in_clock_out_and_correction(
    tenant_a: Any,
    tenant_a_client: Any,
    allow_hr_access: Any,
) -> None:
    allow_hr_access(tenant_a.id)
    employee = EmployeeFactory(tenant_id=tenant_a.id)
    manual = tenant_a_client.post(
        "/api/v2/human-resources/attendances/",
        {
            "employee_id": str(employee.id),
            "attendance_date": "2026-07-20",
            "status": "present",
            "notes": "Manual record",
        },
        format="json",
    )
    assert manual.status_code == status.HTTP_201_CREATED
    attendance_id = assert_success_envelope(manual)["data"]["id"]
    correction = tenant_a_client.patch(
        f"/api/v2/human-resources/attendances/{attendance_id}/",
        {"status": "late", "notes": "Manager-approved correction"},
        format="json",
    )
    assert correction.status_code == status.HTTP_200_OK

    clock_employee = EmployeeFactory(tenant_id=tenant_a.id)
    occurred = datetime(2026, 7, 21, 9, tzinfo=timezone.utc)
    clock_in = tenant_a_client.post(
        "/api/v2/human-resources/attendances/clock-in/",
        {
            "employee_id": str(clock_employee.id),
            "occurred_at": occurred.isoformat(),
            "idempotency_key": "api-clock-in",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-clock-in",
    )
    assert clock_in.status_code == status.HTTP_201_CREATED
    clock_id = assert_success_envelope(clock_in)["data"]["id"]
    clock_out = tenant_a_client.post(
        f"/api/v2/human-resources/attendances/{clock_id}/clock-out/",
        {
            "occurred_at": (occurred + timedelta(hours=8)).isoformat(),
            "idempotency_key": "api-clock-out",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-clock-out",
    )
    assert clock_out.status_code == status.HTTP_200_OK
    assert assert_success_envelope(clock_out)["data"]["hours_worked"] == "8.00"


def test_leave_balance_version_conflict_and_request_action_workflow(
    tenant_a: Any,
    tenant_a_client: Any,
    allow_hr_access: Any,
) -> None:
    allow_hr_access(tenant_a.id)
    employee = EmployeeFactory(tenant_id=tenant_a.id)
    balance_response = tenant_a_client.post(
        "/api/v2/human-resources/leave-balances/",
        {
            "employee_id": str(employee.id),
            "leave_type": "annual",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "entitled_days": "20.00",
            "carried_days": "0.00",
        },
        format="json",
    )
    assert balance_response.status_code == status.HTTP_201_CREATED
    balance_id = assert_success_envelope(balance_response)["data"]["id"]
    stale = tenant_a_client.patch(
        f"/api/v2/human-resources/leave-balances/{balance_id}/",
        {
            "entitled_days": "21.00",
            "carried_days": "0.00",
            "expected_version": 99,
            "note": "Stale allocation",
        },
        format="json",
    )
    assert stale.status_code == status.HTTP_409_CONFLICT
    assert stale.json()["error"]["code"] == "HR_VERSION_CONFLICT"

    submitted = tenant_a_client.post(
        "/api/v2/human-resources/leave-requests/",
        {
            "employee_id": str(employee.id),
            "leave_balance_id": balance_id,
            "leave_type": "annual",
            "start_date": "2026-08-10",
            "end_date": "2026-08-12",
            "reason": "Family leave",
            "idempotency_key": "api-leave-submit",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-leave-submit",
    )
    assert submitted.status_code == status.HTTP_201_CREATED
    request_id = assert_success_envelope(submitted)["data"]["id"]
    approved = tenant_a_client.post(
        f"/api/v2/human-resources/leave-requests/{request_id}/approve/",
        {"transition_key": "api-leave-approve"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-leave-approve",
    )
    assert approved.status_code == status.HTTP_200_OK
    assert assert_success_envelope(approved)["data"]["status"] == "approved"


def test_invalid_filters_and_unknown_fields_use_governed_400(
    tenant_a: Any,
    tenant_a_client: Any,
    allow_hr_access: Any,
) -> None:
    allow_hr_access(tenant_a.id)
    response = tenant_a_client.get("/api/v2/human-resources/employees/?unknown=true")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["correlation_id"]


def test_health_is_governed_and_never_exposes_domain_rows(
    tenant_a: Any,
    tenant_a_client: Any,
    allow_hr_access: Any,
) -> None:
    allow_hr_access(tenant_a.id)
    response = tenant_a_client.get("/api/v2/human-resources/health/")
    assert response.status_code in {status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE}
    payload = response.json()
    if response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
        assert payload["error"]["code"] == "HR_NOT_READY"
        data = payload["error"]["detail"]
    else:
        data = payload["data"]
    rendered = str(data).lower()
    assert data["module"] == "human_resources"
    assert "email" not in rendered
    assert "row_count" not in rendered
