"""Domain invariants and lifecycle tests."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from src.core.tenancy import TenantScopedModel, TimestampedModel
from src.modules.backup_disaster_recovery.models import (
    BDRConfiguration,
    BDRConfigurationVersion,
    DRExercise,
    DRRunbook,
    DRStepExecution,
    RecoveryPoint,
    RecoveryPointEvidence,
    RecoveryPointStatus,
    RestoreRun,
    RunbookActionType,
    RunbookStatus,
    RunbookStep,
    ScopeType,
    StepExecutionStatus,
    TargetEnvironment,
)
from src.modules.backup_disaster_recovery.services import get_configuration
from src.modules.backup_disaster_recovery.state_machines import (
    RECOVERY_POINT_MACHINE,
    RUNBOOK_MACHINE,
    STEP_EXECUTION_MACHINE,
)

from .factories import (
    exercise_factory,
    recovery_point_factory,
    runbook_factory,
    runbook_step_factory,
    step_execution_factory,
)


@pytest.mark.parametrize(
    "model",
    [
        RecoveryPoint,
        RestoreRun,
        DRRunbook,
        RunbookStep,
        DRExercise,
        DRStepExecution,
        BDRConfiguration,
        BDRConfigurationVersion,
        RecoveryPointEvidence,
    ],
)
def test_domain_models_use_canonical_tenant_and_timestamp_bases(model: type) -> None:
    assert issubclass(model, TenantScopedModel)
    assert issubclass(model, TimestampedModel)
    assert model._meta.get_field("id").get_internal_type() == "UUIDField"
    tenant_field = model._meta.get_field("tenant_id")
    assert tenant_field.get_internal_type() == "UUIDField"
    assert tenant_field.db_index is True


@pytest.mark.django_db
def test_recovery_point_validates_integrity_and_artifact_time() -> None:
    now = timezone.now()
    point = RecoveryPoint(
        tenant_id=uuid.uuid4(),
        backup_job_id=uuid.uuid4(),
        adapter_key="open-source",
        artifact_locator_ref="vault:artifact/one",
        scope_type=ScopeType.TENANT,
        scope_ref="primary",
        backup_type="full",
        data_cutoff_at=now - timedelta(seconds=1),
        captured_at=now,
        checksum_digest="NOT-A-DIGEST",
        created_by=uuid.uuid4(),
    )
    with pytest.raises(ValidationError) as raised:
        point.full_clean()
    assert "checksum_digest" in raised.value.message_dict

    point.checksum_digest = "a" * 64
    point.data_cutoff_at = now + timedelta(seconds=1)
    with pytest.raises(ValidationError) as raised:
        point.full_clean()
    assert "data_cutoff_at" in raised.value.message_dict


@pytest.mark.django_db
def test_recovery_point_artifact_facts_are_immutable() -> None:
    point = recovery_point_factory()
    point.scope_ref = "different"
    with pytest.raises(ValidationError, match="immutable"):
        point.save()


@pytest.mark.django_db
def test_recovery_point_state_machine_is_audited_and_expiry_is_guarded() -> None:
    future_point = recovery_point_factory(expires_at=timezone.now() + timedelta(days=1))
    RECOVERY_POINT_MACHINE.apply(future_point, "begin_verification", transition_key="future-verify-1")
    RECOVERY_POINT_MACHINE.apply(future_point, "mark_available", transition_key="future-verify-2")
    with pytest.raises(Exception, match="Guard"):
        RECOVERY_POINT_MACHINE.apply(future_point, "expire", transition_key="expire-too-soon")

    now = timezone.now()
    point = recovery_point_factory(
        data_cutoff_at=now - timedelta(days=3),
        captured_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )
    RECOVERY_POINT_MACHINE.apply(point, "begin_verification", transition_key="verify-1")
    RECOVERY_POINT_MACHINE.apply(point, "mark_available", transition_key="verify-2")
    expired = RECOVERY_POINT_MACHINE.apply(point, "expire", transition_key="expire-1")
    assert expired.status == RecoveryPointStatus.EXPIRED
    assert [entry["command"] for entry in expired.transition_history] == [
        "begin_verification",
        "mark_available",
        "expire",
    ]


@pytest.mark.django_db
def test_evidence_models_reject_instance_and_queryset_hard_delete() -> None:
    point = recovery_point_factory()
    with pytest.raises(ProtectedError):
        point.delete()
    with pytest.raises(ProtectedError):
        RecoveryPoint.objects.filter(pk=point.pk).delete()
    with pytest.raises(ValidationError, match="Bulk updates"):
        RecoveryPoint.objects.filter(pk=point.pk).update(scope_ref="rewritten")


@pytest.mark.django_db
def test_restore_requires_same_tenant_and_production_approval() -> None:
    point = recovery_point_factory()
    run = RestoreRun(
        tenant_id=point.tenant_id,
        recovery_point=point,
        target_environment=TargetEnvironment.PRODUCTION,
        target_ref="production-primary",
        restore_mode="full",
        idempotency_key="production-restore",
        requested_by=uuid.uuid4(),
        requested_at=timezone.now(),
    )
    with pytest.raises(ValidationError) as raised:
        run.full_clean()
    assert "approved_by" in raised.value.message_dict

    run.target_environment = TargetEnvironment.ISOLATED
    run.tenant_id = uuid.uuid4()
    with pytest.raises(ValidationError) as raised:
        run.full_clean()
    assert "recovery_point" in raised.value.message_dict


@pytest.mark.django_db
def test_runbook_supersedes_only_same_tenant_and_slug() -> None:
    published = runbook_factory(status=RunbookStatus.PUBLISHED)
    with pytest.raises(ValidationError, match="same tenant"):
        runbook_factory(
            tenant_id=uuid.uuid4(),
            slug=published.slug,
            version=2,
            supersedes=published,
        )


@pytest.mark.django_db
def test_published_runbook_is_immutable_but_can_retire() -> None:
    runbook = runbook_factory()
    RUNBOOK_MACHINE.apply(runbook, "publish", transition_key="publish-1")
    runbook.name = "Rewritten instructions"
    with pytest.raises(ValidationError, match="immutable"):
        runbook.save()

    runbook.refresh_from_db()
    retired = RUNBOOK_MACHINE.apply(runbook, "retire", transition_key="retire-1")
    assert retired.status == RunbookStatus.RETIRED


@pytest.mark.django_db
def test_step_action_shape_validation_errors_are_explicit() -> None:
    runbook = runbook_factory()
    with pytest.raises(ValidationError) as raised:
        runbook_step_factory(
            runbook,
            action_type=RunbookActionType.EXTENSION,
            extension_action_key=None,
            parameters={},
        )
    assert "extension_action_key" in raised.value.message_dict

    with pytest.raises(ValidationError) as raised:
        runbook_step_factory(
            runbook,
            parameters={"callback_url": "https://example.invalid"},
        )
    assert "parameters" in raised.value.message_dict


@pytest.mark.django_db
def test_relations_are_tenant_and_runbook_version_safe() -> None:
    runbook = runbook_factory()
    step = runbook_step_factory(runbook)
    RUNBOOK_MACHINE.apply(runbook, "publish", transition_key="publish-for-exercise")
    exercise = exercise_factory(runbook)
    execution = DRStepExecution(
        tenant_id=uuid.uuid4(),
        exercise=exercise,
        runbook_step=step,
    )
    with pytest.raises(ValidationError, match="same tenant"):
        execution.full_clean()


@pytest.mark.django_db
def test_step_execution_identity_and_terminal_evidence_are_append_only() -> None:
    runbook = runbook_factory()
    step = runbook_step_factory(runbook)
    RUNBOOK_MACHINE.apply(runbook, "publish", transition_key="publish-step-runbook")
    exercise = exercise_factory(runbook)
    execution = step_execution_factory(exercise, step)
    STEP_EXECUTION_MACHINE.apply(execution, "start", transition_key="step-start")
    terminal = STEP_EXECUTION_MACHINE.apply(execution, "pass", transition_key="step-pass")
    assert terminal.status == StepExecutionStatus.PASSED

    terminal.evidence = {"rewritten": True}
    with pytest.raises(ValidationError, match="immutable"):
        terminal.save()


@pytest.mark.django_db
def test_configuration_versions_are_tenant_bound_and_immutable() -> None:
    tenant_id = uuid.uuid4()
    tenant_defaults = get_configuration(tenant_id)
    configuration = BDRConfiguration.objects.create(
        tenant_id=tenant_id,
        environment="default",
        document=tenant_defaults.document,
        rollout=tenant_defaults.rollout,
    )
    version = BDRConfigurationVersion.objects.create(
        tenant_id=tenant_id,
        configuration=configuration,
        version=1,
        actor_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
        prior_value={},
        new_value={"document": configuration.document, "rollout": configuration.rollout},
    )

    version.new_value = {"tampered": True}
    with pytest.raises(ValidationError, match="immutable"):
        version.save()
    with pytest.raises(ValidationError, match="Bulk updates"):
        BDRConfigurationVersion.objects.filter(pk=version.pk).update(new_value={})
    with pytest.raises(ProtectedError):
        version.delete()
    with pytest.raises(ProtectedError):
        BDRConfigurationVersion.objects.filter(pk=version.pk).delete()

    foreign_tenant_id = uuid.uuid4()
    foreign_defaults = get_configuration(foreign_tenant_id)
    foreign_configuration = BDRConfiguration.objects.create(
        tenant_id=foreign_tenant_id,
        environment="default",
        document=foreign_defaults.document,
        rollout=foreign_defaults.rollout,
    )
    cross_tenant = BDRConfigurationVersion(
        tenant_id=tenant_id,
        configuration=foreign_configuration,
        version=1,
        actor_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
        prior_value={},
        new_value={},
    )
    with pytest.raises(ValidationError, match="same tenant"):
        cross_tenant.full_clean()


@pytest.mark.django_db
def test_recovery_point_evidence_is_append_only_and_tenant_bound() -> None:
    point = recovery_point_factory()
    evidence = RecoveryPointEvidence.objects.create(
        tenant_id=point.tenant_id,
        recovery_point=point,
        sequence=1,
        actor_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
        evidence={"valid": True, "checksum_matches": True},
    )

    evidence.evidence = {"valid": False}
    with pytest.raises(ValidationError, match="immutable"):
        evidence.save()
    with pytest.raises(ValidationError, match="Bulk updates"):
        RecoveryPointEvidence.objects.filter(pk=evidence.pk).update(evidence={})
    with pytest.raises(ProtectedError):
        evidence.delete()
    with pytest.raises(ProtectedError):
        RecoveryPointEvidence.objects.filter(pk=evidence.pk).delete()

    cross_tenant = RecoveryPointEvidence(
        tenant_id=uuid.uuid4(),
        recovery_point=point,
        sequence=2,
        actor_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
        evidence={},
    )
    with pytest.raises(ValidationError, match="same tenant"):
        cross_tenant.full_clean()
