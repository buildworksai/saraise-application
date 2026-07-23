"""Transactional service authority, idempotency, and outbox evidence."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from src.core.async_jobs.models import OutboxEvent

from ..events import EVENT_TYPES, publish_domain_event
from ..extensions import (
    ApprovalSubmission,
    BusinessCalendarPort,
    ExtensionContext,
    HumanResourcesEventSubscriber,
    MasterDataEmployeePort,
    MasterDataEmployeeReference,
    WorkflowApprovalPort,
)
from ..models import Attendance, Department, Employee, LeaveBalance, LeaveRequest
from ..services import (
    AttendanceService,
    DepartmentService,
    EmployeeService,
    HRCapabilityUnavailableError,
    HRConflictError,
    HRNotFoundError,
    HRValidationError,
    LeaveBalanceService,
    LeaveRequestService,
)
from .factories import AttendanceFactory, DepartmentFactory, EmployeeFactory, LeaveBalanceFactory

pytestmark = pytest.mark.django_db
ACTOR = "service-test-actor"


def event_exists(tenant_id: object, event_type: str, aggregate_id: object) -> bool:
    return (
        OutboxEvent.objects.for_tenant(tenant_id)
        .filter(
            event_type=event_type,
            aggregate_id=aggregate_id,
        )
        .exists()
    )


def test_department_service_normalizes_validates_hierarchy_and_emits_outbox() -> None:
    tenant_id = uuid4()
    root = DepartmentService.create_department(
        tenant_id,
        code=" eng ",
        name=" Engineering ",
        parent_id=None,
        manager_id=None,
        description=" Product engineering ",
        actor_id=ACTOR,
        correlation_id="corr-department",
    )
    child = DepartmentService.create_department(
        tenant_id,
        code="platform",
        name="Platform",
        parent_id=root.id,
        manager_id=None,
        description="",
        actor_id=ACTOR,
    )
    assert (root.department_code, root.department_name, root.description) == (
        "ENG",
        "Engineering",
        "Product engineering",
    )
    hierarchy = DepartmentService.get_hierarchy(tenant_id)
    assert hierarchy[0].id == root.id
    assert hierarchy[0].children[0].id == child.id
    assert event_exists(tenant_id, "human_resources.department.created", root.id)

    with pytest.raises(HRConflictError):
        DepartmentService.update_department(
            tenant_id,
            root.id,
            changes={"parent_department_id": child.id},
            actor_id=ACTOR,
        )
    root.refresh_from_db()
    assert root.parent_department_id is None


def test_department_cross_tenant_reference_and_active_child_archive_are_rejected() -> None:
    tenant_id = uuid4()
    foreign = DepartmentFactory(tenant_id=uuid4())
    with pytest.raises(HRNotFoundError):
        DepartmentService.create_department(
            tenant_id,
            code="BAD",
            name="Bad reference",
            parent_id=foreign.id,
            manager_id=None,
            description="",
            actor_id=ACTOR,
        )
    assert not Department.objects.for_tenant(tenant_id).exists()

    parent = DepartmentFactory(tenant_id=tenant_id)
    DepartmentFactory(tenant_id=tenant_id, parent_department=parent)
    with pytest.raises(HRConflictError):
        DepartmentService.delete_department(tenant_id, parent.id, actor_id=ACTOR)


def test_employee_create_update_transition_retry_and_archive_are_governed() -> None:
    tenant_id = uuid4()
    department = DepartmentFactory(tenant_id=tenant_id)
    employee = EmployeeService.create_employee(
        tenant_id,
        data={
            "employee_number": " emp-101 ",
            "first_name": " Ada ",
            "last_name": " Lovelace ",
            "email": "ADA@EXAMPLE.TEST",
            "department_id": department.id,
            "hire_date": date(2024, 1, 1),
            "employment_type": "full_time",
        },
        actor_id=ACTOR,
        correlation_id="corr-employee",
    )
    assert employee.employee_number == "EMP-101"
    assert employee.email == "ada@example.test"
    assert event_exists(tenant_id, "human_resources.employee.created", employee.id)

    updated = EmployeeService.update_employee(
        tenant_id,
        employee.id,
        changes={"position": "Principal engineer", "department_id": None},
        actor_id=ACTOR,
    )
    assert updated.position == "Principal engineer"
    assert updated.department_id is None
    assert event_exists(tenant_id, "human_resources.employee.department_changed", employee.id)

    inactive = EmployeeService.transition_employee(
        tenant_id,
        employee.id,
        command="deactivate",
        transition_key="employee-deactivate-1",
        effective_date=date.today(),
        reason="",
        actor_id=ACTOR,
    )
    assert (inactive.employment_status, inactive.is_active) == ("inactive", False)
    replay = EmployeeService.transition_employee(
        tenant_id,
        employee.id,
        command="deactivate",
        transition_key="employee-deactivate-1",
        effective_date=date.today(),
        reason="",
        actor_id=ACTOR,
    )
    assert len(replay.transition_history) == 1

    active = EmployeeService.transition_employee(
        tenant_id,
        employee.id,
        command="activate",
        transition_key="employee-activate-1",
        effective_date=date.today(),
        reason="",
        actor_id=ACTOR,
    )
    terminated = EmployeeService.transition_employee(
        tenant_id,
        active.id,
        command="terminate",
        transition_key="employee-terminate-1",
        effective_date=date.today(),
        reason="Employment ended",
        actor_id=ACTOR,
    )
    assert terminated.termination_date == date.today()
    EmployeeService.delete_employee(tenant_id, employee.id, actor_id=ACTOR)
    assert not Employee.objects.for_tenant(tenant_id).filter(pk=employee.id).exists()
    assert Employee.all_objects.filter(pk=employee.id, deleted_by=ACTOR).exists()


def test_employee_rejects_cross_tenant_department_and_reused_transition_key() -> None:
    tenant_id = uuid4()
    employee = EmployeeFactory(tenant_id=tenant_id)
    foreign = DepartmentFactory(tenant_id=uuid4())
    with pytest.raises(HRNotFoundError):
        EmployeeService.update_employee(
            tenant_id,
            employee.id,
            changes={"department_id": foreign.id},
            actor_id=ACTOR,
        )
    EmployeeService.transition_employee(
        tenant_id,
        employee.id,
        command="deactivate",
        transition_key="shared-transition",
        effective_date=date.today(),
        reason="",
        actor_id=ACTOR,
    )
    with pytest.raises(HRConflictError, match="another command"):
        EmployeeService.transition_employee(
            tenant_id,
            employee.id,
            command="activate",
            transition_key="shared-transition",
            effective_date=date.today(),
            reason="",
            actor_id=ACTOR,
        )


def test_attendance_create_correction_clock_and_retry_are_real() -> None:
    tenant_id = uuid4()
    employee = EmployeeFactory(tenant_id=tenant_id)
    occurred = datetime(2026, 7, 20, 9, tzinfo=timezone.utc)
    attendance = AttendanceService.create_attendance(
        tenant_id,
        data={
            "employee_id": employee.id,
            "attendance_date": occurred.date(),
            "check_in_time": occurred,
            "check_out_time": occurred + timedelta(hours=8, minutes=30),
            "status": "present",
            "notes": "Manual verification",
        },
        actor_id=ACTOR,
    )
    assert attendance.hours_worked == Decimal("8.50")
    with pytest.raises(HRValidationError) as correction:
        AttendanceService.update_attendance(
            tenant_id,
            attendance.id,
            changes={"status": "late", "notes": ""},
            actor_id=ACTOR,
        )
    assert correction.value.error_code == "HR_CORRECTION_NOTE_REQUIRED"

    clock_employee = EmployeeFactory(tenant_id=tenant_id)
    clocked = AttendanceService.clock_in(
        tenant_id,
        employee_id=clock_employee.id,
        occurred_at=occurred,
        actor_id=ACTOR,
        idempotency_key="clock-in-1",
    )
    replay = AttendanceService.clock_in(
        tenant_id,
        employee_id=clock_employee.id,
        occurred_at=occurred,
        actor_id=ACTOR,
        idempotency_key="clock-in-1",
    )
    assert replay.id == clocked.id
    completed = AttendanceService.clock_out(
        tenant_id,
        clocked.id,
        occurred_at=occurred + timedelta(hours=8),
        actor_id=ACTOR,
        idempotency_key="clock-out-1",
    )
    assert completed.hours_worked == Decimal("8.00")
    assert Attendance.objects.for_tenant(tenant_id).count() == 2


def test_leave_balance_mutations_lock_version_and_preserve_accounting() -> None:
    tenant_id = uuid4()
    employee = EmployeeFactory(tenant_id=tenant_id)
    balance = LeaveBalanceService.create_balance(
        tenant_id,
        data={
            "employee_id": employee.id,
            "leave_type": "annual",
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 12, 31),
            "entitled_days": Decimal("20.00"),
            "carried_days": Decimal("2.00"),
        },
        actor_id=ACTOR,
    )
    adjusted = LeaveBalanceService.update_allocation(
        tenant_id,
        balance.id,
        entitled_days=Decimal("21.00"),
        carried_days=Decimal("2.00"),
        expected_version=1,
        note="Annual review",
        actor_id=ACTOR,
    )
    assert adjusted.adjustment_version == 2
    with pytest.raises(HRConflictError) as conflict:
        LeaveBalanceService.update_allocation(
            tenant_id,
            balance.id,
            entitled_days=Decimal("22.00"),
            carried_days=Decimal("2.00"),
            expected_version=1,
            note="Stale update",
            actor_id=ACTOR,
        )
    assert conflict.value.error_code == "HR_VERSION_CONFLICT"

    reserved = LeaveBalanceService.reserve(
        tenant_id,
        balance.id,
        days=Decimal("3.00"),
        actor_id=ACTOR,
    )
    consumed = LeaveBalanceService.approve_reservation(
        tenant_id,
        balance.id,
        days=Decimal("2.00"),
        actor_id=ACTOR,
    )
    released = LeaveBalanceService.release_reservation(
        tenant_id,
        balance.id,
        days=Decimal("1.00"),
        actor_id=ACTOR,
    )
    reversed_balance = LeaveBalanceService.reverse_usage(
        tenant_id,
        balance.id,
        days=Decimal("1.00"),
        actor_id=ACTOR,
    )
    assert reserved.pending_days == Decimal("3.00")
    assert consumed.used_days == Decimal("2.00")
    assert released.pending_days == Decimal("0.00")
    assert reversed_balance.used_days == Decimal("1.00")


def test_leave_submission_approval_is_atomic_idempotent_and_balance_backed() -> None:
    tenant_id = uuid4()
    balance = LeaveBalanceFactory(tenant_id=tenant_id, entitled_days=Decimal("10.00"))
    payload = {
        "employee_id": balance.employee_id,
        "leave_balance_id": balance.id,
        "leave_type": balance.leave_type,
        "start_date": date(2026, 8, 10),
        "end_date": date(2026, 8, 12),
        "reason": "Family leave",
    }
    request = LeaveRequestService.submit_request(
        tenant_id,
        data=payload,
        actor_id=ACTOR,
        idempotency_key="submit-leave-1",
        correlation_id="corr-leave",
    )
    replay = LeaveRequestService.submit_request(
        tenant_id,
        data=payload,
        actor_id=ACTOR,
        idempotency_key="submit-leave-1",
    )
    assert replay.id == request.id
    balance.refresh_from_db()
    assert (request.days_requested, balance.pending_days) == (Decimal("3.00"), Decimal("3.00"))

    approved = LeaveRequestService.approve_request(
        tenant_id,
        request.id,
        transition_key="approve-leave-1",
        actor_id=ACTOR,
    )
    balance.refresh_from_db()
    assert approved.status == "approved"
    assert (balance.pending_days, balance.used_days) == (Decimal("0.00"), Decimal("3.00"))
    replay_approval = LeaveRequestService.approve_request(
        tenant_id,
        request.id,
        transition_key="approve-leave-1",
        actor_id=ACTOR,
    )
    balance.refresh_from_db()
    assert replay_approval.status == "approved"
    assert balance.used_days == Decimal("3.00")
    assert event_exists(tenant_id, "human_resources.leave_request.approved", request.id)


def test_leave_insufficient_and_overlap_fail_without_partial_reservation() -> None:
    tenant_id = uuid4()
    balance = LeaveBalanceFactory(tenant_id=tenant_id, entitled_days=Decimal("2.00"))
    too_large = {
        "employee_id": balance.employee_id,
        "leave_balance_id": balance.id,
        "leave_type": balance.leave_type,
        "start_date": date(2026, 9, 1),
        "end_date": date(2026, 9, 5),
    }
    with pytest.raises(HRConflictError) as insufficient:
        LeaveRequestService.submit_request(
            tenant_id,
            data=too_large,
            actor_id=ACTOR,
            idempotency_key="too-large",
        )
    assert insufficient.value.error_code == "HR_INSUFFICIENT_BALANCE"
    balance.refresh_from_db()
    assert balance.pending_days == Decimal("0.00")
    assert not LeaveRequest.objects.for_tenant(tenant_id).exists()

    LeaveBalance.objects.for_tenant(tenant_id).filter(pk=balance.pk).update(entitled_days=Decimal("20.00"))
    first = dict(too_large, end_date=date(2026, 9, 2))
    LeaveRequestService.submit_request(
        tenant_id,
        data=first,
        actor_id=ACTOR,
        idempotency_key="first-request",
    )
    overlap = dict(first, start_date=date(2026, 9, 2), end_date=date(2026, 9, 3))
    with pytest.raises(HRConflictError) as conflict:
        LeaveRequestService.submit_request(
            tenant_id,
            data=overlap,
            actor_id=ACTOR,
            idempotency_key="overlap-request",
        )
    assert conflict.value.error_code == "HR_LEAVE_OVERLAP"
    assert LeaveRequest.objects.for_tenant(tenant_id).count() == 1


def test_structured_logs_include_correlation_but_not_employee_pii(caplog: pytest.LogCaptureFixture) -> None:
    tenant_id = uuid4()
    with caplog.at_level("INFO", logger="saraise.human_resources"):
        employee = EmployeeService.create_employee(
            tenant_id,
            data={
                "employee_number": "LOG-1",
                "first_name": "Private",
                "last_name": "Person",
                "email": "private-person@example.test",
                "hire_date": date(2025, 1, 1),
                "employment_type": "full_time",
            },
            actor_id=ACTOR,
            correlation_id="corr-safe-log",
        )
    record = next(item for item in caplog.records if item.action == "create_employee")
    assert record.correlation_id == "corr-safe-log"
    assert record.aggregate_id == str(employee.id)
    rendered = caplog.text
    assert "private-person@example.test" not in rendered
    assert "Private Person" not in rendered


def test_department_update_deactivate_and_archive_cover_lifecycle_guards() -> None:
    tenant_id = uuid4()
    manager = EmployeeFactory(tenant_id=tenant_id)
    department = DepartmentFactory(tenant_id=tenant_id)
    updated = DepartmentService.update_department(
        tenant_id,
        department.id,
        changes={
            "department_code": " ops ",
            "department_name": " Operations ",
            "manager_id": manager.id,
            "description": " Delivery ",
        },
        actor_id=ACTOR,
    )
    assert (updated.department_code, updated.department_name, updated.manager_id) == (
        "OPS",
        "Operations",
        manager.id,
    )
    assert DepartmentService.get_hierarchy(tenant_id, root_id=department.id)[0].manager_name

    attached = EmployeeFactory(tenant_id=tenant_id, department=department)
    with pytest.raises(HRConflictError, match="employees"):
        DepartmentService.deactivate_department(tenant_id, department.id, actor_id=ACTOR)
    attached.employment_status = "inactive"
    attached.is_active = False
    attached.save(update_fields=("employment_status", "is_active"))
    inactive = DepartmentService.deactivate_department(tenant_id, department.id, actor_id=ACTOR)
    assert inactive.is_active is False
    DepartmentService.delete_department(tenant_id, department.id, actor_id=ACTOR)
    assert Department.all_objects.get(pk=department.id).deleted_by == ACTOR


def test_employee_validation_reporting_tree_and_transition_guards() -> None:
    tenant_id = uuid4()
    inactive_department = DepartmentFactory(tenant_id=tenant_id, is_active=False)
    with pytest.raises(HRConflictError, match="active"):
        EmployeeService.validate_department(tenant_id, inactive_department.id)

    manager = EmployeeFactory(tenant_id=tenant_id)
    report = EmployeeFactory(tenant_id=tenant_id, manager=manager)
    second_level = EmployeeFactory(tenant_id=tenant_id, manager=report)
    tree = EmployeeService.get_reporting_tree(tenant_id, manager.id, depth=2)
    assert [item.id for item in tree.children] == [report.id]
    assert tree.children[0].children == []
    with pytest.raises(HRValidationError, match="between 1 and 20"):
        EmployeeService.get_reporting_tree(tenant_id, manager.id, depth=0)
    with pytest.raises(HRConflictError, match="cycle"):
        EmployeeService.update_employee(
            tenant_id,
            manager.id,
            changes={"manager_id": second_level.id},
            actor_id=ACTOR,
        )
    with pytest.raises(HRCapabilityUnavailableError):
        EmployeeService.transition_employee(
            tenant_id,
            report.id,
            command="deactivate",
            transition_key="future-transition",
            effective_date=date.today() + timedelta(days=1),
            reason="",
            actor_id=ACTOR,
        )


def test_attendance_recalculate_archive_and_failure_matrix() -> None:
    tenant_id = uuid4()
    employee = EmployeeFactory(tenant_id=tenant_id)
    occurred = datetime(2026, 7, 20, 9, tzinfo=timezone.utc)
    attendance = AttendanceService.create_attendance(
        tenant_id,
        data={
            "employee_id": employee.id,
            "attendance_date": occurred.date(),
            "check_in_time": occurred,
            "check_out_time": occurred + timedelta(hours=7, minutes=45),
            "status": "present",
        },
        actor_id=ACTOR,
    )
    recalculated = AttendanceService.recalculate_hours(
        tenant_id,
        attendance.id,
        actor_id=ACTOR,
    )
    assert recalculated.hours_worked == Decimal("7.75")
    AttendanceService.delete_attendance(tenant_id, attendance.id, actor_id=ACTOR)
    assert Attendance.all_objects.get(pk=attendance.id).deleted_at is not None

    missing_clock = AttendanceFactory(tenant_id=tenant_id, employee=employee, attendance_date=date(2026, 7, 21))
    with pytest.raises(HRConflictError, match="timestamps"):
        AttendanceService.recalculate_hours(tenant_id, missing_clock.id, actor_id=ACTOR)
    with pytest.raises(HRConflictError, match="check-in"):
        AttendanceService.clock_out(
            tenant_id,
            missing_clock.id,
            occurred_at=occurred,
            actor_id=ACTOR,
            idempotency_key="missing-check-in",
        )


def test_balance_failure_paths_and_unused_archive() -> None:
    tenant_id = uuid4()
    balance = LeaveBalanceFactory(tenant_id=tenant_id, entitled_days=Decimal("5.00"))
    with pytest.raises(HRValidationError, match="positive"):
        LeaveBalanceService.reserve(tenant_id, balance.id, days=Decimal("0"), actor_id=ACTOR)
    with pytest.raises(HRConflictError, match="insufficient"):
        LeaveBalanceService.reserve(tenant_id, balance.id, days=Decimal("6"), actor_id=ACTOR)
    with pytest.raises(HRConflictError, match="pending"):
        LeaveBalanceService.release_reservation(
            tenant_id,
            balance.id,
            days=Decimal("1"),
            actor_id=ACTOR,
        )
    with pytest.raises(HRConflictError, match="Used"):
        LeaveBalanceService.reverse_usage(
            tenant_id,
            balance.id,
            days=Decimal("1"),
            actor_id=ACTOR,
        )
    LeaveBalanceService.delete_balance(tenant_id, balance.id, actor_id=ACTOR)
    assert LeaveBalance.all_objects.get(pk=balance.id).deleted_at is not None


def test_leave_update_reject_cancel_and_archive_workflows() -> None:
    tenant_id = uuid4()
    balance = LeaveBalanceFactory(tenant_id=tenant_id, entitled_days=Decimal("30"))

    rejected = LeaveRequestService.submit_request(
        tenant_id,
        data={
            "employee_id": balance.employee_id,
            "leave_balance_id": balance.id,
            "leave_type": balance.leave_type,
            "start_date": date(2026, 10, 1),
            "end_date": date(2026, 10, 2),
        },
        actor_id=ACTOR,
        idempotency_key="submit-reject",
    )
    updated = LeaveRequestService.update_pending_request(
        tenant_id,
        rejected.id,
        changes={"start_date": date(2026, 10, 2), "end_date": date(2026, 10, 4), "reason": "Updated"},
        actor_id=ACTOR,
    )
    assert updated.days_requested == Decimal("3.00")
    rejected = LeaveRequestService.reject_request(
        tenant_id,
        rejected.id,
        transition_key="reject-request",
        rejection_reason="Coverage unavailable",
        actor_id=ACTOR,
    )
    assert rejected.status == "rejected"
    with pytest.raises(HRConflictError, match="cancellable"):
        LeaveRequestService.delete_request(
            tenant_id,
            rejected.id,
            transition_key="archive-rejected",
            actor_id=ACTOR,
        )

    pending = LeaveRequestService.submit_request(
        tenant_id,
        data={
            "employee_id": balance.employee_id,
            "leave_balance_id": balance.id,
            "leave_type": balance.leave_type,
            "start_date": date(2026, 11, 1),
            "end_date": date(2026, 11, 2),
        },
        actor_id=ACTOR,
        idempotency_key="submit-cancel",
    )
    cancelled = LeaveRequestService.cancel_request(
        tenant_id,
        pending.id,
        transition_key="cancel-request",
        actor_id=ACTOR,
    )
    assert cancelled.status == "cancelled"
    LeaveRequestService.delete_request(
        tenant_id,
        cancelled.id,
        transition_key="archive-cancelled",
        actor_id=ACTOR,
    )
    assert LeaveRequest.all_objects.get(pk=cancelled.id).deleted_at is not None


def test_approved_future_leave_cancellation_reverses_usage_atomically() -> None:
    tenant_id = uuid4()
    balance = LeaveBalanceFactory(tenant_id=tenant_id, entitled_days=Decimal("10"))
    request = LeaveRequestService.submit_request(
        tenant_id,
        data={
            "employee_id": balance.employee_id,
            "leave_balance_id": balance.id,
            "leave_type": balance.leave_type,
            "start_date": date(2026, 12, 1),
            "end_date": date(2026, 12, 2),
        },
        actor_id=ACTOR,
        idempotency_key="submit-approved-cancel",
    )
    LeaveRequestService.approve_request(
        tenant_id,
        request.id,
        transition_key="approve-before-cancel",
        actor_id=ACTOR,
    )
    cancelled = LeaveRequestService.cancel_request(
        tenant_id,
        request.id,
        transition_key="cancel-approved",
        actor_id=ACTOR,
    )
    balance.refresh_from_db()
    assert cancelled.status == "cancelled"
    assert balance.used_days == Decimal("0.00")


def test_event_envelope_and_extension_protocol_contract_are_concrete() -> None:
    tenant_id = uuid4()
    aggregate_id = uuid4()
    event = publish_domain_event(
        tenant_id,
        "human_resources.attendance.recorded",
        "attendance",
        aggregate_id,
        actor_id=ACTOR,
        correlation_id="corr-event-contract",
        payload={"employee_id": uuid4(), "attendance_date": date(2026, 7, 22), "status": "present"},
    )
    envelope = event.payload
    assert set(envelope) == {
        "event_id",
        "event_type",
        "schema_version",
        "tenant_id",
        "aggregate_type",
        "aggregate_id",
        "occurred_at",
        "actor_id",
        "correlation_id",
        "causation_id",
        "payload",
    }
    assert envelope["correlation_id"] == "corr-event-contract"
    assert envelope["event_type"] in EVENT_TYPES
    with pytest.raises(ValueError, match="Unsupported"):
        publish_domain_event(
            tenant_id,
            "human_resources.fake.succeeded",
            "attendance",
            aggregate_id,
            actor_id=ACTOR,
        )
    with pytest.raises(ValueError, match="non-allowlisted"):
        publish_domain_event(
            tenant_id,
            "human_resources.attendance.recorded",
            "attendance",
            aggregate_id,
            actor_id=ACTOR,
            payload={"email": "must-not-leak@example.test"},
        )

    context = ExtensionContext(tenant_id, ACTOR, "corr-extension")
    reference = MasterDataEmployeeReference(aggregate_id, "master-1", "1.0")
    submission = ApprovalSubmission("workflow-1", "pending")
    assert context.schema_version == "1.0"
    assert reference.master_record_id == "master-1"
    assert submission.state == "pending"
    assert MasterDataEmployeePort is not None
    assert WorkflowApprovalPort is not None
    assert BusinessCalendarPort is not None
    assert HumanResourcesEventSubscriber is not None
