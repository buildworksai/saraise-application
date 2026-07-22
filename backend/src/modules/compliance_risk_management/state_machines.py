"""Declarative lifecycle transitions for compliance-risk aggregates.

The resolver is intentionally persistence-free.  Services own guards,
idempotency keys, row locks, history recording, and outbox publication; this
module provides one authoritative transition graph shared by those services,
serializers, documentation, and extension adapters.
"""

from __future__ import annotations

from collections.abc import Mapping

from django.core.exceptions import ValidationError

from .models import (
    CalendarEntryStatus,
    ControlStatus,
    ControlTestStatus,
    RemediationStatus,
    RequirementStatus,
    RiskStatus,
)

TransitionMap = Mapping[str, Mapping[str, str]]


class InvalidTransition(ValidationError):
    """A command is unknown or illegal from the aggregate's current state."""


RISK_TRANSITIONS: dict[str, dict[str, str]] = {
    "assess": {RiskStatus.IDENTIFIED: RiskStatus.ASSESSED},
    "start_mitigation": {RiskStatus.ASSESSED: RiskStatus.MITIGATING},
    "accept": {
        RiskStatus.ASSESSED: RiskStatus.ACCEPTED,
        RiskStatus.MITIGATING: RiskStatus.ACCEPTED,
    },
    "close": {
        RiskStatus.ASSESSED: RiskStatus.CLOSED,
        RiskStatus.MITIGATING: RiskStatus.CLOSED,
        RiskStatus.ACCEPTED: RiskStatus.CLOSED,
    },
    "reopen": {
        RiskStatus.ACCEPTED: RiskStatus.ASSESSED,
        RiskStatus.CLOSED: RiskStatus.ASSESSED,
    },
}

CONTROL_TRANSITIONS: dict[str, dict[str, str]] = {
    "activate": {ControlStatus.DRAFT: ControlStatus.ACTIVE},
    "retire": {ControlStatus.ACTIVE: ControlStatus.RETIRED},
    "reactivate": {ControlStatus.RETIRED: ControlStatus.ACTIVE},
}

CONTROL_TEST_TRANSITIONS: dict[str, dict[str, str]] = {
    "start": {ControlTestStatus.SCHEDULED: ControlTestStatus.IN_PROGRESS},
    "cancel": {ControlTestStatus.SCHEDULED: ControlTestStatus.CANCELLED},
    "record_result": {ControlTestStatus.IN_PROGRESS: ControlTestStatus.COMPLETED},
}

REQUIREMENT_TRANSITIONS: dict[str, dict[str, str]] = {
    "assess_compliant": {RequirementStatus.NOT_ASSESSED: RequirementStatus.COMPLIANT},
    "assess_partial": {
        RequirementStatus.NOT_ASSESSED: RequirementStatus.PARTIALLY_COMPLIANT,
        RequirementStatus.COMPLIANT: RequirementStatus.PARTIALLY_COMPLIANT,
        RequirementStatus.NON_COMPLIANT: RequirementStatus.PARTIALLY_COMPLIANT,
    },
    "assess_non_compliant": {
        RequirementStatus.NOT_ASSESSED: RequirementStatus.NON_COMPLIANT,
        RequirementStatus.COMPLIANT: RequirementStatus.NON_COMPLIANT,
        RequirementStatus.PARTIALLY_COMPLIANT: RequirementStatus.NON_COMPLIANT,
    },
    "remediate": {
        RequirementStatus.PARTIALLY_COMPLIANT: RequirementStatus.COMPLIANT,
        RequirementStatus.NON_COMPLIANT: RequirementStatus.COMPLIANT,
    },
}

CALENDAR_TRANSITIONS: dict[str, dict[str, str]] = {
    "mark_overdue": {CalendarEntryStatus.UPCOMING: CalendarEntryStatus.OVERDUE},
    "complete": {
        CalendarEntryStatus.UPCOMING: CalendarEntryStatus.COMPLETED,
        CalendarEntryStatus.OVERDUE: CalendarEntryStatus.COMPLETED,
    },
    "cancel": {
        CalendarEntryStatus.UPCOMING: CalendarEntryStatus.CANCELLED,
        CalendarEntryStatus.OVERDUE: CalendarEntryStatus.CANCELLED,
    },
}

REMEDIATION_TRANSITIONS: dict[str, dict[str, str]] = {
    "start": {RemediationStatus.PLANNED: RemediationStatus.IN_PROGRESS},
    "mark_overdue": {
        RemediationStatus.PLANNED: RemediationStatus.OVERDUE,
        RemediationStatus.IN_PROGRESS: RemediationStatus.OVERDUE,
    },
    "complete": {
        RemediationStatus.IN_PROGRESS: RemediationStatus.COMPLETED,
        RemediationStatus.OVERDUE: RemediationStatus.COMPLETED,
    },
    "cancel": {
        RemediationStatus.PLANNED: RemediationStatus.CANCELLED,
        RemediationStatus.IN_PROGRESS: RemediationStatus.CANCELLED,
        RemediationStatus.OVERDUE: RemediationStatus.CANCELLED,
    },
}


def resolve_transition(current_status: str, command: str, transitions: TransitionMap) -> str:
    """Return the target state or raise a stable, field-addressable error.

    Idempotency is deliberately keyed and enforced by services before this
    resolver is called.  A repeated command with a *different* key remains an
    illegal transition, which prevents duplicate terminal history/events.
    """

    command_transitions = transitions.get(command)
    if command_transitions is None:
        raise InvalidTransition(
            {"command": f"Unknown transition command: {command}."},
            code="unknown_transition",
        )
    target = command_transitions.get(current_status)
    if target is not None:
        return str(target)
    raise InvalidTransition(
        {"command": f"Command {command!r} is not allowed from state {current_status!r}."},
        code="invalid_transition",
    )


def transition_risk(current_status: str, command: str) -> str:
    return resolve_transition(current_status, command, RISK_TRANSITIONS)


def transition_control(current_status: str, command: str) -> str:
    return resolve_transition(current_status, command, CONTROL_TRANSITIONS)


def transition_control_test(current_status: str, command: str) -> str:
    return resolve_transition(current_status, command, CONTROL_TEST_TRANSITIONS)


def transition_requirement(current_status: str, command: str) -> str:
    return resolve_transition(current_status, command, REQUIREMENT_TRANSITIONS)


def transition_calendar(current_status: str, command: str) -> str:
    return resolve_transition(current_status, command, CALENDAR_TRANSITIONS)


def transition_remediation(current_status: str, command: str) -> str:
    return resolve_transition(current_status, command, REMEDIATION_TRANSITIONS)


# Concise compatibility alias for service callers.
transition_test = transition_control_test


__all__ = [
    "CALENDAR_TRANSITIONS",
    "CONTROL_TEST_TRANSITIONS",
    "CONTROL_TRANSITIONS",
    "InvalidTransition",
    "REMEDIATION_TRANSITIONS",
    "REQUIREMENT_TRANSITIONS",
    "RISK_TRANSITIONS",
    "resolve_transition",
    "transition_calendar",
    "transition_control",
    "transition_control_test",
    "transition_remediation",
    "transition_requirement",
    "transition_risk",
    "transition_test",
]
