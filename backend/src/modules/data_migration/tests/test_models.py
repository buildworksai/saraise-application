"""Domain model, constraint, immutability, and state-machine contracts."""

from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import models

from src.core.state_machine import IdempotencyConflictError, IllegalTransitionError, TerminalStateError
from src.core.tenancy import TenantScopedModel, TimestampedModel
from src.modules.data_migration.models import (
    DataMigrationConfiguration,
    DataMigrationConfigurationAudit,
    ExternalConnection,
    ImmutableEvidenceError,
    MigrationChange,
    MigrationJob,
    MigrationJobVersion,
    MigrationMapping,
    MigrationRollback,
    MigrationRun,
    MigrationRunIssue,
    ValidationRule,
)
from src.modules.data_migration.state_machines import JOB_MACHINE, RUN_MACHINE

TENANT_MODELS = (
    ExternalConnection, MigrationJob, MigrationJobVersion, MigrationMapping, ValidationRule,
    MigrationRun, MigrationRunIssue, MigrationChange, MigrationRollback,
    DataMigrationConfiguration, DataMigrationConfigurationAudit,
)


def test_every_domain_entity_has_native_uuid_identity_and_indexed_uuid_tenant() -> None:
    for model in TENANT_MODELS:
        assert issubclass(model, TenantScopedModel)
        assert isinstance(model._meta.pk, models.UUIDField)
        tenant_field = model._meta.get_field("tenant_id")
        assert isinstance(tenant_field, models.UUIDField)
        assert tenant_field.db_index and not tenant_field.null


def test_every_mutable_entity_has_timestamps() -> None:
    for model in (ExternalConnection, MigrationJob, MigrationMapping, ValidationRule, MigrationRun, MigrationRollback, DataMigrationConfiguration):
        assert issubclass(model, TimestampedModel)
        assert model._meta.get_field("created_at")
        assert model._meta.get_field("updated_at")


def test_expected_unique_constraints_and_indexes_are_declared() -> None:
    assert {item.name for item in MigrationJob._meta.constraints} >= {"dm_job_live_name_uniq", "dm_job_version_gte_1"}
    assert {item.name for item in MigrationRun._meta.constraints} >= {"dm_run_idempotency_uniq", "dm_run_processed_lte_total"}
    assert {item.name for item in MigrationMapping._meta.constraints} >= {
        "dm_mapping_source_uniq", "dm_mapping_target_uniq", "dm_mapping_position_uniq", "dm_mapping_confidence_range"
    }
    assert {item.name for item in DataMigrationConfiguration._meta.constraints} >= {"dm_config_tenant_uniq", "dm_config_batch_range"}
    assert all(index.fields[0] == "tenant_id" for model in TENANT_MODELS for index in model._meta.indexes)


@pytest.mark.django_db
def test_job_configuration_constraints_and_string_representation() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    job = MigrationJob(
        tenant_id=tenant, name="Customers", source_type="csv", source_artifact_id=uuid.uuid4(),
        source_config={"encoding": "utf-8"}, target_adapter="core.record", target_entity="customer", created_by=actor,
    )
    job.full_clean()
    assert str(job) == "Customers (draft)"
    missing_artifact = MigrationJob(
        tenant_id=tenant, name="Unsafe", source_type="csv", source_config={},
        target_adapter="core.record", target_entity="customer", created_by=actor,
    )
    with pytest.raises(ValidationError, match="artifact"):
        missing_artifact.full_clean()
    invalid_upsert = MigrationJob(
        tenant_id=tenant, name="Upsert", source_type="csv", source_artifact_id=uuid.uuid4(), source_config={},
        target_adapter="core.record", target_entity="customer", write_mode="upsert", lookup_fields=[], created_by=actor,
    )
    with pytest.raises(ValidationError, match="lookup"):
        invalid_upsert.full_clean()


@pytest.mark.django_db
def test_cross_tenant_mapping_rule_and_version_parents_are_rejected() -> None:
    tenant_a, tenant_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    job = MigrationJob.objects.create(
        tenant_id=tenant_b, name="Tenant B", source_type="csv", source_artifact_id=uuid.uuid4(),
        source_config={}, target_adapter="core.record", target_entity="record", created_by=actor,
    )
    mapping = MigrationMapping(
        tenant_id=tenant_a, job=job, source_field="a", target_field="b", position=0,
        transform_type="identity", transform_config={}, created_by=actor,
    )
    rule = ValidationRule(
        tenant_id=tenant_a, job=job, field_name="b", rule_type="required", rule_config={},
        error_message="Required", position=0, created_by=actor,
    )
    version = MigrationJobVersion(
        tenant_id=tenant_a, job=job, version=1,
        snapshot={"tenant_id": str(tenant_a), "job_id": str(job.id)}, change_summary="bad",
        created_by=actor, correlation_id="corr",
    )
    for candidate in (mapping, rule, version):
        with pytest.raises(ValidationError, match="tenant|match"):
            candidate.full_clean()


@pytest.mark.django_db
def test_append_only_version_rejects_save_update_and_delete() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    job = MigrationJob.objects.create(
        tenant_id=tenant, name="Versioned", source_type="csv", source_artifact_id=uuid.uuid4(),
        source_config={}, target_adapter="core.record", target_entity="record", created_by=actor,
    )
    version = MigrationJobVersion.objects.create(
        tenant_id=tenant, job=job, version=1,
        snapshot={"tenant_id": str(tenant), "job_id": str(job.id)}, change_summary="initial",
        created_by=actor, correlation_id="corr",
    )
    version.change_summary = "tampered"
    with pytest.raises(ImmutableEvidenceError):
        version.save()
    with pytest.raises(ImmutableEvidenceError):
        MigrationJobVersion.objects.filter(pk=version.pk).update(change_summary="tampered")
    with pytest.raises(ImmutableEvidenceError):
        version.delete()


