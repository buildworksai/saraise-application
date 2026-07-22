"""Declarative lifecycle authorities for Human Resources aggregates."""

from __future__ import annotations

from datetime import date
from typing import Any, Final, cast

from django.utils import timezone

from src.core.state_machine import JSONFieldTransitionRecorder, StateMachine, TransitionRecord, registry

from .models import Employee, EmploymentStatus, LeaveRequest, LeaveRequestStatus

EMPLOYEE_MACHINE_NAME: Final = "human_resources.employee_lifecycle"
LEAVE_REQUEST_MACHINE_NAME: Final = "human_resources.leave_request"


class EmployeeLifecycleRecorder(JSONFieldTransitionRecorder[Employee]):
    """Synchronize lifecycle companion fields for direct machine consumers."""

    def record(self, aggregate: Employee, record: TransitionRecord) -> None:
        super().record(aggregate, record)
        aggregate.is_active = record.to_state in {
            EmploymentStatus.ACTIVE,
            EmploymentStatus.ON_LEAVE,
        }
        if record.to_state == EmploymentStatus.TERMINATED:
            raw_date = record.metadata.get("effective_date")
            aggregate.termination_date = raw_date if isinstance(raw_date, date) else date.fromisoformat(str(raw_date))
            aggregate.termination_reason = str(record.metadata.get("reason") or "")
        else:
            aggregate.termination_date = None
            aggregate.termination_reason = ""
        actor_id = str(record.metadata.get("actor_id") or "").strip()
        if actor_id:
            aggregate.updated_by = actor_id

    def aggregate_update_fields(self) -> tuple[str, ...]:
        return (
            "transition_history",
            "is_active",
            "termination_date",
            "termination_reason",
            "updated_by",
        )


class LeaveRequestLifecycleRecorder(JSONFieldTransitionRecorder[LeaveRequest]):
    """Populate status metadata before generic StateMachine persistence."""

    def record(self, aggregate: LeaveRequest, record: TransitionRecord) -> None:
        super().record(aggregate, record)
        actor_id = str(record.metadata.get("actor_id") or "").strip()
        occurred_at = timezone.now()
        if record.command == "approve":
            aggregate.approved_by = actor_id
            aggregate.approved_at = occurred_at
        elif record.command == "reject":
            aggregate.rejection_reason = str(record.metadata.get("reason") or "").strip()
        elif record.command == "cancel":
            aggregate.cancelled_by = actor_id
            aggregate.cancelled_at = occurred_at
        if actor_id:
            aggregate.updated_by = actor_id

    def aggregate_update_fields(self) -> tuple[str, ...]:
        return (
            "transition_history",
            "approved_by",
            "approved_at",
            "rejection_reason",
            "cancelled_by",
            "cancelled_at",
            "updated_by",
        )


EMPLOYEE_LIFECYCLE_MACHINE: Final[StateMachine[Employee]] = StateMachine(
    name=EMPLOYEE_MACHINE_NAME,
    model=Employee,
    states=tuple(EmploymentStatus.values),
    terminal_states=(EmploymentStatus.TERMINATED,),
    state_field="employment_status",
    history_field="transition_history",
    recorder=EmployeeLifecycleRecorder(),
    transitions=(
        {"command": "place_on_leave", "from": EmploymentStatus.ACTIVE, "to": EmploymentStatus.ON_LEAVE},
        {"command": "return_from_leave", "from": EmploymentStatus.ON_LEAVE, "to": EmploymentStatus.ACTIVE},
        {
            "command": "deactivate",
            "from": (EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE),
            "to": EmploymentStatus.INACTIVE,
        },
        {"command": "activate", "from": EmploymentStatus.INACTIVE, "to": EmploymentStatus.ACTIVE},
        {
            "command": "terminate",
            "from": (EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE, EmploymentStatus.INACTIVE),
            "to": EmploymentStatus.TERMINATED,
        },
    ),
)

LEAVE_REQUEST_MACHINE: Final[StateMachine[LeaveRequest]] = StateMachine(
    name=LEAVE_REQUEST_MACHINE_NAME,
    model=LeaveRequest,
    states=tuple(LeaveRequestStatus.values),
    terminal_states=(LeaveRequestStatus.REJECTED, LeaveRequestStatus.CANCELLED),
    state_field="status",
    history_field="transition_history",
    recorder=LeaveRequestLifecycleRecorder(),
    transitions=(
        {"command": "approve", "from": LeaveRequestStatus.PENDING, "to": LeaveRequestStatus.APPROVED},
        {"command": "reject", "from": LeaveRequestStatus.PENDING, "to": LeaveRequestStatus.REJECTED},
        {
            "command": "cancel",
            "from": (LeaveRequestStatus.PENDING, LeaveRequestStatus.APPROVED),
            "to": LeaveRequestStatus.CANCELLED,
        },
    ),
)


def register_state_machines() -> None:
    """Register both machines idempotently while detecting name collisions."""

    for name, machine in (
        (EMPLOYEE_MACHINE_NAME, EMPLOYEE_LIFECYCLE_MACHINE),
        (LEAVE_REQUEST_MACHINE_NAME, LEAVE_REQUEST_MACHINE),
    ):
        try:
            current = registry.get(name)
        except LookupError:
            current = None
        if current is None:
            registry.register(name, cast(StateMachine[Any], machine))
        elif current is not machine:
            raise RuntimeError(f"A different state machine is already registered as {name!r}")


__all__ = [
    "EMPLOYEE_LIFECYCLE_MACHINE",
    "EMPLOYEE_MACHINE_NAME",
    "EmployeeLifecycleRecorder",
    "LEAVE_REQUEST_MACHINE",
    "LEAVE_REQUEST_MACHINE_NAME",
    "LeaveRequestLifecycleRecorder",
    "register_state_machines",
]
