"""Small typed factories for disaster-recovery tests."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from django.utils import timezone

from ..models import (
    DRExercise,
    DRRunbook,
    DRStepExecution,
    ExerciseEnvironment,
    ExerciseType,
    RecoveryPoint,
    RestoreMode,
    RestoreRun,
    RunbookActionType,
    RunbookStatus,
    RunbookStep,
    ScopeType,
    TargetEnvironment,
)


def recovery_point_factory(**overrides: Any) -> RecoveryPoint:
    now = timezone.now()
    values: dict[str, Any] = {
        "tenant_id": uuid.uuid4(),
        "backup_job_id": uuid.uuid4(),
        "adapter_key": "open-source",
        "artifact_locator_ref": "vault:artifact/example",
        "scope_type": ScopeType.TENANT,
        "scope_ref": "tenant-primary",
        "backup_type": "full",
        "data_cutoff_at": now - timedelta(minutes=3),
        "captured_at": now,
        "expires_at": now + timedelta(days=30),
        "size_bytes": 4096,
        "checksum_digest": "a" * 64,
        "created_by": uuid.uuid4(),
    }
    values.update(overrides)
    return RecoveryPoint.objects.create(**values)


def runbook_factory(**overrides: Any) -> DRRunbook:
    actor_id = uuid.uuid4()
    values: dict[str, Any] = {
        "tenant_id": uuid.uuid4(),
        "name": "Primary recovery",
        "slug": f"primary-{uuid.uuid4().hex[:8]}",
        "status": RunbookStatus.DRAFT,
        "scope_type": ScopeType.TENANT,
        "scope_ref": "tenant-primary",
        "adapter_key": "open-source",
        "rpo_target_seconds": 3600,
        "rto_target_seconds": 7200,
        "owner_id": actor_id,
        "created_by": actor_id,
        "updated_by": actor_id,
    }
    values.update(overrides)
    return DRRunbook.objects.create(**values)


def runbook_step_factory(runbook: DRRunbook, **overrides: Any) -> RunbookStep:
    actor_id = uuid.uuid4()
    values: dict[str, Any] = {
        "tenant_id": runbook.tenant_id,
        "runbook": runbook,
        "step_key": f"step-{uuid.uuid4().hex[:8]}",
        "position": runbook.steps.count() + 1,
        "name": "Validate recovery point",
        "action_type": RunbookActionType.VALIDATE_RECOVERY_POINT,
        "parameters": {},
        "created_by": actor_id,
        "updated_by": actor_id,
    }
    values.update(overrides)
    return RunbookStep.objects.create(**values)


def exercise_factory(runbook: DRRunbook, **overrides: Any) -> DRExercise:
    values: dict[str, Any] = {
        "tenant_id": runbook.tenant_id,
        "name": "Quarterly resilience exercise",
        "runbook": runbook,
        "exercise_type": ExerciseType.TABLETOP,
        "environment": ExerciseEnvironment.ISOLATED,
        "scheduled_for": timezone.now() + timedelta(days=1),
        "idempotency_key": f"exercise-{uuid.uuid4()}",
        "initiated_by": uuid.uuid4(),
    }
    values.update(overrides)
    return DRExercise.objects.create(**values)


def restore_run_factory(recovery_point: RecoveryPoint, **overrides: Any) -> RestoreRun:
    values: dict[str, Any] = {
        "tenant_id": recovery_point.tenant_id,
        "recovery_point": recovery_point,
        "target_environment": TargetEnvironment.ISOLATED,
        "target_ref": f"sandbox-{uuid.uuid4()}",
        "restore_mode": RestoreMode.FULL,
        "idempotency_key": f"restore-{uuid.uuid4()}",
        "requested_by": uuid.uuid4(),
        "requested_at": timezone.now(),
    }
    values.update(overrides)
    return RestoreRun.objects.create(**values)


def step_execution_factory(
    exercise: DRExercise,
    runbook_step: RunbookStep,
    **overrides: Any,
) -> DRStepExecution:
    values: dict[str, Any] = {
        "tenant_id": exercise.tenant_id,
        "exercise": exercise,
        "runbook_step": runbook_step,
        "attempt": 1,
    }
    values.update(overrides)
    return DRStepExecution.objects.create(**values)
