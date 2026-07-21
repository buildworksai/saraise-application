"""Canonical state machines for disaster-recovery aggregates.

These are the sole command vocabulary for lifecycle mutations.  Services add
the operation-specific evidence and timestamps inside the surrounding atomic
transaction, then delegate the actual state/history mutation here.
"""

from __future__ import annotations

from django.utils import timezone

from src.core.state_machine import StateMachine, Transition

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


RECOVERY_POINT_MACHINE = StateMachine(
    name="backup_disaster_recovery.recovery_point",
    model=RecoveryPoint,
    states=RecoveryPointStatus.values,
    terminal_states=(RecoveryPointStatus.DELETED,),
    transitions=(
        Transition("begin_verification", RecoveryPointStatus.DISCOVERED, RecoveryPointStatus.VERIFYING),
        Transition("begin_verification", RecoveryPointStatus.AVAILABLE, RecoveryPointStatus.VERIFYING),
        Transition("mark_available", RecoveryPointStatus.VERIFYING, RecoveryPointStatus.AVAILABLE),
        Transition("mark_corrupt", RecoveryPointStatus.VERIFYING, RecoveryPointStatus.CORRUPT),
        Transition("expire", RecoveryPointStatus.AVAILABLE, RecoveryPointStatus.EXPIRED, (_past_retention,)),
        Transition("delete", RecoveryPointStatus.EXPIRED, RecoveryPointStatus.DELETED),
        Transition("delete", RecoveryPointStatus.CORRUPT, RecoveryPointStatus.DELETED),
    ),
)


RESTORE_RUN_MACHINE = StateMachine(
    name="backup_disaster_recovery.restore_run",
    model=RestoreRun,
    states=RestoreRunStatus.values,
    terminal_states=(
        RestoreRunStatus.SUCCEEDED,
        RestoreRunStatus.FAILED,
        RestoreRunStatus.CANCELLED,
    ),
    transitions=(
        Transition("begin_validation", RestoreRunStatus.QUEUED, RestoreRunStatus.VALIDATING),
        Transition("mark_ready", RestoreRunStatus.VALIDATING, RestoreRunStatus.READY),
        Transition("begin_restore", RestoreRunStatus.READY, RestoreRunStatus.RESTORING),
        Transition("begin_verification", RestoreRunStatus.RESTORING, RestoreRunStatus.VERIFYING),
        Transition("succeed", RestoreRunStatus.VERIFYING, RestoreRunStatus.SUCCEEDED),
        Transition("fail", RestoreRunStatus.VALIDATING, RestoreRunStatus.FAILED),
        Transition("fail", RestoreRunStatus.RESTORING, RestoreRunStatus.FAILED),
        Transition("fail", RestoreRunStatus.VERIFYING, RestoreRunStatus.FAILED),
        Transition("cancel", RestoreRunStatus.QUEUED, RestoreRunStatus.CANCELLED),
        Transition("cancel", RestoreRunStatus.VALIDATING, RestoreRunStatus.CANCELLED),
        Transition("cancel", RestoreRunStatus.READY, RestoreRunStatus.CANCELLED),
    ),
)


RUNBOOK_MACHINE = StateMachine(
    name="backup_disaster_recovery.runbook",
    model=DRRunbook,
    states=RunbookStatus.values,
    terminal_states=(RunbookStatus.RETIRED,),
    transitions=(
        Transition("publish", RunbookStatus.DRAFT, RunbookStatus.PUBLISHED),
        Transition("retire", RunbookStatus.PUBLISHED, RunbookStatus.RETIRED),
    ),
)


EXERCISE_MACHINE = StateMachine(
    name="backup_disaster_recovery.exercise",
    model=DRExercise,
    states=ExerciseStatus.values,
    terminal_states=(ExerciseStatus.PASSED, ExerciseStatus.FAILED, ExerciseStatus.CANCELLED),
    transitions=(
        Transition("queue", ExerciseStatus.SCHEDULED, ExerciseStatus.QUEUED),
        Transition("start", ExerciseStatus.QUEUED, ExerciseStatus.RUNNING),
        Transition("pass", ExerciseStatus.RUNNING, ExerciseStatus.PASSED),
        Transition("fail", ExerciseStatus.RUNNING, ExerciseStatus.FAILED),
        Transition("cancel", ExerciseStatus.SCHEDULED, ExerciseStatus.CANCELLED),
        Transition("cancel", ExerciseStatus.QUEUED, ExerciseStatus.CANCELLED),
        Transition("cancel", ExerciseStatus.RUNNING, ExerciseStatus.CANCELLED),
    ),
)


STEP_EXECUTION_MACHINE = StateMachine(
    name="backup_disaster_recovery.step_execution",
    model=DRStepExecution,
    states=StepExecutionStatus.values,
    terminal_states=(
        StepExecutionStatus.PASSED,
        StepExecutionStatus.FAILED,
        StepExecutionStatus.DEGRADED,
        StepExecutionStatus.SKIPPED,
    ),
    transitions=(
        Transition("start", StepExecutionStatus.PENDING, StepExecutionStatus.RUNNING),
        Transition("pass", StepExecutionStatus.RUNNING, StepExecutionStatus.PASSED),
        Transition("fail", StepExecutionStatus.RUNNING, StepExecutionStatus.FAILED),
        Transition("degrade", StepExecutionStatus.RUNNING, StepExecutionStatus.DEGRADED),
        Transition("skip", StepExecutionStatus.PENDING, StepExecutionStatus.SKIPPED),
    ),
)


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
