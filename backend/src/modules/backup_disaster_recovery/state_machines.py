"""Canonical state machines for disaster-recovery aggregates.

These are the sole command vocabulary for lifecycle mutations.  Services add
the operation-specific evidence and timestamps inside the surrounding atomic
transaction, then delegate the actual state/history mutation here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from django.db import models
from django.utils import timezone

from src.core.state_machine import StateMachine, StateMachineConfigurationError, Transition

from .models import (
    DRExercise,
    DRRunbook,
    DRStepExecution,
    ExerciseStatus,
    RecoveryPoint,
    RecoveryPointStatus,
    RestoreRun,
    RestoreRunStatus,
    RunbookStatus,
    StepExecutionStatus,
)


def _past_retention(record: RecoveryPoint) -> bool:
    return record.expires_at is not None and record.expires_at <= timezone.now()


class ConfiguredStateMachine:
    """Resolve the validated workflow for the aggregate tenant on every use."""

    def __init__(
        self,
        key: str,
        model: type[models.Model],
        allowed_states: tuple[str, ...],
    ) -> None:
        self.key = key
        self.model = model
        self.allowed_states = frozenset(allowed_states)
        self.name = f"backup_disaster_recovery.{key}"

    def _definition(self, tenant_id: UUID | None) -> Mapping[str, object]:
        from .services import DEFAULT_CONFIGURATION_DOCUMENT, get_configuration

        document = get_configuration(tenant_id).document if tenant_id is not None else DEFAULT_CONFIGURATION_DOCUMENT
        workflows = document.get("workflows")
        definition = workflows.get(self.key) if isinstance(workflows, Mapping) else None
        if not isinstance(definition, Mapping):
            raise StateMachineConfigurationError(f"Workflow {self.key!r} is unavailable")
        return definition

    def _build(self, tenant_id: UUID | None) -> StateMachine[Any]:
        definition = self._definition(tenant_id)
        raw_states = definition.get("states")
        raw_terminal = definition.get("terminal_states")
        raw_transitions = definition.get("transitions")
        raw_guards = definition.get("retention_guard_commands")
        if not isinstance(raw_states, list) or set(raw_states) != self.allowed_states:
            raise StateMachineConfigurationError(f"Workflow {self.key!r} states do not match the domain model")
        if not isinstance(raw_terminal, list) or not isinstance(raw_transitions, list):
            raise StateMachineConfigurationError(f"Workflow {self.key!r} is malformed")
        if not isinstance(raw_guards, list) or not all(isinstance(item, str) for item in raw_guards):
            raise StateMachineConfigurationError(f"Workflow {self.key!r} guards are malformed")
        guarded_commands = frozenset(raw_guards)
        transitions: list[Transition] = []
        for raw in raw_transitions:
            if not isinstance(raw, Mapping):
                raise StateMachineConfigurationError(f"Workflow {self.key!r} transition is malformed")
            try:
                command = str(raw["command"])
                source = str(raw["from_state"])
                target = str(raw["to_state"])
            except KeyError as exc:
                raise StateMachineConfigurationError(f"Workflow {self.key!r} transition is malformed") from exc
            guards = (_past_retention,) if command in guarded_commands else ()
            transitions.append(Transition(command, source, target, guards))
        return StateMachine(
            name=self.name,
            model=self.model,
            states=raw_states,
            terminal_states=raw_terminal,
            transitions=transitions,
        )

    @staticmethod
    def _tenant_id(args: tuple[object, ...], kwargs: Mapping[str, object]) -> UUID | None:
        raw = kwargs.get("tenant_id")
        if raw is None:
            aggregate = kwargs.get("aggregate")
            if aggregate is None:
                aggregate = next((item for item in args if isinstance(item, models.Model)), None)
            raw = getattr(aggregate, "tenant_id", None)
        if raw is None:
            return None
        try:
            return raw if isinstance(raw, UUID) else UUID(str(raw))
        except (TypeError, ValueError, AttributeError) as exc:
            raise StateMachineConfigurationError("Workflow invocation requires a tenant UUID") from exc

    def apply(self, *args: object, **kwargs: object) -> models.Model:
        return self._build(self._tenant_id(args, kwargs)).apply(*args, **kwargs)

    def allowed_commands(self, state: str, *, tenant_id: UUID | None = None) -> tuple[str, ...]:
        return self._build(tenant_id).allowed_commands(state)

    @property
    def states(self) -> frozenset[str]:
        return self._build(None).states

    @property
    def terminal_states(self) -> frozenset[str]:
        return self._build(None).terminal_states

    @property
    def transitions(self) -> tuple[Transition, ...]:
        return self._build(None).transitions


RECOVERY_POINT_MACHINE = ConfiguredStateMachine("recovery_point", RecoveryPoint, tuple(RecoveryPointStatus.values))
RESTORE_RUN_MACHINE = ConfiguredStateMachine("restore_run", RestoreRun, tuple(RestoreRunStatus.values))
RUNBOOK_MACHINE = ConfiguredStateMachine("runbook", DRRunbook, tuple(RunbookStatus.values))
EXERCISE_MACHINE = ConfiguredStateMachine("exercise", DRExercise, tuple(ExerciseStatus.values))
STEP_EXECUTION_MACHINE = ConfiguredStateMachine("step_execution", DRStepExecution, tuple(StepExecutionStatus.values))


# Lowercase aliases are retained for ergonomic imports in extension modules.
recovery_point_state_machine = RECOVERY_POINT_MACHINE
restore_run_state_machine = RESTORE_RUN_MACHINE
runbook_state_machine = RUNBOOK_MACHINE
exercise_state_machine = EXERCISE_MACHINE
step_execution_state_machine = STEP_EXECUTION_MACHINE


__all__ = [
    "EXERCISE_MACHINE",
    "RECOVERY_POINT_MACHINE",
    "RESTORE_RUN_MACHINE",
    "RUNBOOK_MACHINE",
    "STEP_EXECUTION_MACHINE",
    "exercise_state_machine",
    "recovery_point_state_machine",
    "restore_run_state_machine",
    "runbook_state_machine",
    "step_execution_state_machine",
]