@pytest.mark.django_db
def test_issue_sample_rejects_unredacted_pii() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    job = MigrationJob.objects.create(
        tenant_id=tenant, name="Issues", source_type="csv", source_artifact_id=uuid.uuid4(),
        source_config={}, target_adapter="core.record", target_entity="record", created_by=actor,
    )
    version = MigrationJobVersion.objects.create(
        tenant_id=tenant, job=job, version=1, snapshot={"tenant_id": str(tenant), "job_id": str(job.id)},
        change_summary="initial", created_by=actor, correlation_id="corr",
    )
    run = MigrationRun.objects.create(
        tenant_id=tenant, job=job, job_version=version, async_job_id=uuid.uuid4(), mode="dry_run",
        idempotency_key="issues", source_checksum="a" * 64, created_by=actor, correlation_id="corr",
    )
    unsafe = MigrationRunIssue(
        tenant_id=tenant, run=run, row_number=1, stage="validation", severity="error", code="EMAIL",
        message="Invalid", redacted_sample={"email": "person@example.test"},
    )
    with pytest.raises(ValidationError, match="redact"):
        unsafe.full_clean()
    safe = MigrationRunIssue(
        tenant_id=tenant, run=run, row_number=1, stage="validation", severity="error", code="EMAIL",
        message="Invalid", redacted_sample={"email": "[REDACTED]"},
    )
    safe.full_clean()


@pytest.mark.django_db
def test_change_before_image_invariants() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    job = MigrationJob.objects.create(
        tenant_id=tenant, name="Changes", source_type="csv", source_artifact_id=uuid.uuid4(), source_config={},
        target_adapter="core.record", target_entity="record", created_by=actor,
    )
    version = MigrationJobVersion.objects.create(
        tenant_id=tenant, job=job, version=1, snapshot={"tenant_id": str(tenant), "job_id": str(job.id)},
        change_summary="initial", created_by=actor, correlation_id="corr",
    )
    run = MigrationRun.objects.create(
        tenant_id=tenant, job=job, job_version=version, async_job_id=uuid.uuid4(), mode="commit",
        idempotency_key="changes", source_checksum="a" * 64, created_by=actor, correlation_id="corr",
    )
    common = dict(
        tenant_id=tenant, run=run, sequence=1, target_adapter="core.record", target_entity="record",
        target_record_id="1", after_checksum="b" * 64, idempotency_key="change-1",
    )
    with pytest.raises(ValidationError):
        MigrationChange(**common, operation="create", before_payload_encrypted="encrypted").full_clean()
    with pytest.raises(ValidationError):
        MigrationChange(**common, operation="update", before_payload_encrypted="").full_clean()


@pytest.mark.django_db
def test_job_state_machine_legal_idempotent_conflicting_and_illegal() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    job = MigrationJob.objects.create(
        tenant_id=tenant, name="State", source_type="csv", source_artifact_id=uuid.uuid4(), source_config={},
        target_adapter="core.record", target_entity="record", created_by=actor,
    )
    ready = JOB_MACHINE.apply(job, "validate", transition_key="validate-1")
    assert ready.status == "ready" and len(ready.transition_history) == 1
    repeated = JOB_MACHINE.apply(ready, "validate", transition_key="validate-1")
    assert repeated.status == "ready" and len(repeated.transition_history) == 1
    with pytest.raises(IdempotencyConflictError):
        JOB_MACHINE.apply(repeated, "archive", transition_key="validate-1")
    with pytest.raises(IllegalTransitionError):
        JOB_MACHINE.apply(repeated, "restore", transition_key="restore-illegal")


@pytest.mark.django_db
def test_run_and_rollback_terminal_states_are_immutable() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    job = MigrationJob.objects.create(
        tenant_id=tenant, name="Terminal", source_type="csv", source_artifact_id=uuid.uuid4(), source_config={},
        target_adapter="core.record", target_entity="record", created_by=actor,
    )
    version = MigrationJobVersion.objects.create(
        tenant_id=tenant, job=job, version=1, snapshot={"tenant_id": str(tenant), "job_id": str(job.id)},
        change_summary="initial", created_by=actor, correlation_id="corr",
    )
    run = MigrationRun.objects.create(
        tenant_id=tenant, job=job, job_version=version, async_job_id=uuid.uuid4(), mode="commit",
        idempotency_key="terminal", source_checksum="a" * 64, created_by=actor, correlation_id="corr",
    )
    cancelled = RUN_MACHINE.apply(run, "cancel", transition_key="cancel")
    with pytest.raises(TerminalStateError):
        RUN_MACHINE.apply(cancelled, "start", transition_key="start-after-cancel")


@pytest.mark.django_db
def test_configuration_defaults_and_safe_bounds() -> None:
    config = DataMigrationConfiguration(tenant_id=uuid.uuid4(), created_by=uuid.uuid4())
    assert config.batch_size == 500
    assert config.preview_row_limit == 100
    assert config.allowed_target_adapters == ["core.record"]
    config.batch_size = 0
    with pytest.raises(ValidationError):
        config.full_clean()
    config.batch_size = 500
    config.enabled_roles = ["root"]
    with pytest.raises(ValidationError, match="rollout role"):
        config.full_clean()
