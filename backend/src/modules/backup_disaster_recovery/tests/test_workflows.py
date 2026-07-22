from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from ..adapter_registry import register_backup_catalog, register_extension_action, register_storage_adapter
from ..models import (
    DRExercise,
    ExerciseStatus,
    RecoveryPointStatus,
    RestoreRunStatus,
    RunbookActionType,
    ScopeType,
    StepFailureBehavior,
)
from ..ports import BackupArtifactDescriptor, BackupType
from ..ports import ScopeType as PortScopeType
from ..services import (
    BackupExecutionFacade,
    DomainConflict,
    DRExerciseService,
    ExerciseCommand,
    RecoveryObjectiveService,
    RecoveryPointService,
    RestoreRunCommand,
    RestoreService,
    RunbookCommand,
    RunbookService,
    RunbookStepCommand,
)
from .test_services import Catalog, Storage


@pytest.fixture
def workflow_context():
    tenant_id = uuid.uuid4()
    actor = uuid.uuid4()
    now = timezone.now()
    descriptor = BackupArtifactDescriptor(
        backup_job_id=uuid.uuid4(),
        backup_archive_id=None,
        adapter_key="workflow-storage",
        artifact_locator_ref="artifact.bin",
        encryption_key_ref=None,
        scope_type=PortScopeType.TENANT,
        scope_ref="primary",
        backup_type=BackupType.FULL,
        data_cutoff_at=now - timedelta(minutes=5),
        captured_at=now,
        expires_at=now + timedelta(days=30),
        size_bytes=4,
        checksum_algorithm="sha256",
        checksum_digest="a" * 64,
        provider_acknowledgement="ack-workflow",
    )
    register_backup_catalog("default", Catalog(descriptor), replace=True)
    register_storage_adapter("workflow-storage", Storage(), replace=True)
    point = BackupExecutionFacade().register_recovery_point(tenant_id, actor, descriptor.backup_job_id)
    job = RecoveryPointService().request_verification(tenant_id, actor, point.id, "workflow-point")
    point = RecoveryPointService().execute_verification(tenant_id, point.id, job.id)
    return tenant_id, actor, descriptor, point


def create_published_runbook(tenant_id, actor, *, steps):
    service = RunbookService()
    runbook = service.create_runbook(
        tenant_id,
        actor,
        RunbookCommand(
            name="Workflow recovery",
            slug=f"workflow-{uuid.uuid4().hex[:8]}",
            description="End-to-end evidence",
            scope_type=ScopeType.TENANT,
            scope_ref="primary",
            adapter_key="workflow-storage",
            rpo_target_seconds=3600,
            rto_target_seconds=7200,
            owner_id=actor,
        ),
    )
    for position, (action_type, parameters, on_failure, extension_key) in enumerate(steps, 1):
        service.create_step(
            tenant_id,
            actor,
            RunbookStepCommand(
                runbook_id=runbook.id,
                step_key=f"step-{position}",
                position=position,
                name=f"Step {position}",
                description="Typed action",
                action_type=action_type,
                parameters=parameters,
                timeout_seconds=300,
                retry_limit=0,
                on_failure=on_failure,
                extension_action_key=extension_key,
            ),
        )
    return service.publish(tenant_id, actor, runbook.id, f"publish-{runbook.id}")


@pytest.mark.django_db
def test_runbook_draft_mutations_reorder_and_delete(workflow_context):
    tenant_id, actor, _, _ = workflow_context
    service = RunbookService()
    draft = service.create_runbook(
        tenant_id,
        actor,
        RunbookCommand(
            "Draft",
            "draft",
            "",
            ScopeType.TENANT,
            "primary",
            "workflow-storage",
            60,
            120,
            actor,
        ),
    )
    draft = service.update_draft(tenant_id, actor, draft.id, {"name": "Updated draft", "rpo_target_seconds": 90})
    first = service.create_step(
        tenant_id,
        actor,
        RunbookStepCommand(
            draft.id,
            "one",
            1,
            "One",
            "",
            RunbookActionType.VALIDATE_RECOVERY_POINT,
            {},
            30,
            0,
            "stop",
        ),
    )
    second = service.create_step(
        tenant_id,
        actor,
        RunbookStepCommand(
            draft.id,
            "two",
            2,
            "Two",
            "",
            RunbookActionType.VERIFY,
            {},
            30,
            0,
            "stop",
        ),
    )
    second = service.update_step(tenant_id, actor, second.id, {"name": "Second"})
    ordered = service.reorder_steps(tenant_id, actor, draft.id, [second.id, first.id])
    assert [item.position for item in ordered] == [1, 2]
    service.soft_delete_step(tenant_id, actor, first.id)
    service.soft_delete_draft(tenant_id, actor, draft.id)
    assert draft.name == "Updated draft"


@pytest.mark.django_db
def test_exercise_success_restore_and_objective_reports(workflow_context):
    tenant_id, actor, _, point = workflow_context
    runbook = create_published_runbook(
        tenant_id,
        actor,
        steps=[
            (RunbookActionType.VALIDATE_RECOVERY_POINT, {}, "stop", None),
            (RunbookActionType.RESTORE, {"restore_mode": "full"}, "stop", None),
        ],
    )
    service = DRExerciseService()
    exercise = service.schedule_exercise(
        tenant_id,
        actor,
        ExerciseCommand(
            "Quarterly restore",
            runbook.id,
            "full",
            "isolated",
            timezone.now(),
            "exercise-success",
            point.id,
        ),
    )
    exercise = service.update_scheduled_exercise(tenant_id, actor, exercise.id, {"name": "Updated exercise"})
    job = service.start_exercise(tenant_id, actor, exercise.id, "exercise-start")
    completed = service.execute_exercise(tenant_id, exercise.id, job.id)
    assert completed.status == ExerciseStatus.PASSED
    assert completed.step_executions.count() == 2
    summary = RecoveryObjectiveService().get_readiness_summary(tenant_id)
    assert summary.latest_passed_exercise == completed
    assert summary.provider_state == "operational"
    report = RecoveryObjectiveService().report_objectives(tenant_id, {"bucket": "day"})
    assert report.bucket == "day"


@pytest.mark.django_db
def test_exercise_degraded_evidence_never_passes(workflow_context):
    tenant_id, actor, _, point = workflow_context
    runbook = create_published_runbook(
        tenant_id,
        actor,
        steps=[
            (
                RunbookActionType.NOTIFY,
                {"channel_ref": "ops", "message_template": "started"},
                StepFailureBehavior.CONTINUE_DEGRADED,
                None,
            )
        ],
    )
    exercise = DRExerciseService().schedule_exercise(
        tenant_id,
        actor,
        ExerciseCommand("Degraded", runbook.id, "tabletop", "isolated", timezone.now(), "degraded", point.id),
    )
    job = DRExerciseService().start_exercise(tenant_id, actor, exercise.id, "degraded-start")
    completed = DRExerciseService().execute_exercise(tenant_id, exercise.id, job.id)
    assert completed.status == ExerciseStatus.FAILED
    assert completed.evidence_summary["degraded"] is True


@pytest.mark.django_db
def test_exercise_extension_and_cancel(workflow_context):
    tenant_id, actor, _, point = workflow_context
    register_extension_action("test-action", lambda **kwargs: {"succeeded": bool(kwargs["job_id"])}, replace=True)
    runbook = create_published_runbook(
        tenant_id,
        actor,
        steps=[(RunbookActionType.EXTENSION, {"configuration_ref": "safe"}, "stop", "test-action")],
    )
    service = DRExerciseService()
    scheduled = service.schedule_exercise(
        tenant_id,
        actor,
        ExerciseCommand("Extension", runbook.id, "tabletop", "standby", timezone.now(), "extension", point.id),
    )
    job = service.start_exercise(tenant_id, actor, scheduled.id, "extension-start")
    assert service.execute_exercise(tenant_id, scheduled.id, job.id).status == ExerciseStatus.PASSED
    cancelled = service.schedule_exercise(
        tenant_id,
        actor,
        ExerciseCommand("Cancel", runbook.id, "tabletop", "isolated", timezone.now(), "cancel", point.id),
    )
    assert service.cancel_exercise(tenant_id, actor, cancelled.id, "cancel-1").status == ExerciseStatus.CANCELLED


@pytest.mark.django_db
def test_exercise_without_matching_point_fails_closed(workflow_context):
    tenant_id, actor, _, _ = workflow_context
    runbook = create_published_runbook(
        tenant_id,
        actor,
        steps=[(RunbookActionType.VERIFY, {}, "stop", None)],
    )
    runbook.scope_ref = "unprotected-scope"
    DRExercise.objects.filter(pk=uuid.uuid4()).exists()  # exercise a harmless tenant query path
    # The published record is immutable; create a second tenant with no point instead.
    other_tenant = uuid.uuid4()
    register_storage_adapter("workflow-storage", Storage(), replace=True)
    other = RunbookService().create_runbook(
        other_tenant,
        actor,
        RunbookCommand("No point", "no-point", "", ScopeType.TENANT, "missing", "workflow-storage", 60, 60, actor),
    )
    RunbookService().create_step(
        other_tenant,
        actor,
        RunbookStepCommand(other.id, "verify", 1, "Verify", "", RunbookActionType.VERIFY, {}, 30, 0, "stop"),
    )
    other = RunbookService().publish(other_tenant, actor, other.id, "publish-no-point")
    exercise = DRExerciseService().schedule_exercise(
        other_tenant,
        actor,
        ExerciseCommand("No point", other.id, "tabletop", "isolated", timezone.now(), "no-point"),
    )
    job = DRExerciseService().start_exercise(other_tenant, actor, exercise.id, "no-point-start")
    assert DRExerciseService().execute_exercise(other_tenant, exercise.id, job.id).status == ExerciseStatus.FAILED


@pytest.mark.django_db
def test_restore_validation_failure_cancel_and_conflict(workflow_context):
    tenant_id, actor, _, point = workflow_context
    first = RestoreService().create_restore_run(
        tenant_id,
        actor,
        RestoreRunCommand(point.id, "isolated", "busy", "full", (), "restore-first"),
    )
    with pytest.raises(DomainConflict, match="active operation"):
        RestoreService().create_restore_run(
            tenant_id,
            actor,
            RestoreRunCommand(point.id, "isolated", "busy", "full", (), "restore-second"),
        )
    assert (
        RestoreService().cancel_restore(tenant_id, actor, first.id, "cancel-restore").status
        == RestoreRunStatus.CANCELLED
    )
    with pytest.raises(DomainConflict, match="preflight"):
        RestoreService().execute_restore(tenant_id, actor, first.id, "too-late")


@pytest.mark.django_db
def test_expired_recovery_point_transitions(workflow_context):
    tenant_id, actor, _, point = workflow_context
    # Retention is an immutable artifact fact; create an already-expired descriptor-backed point.
    expired = point.__class__.objects.create(
        tenant_id=tenant_id,
        backup_job_id=uuid.uuid4(),
        adapter_key="workflow-storage",
        artifact_locator_ref="expired.bin",
        scope_type=ScopeType.TENANT,
        scope_ref="primary",
        backup_type="full",
        data_cutoff_at=timezone.now() - timedelta(days=2),
        captured_at=timezone.now() - timedelta(days=1),
        expires_at=timezone.now() - timedelta(hours=1),
        checksum_digest="b" * 64,
        created_by=actor,
    )
    verify_job = RecoveryPointService().request_verification(tenant_id, actor, expired.id, "expired-verify")
    # A fake descriptor for this second point is intentionally absent, so transition it with the state machine path.
    from ..state_machines import RECOVERY_POINT_MACHINE

    expired = RECOVERY_POINT_MACHINE.apply(
        expired, "mark_available", tenant_id=tenant_id, transition_key=f"job:{verify_job.id}:available"
    )
    assert (
        RecoveryPointService().expire_recovery_point(tenant_id, actor, expired.id, "expire-now").status
        == RecoveryPointStatus.EXPIRED
    )
