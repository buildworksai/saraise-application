"""Production service contracts for tenant-safe, durable data migration."""

from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from rest_framework.exceptions import NotFound

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.modules.data_migration.adapters import SOURCE_ADAPTERS, TARGET_ADAPTERS
from src.modules.data_migration.models import (
    DataMigrationConfiguration,
    DataMigrationConfigurationAudit,
    ExternalConnection,
    MigrationChange,
    MigrationJob,
    MigrationJobVersion,
    MigrationMapping,
    MigrationRun,
    ValidationRule,
)
from src.modules.data_migration.schemas import (
    validate_rule_config,
    validate_source_config,
    validate_transform_config,
)
from src.modules.data_migration.services import (
    ConfigurationConflict,
    DataMigrationConfigurationService,
    ExternalConnectionService,
    MigrationExecutionService,
    MigrationJobService,
    MigrationMappingService,
    MigrationServiceError,
    ValidationRuleService,
)


class FakeSourceAdapter:
    def __init__(self, records: tuple[dict[str, object], ...] = ({"name": "Ada"},)) -> None:
        self.records = records

    def validate_config(self, config):
        return config

    def inspect(self, tenant_id, artifact_id, config, runtime):
        del tenant_id, artifact_id, config, runtime
        return {
            "fields": ({"name": "name", "type": "string"},),
            "representative_values": ({"name": "Ada", "email": "ada@example.test"},),
            "row_estimate": len(self.records),
            "source_checksum": "a" * 64,
            "warnings": (),
        }

    def iter_records(self, tenant_id, artifact_id, config, runtime):
        del tenant_id, artifact_id, config, runtime
        yield from self.records


class FakeTargetAdapter:
    def __init__(self) -> None:
        self.writes: list[dict[str, object]] = []

    def describe_schema(self, entity):
        del entity
        return {"fields": {"full_name": {"type": "string", "aliases": ["name"]}}}

    def validate_reference(self, entity, field, value, rule_type, config):
        del entity, field, rule_type, config
        return value != "invalid"

    def lookup(self, tenant_id, entity, fields):
        del tenant_id, entity, fields
        return None

    def write(self, tenant_id, entity, record, **context):
        self.writes.append(dict(record))
        return {
            "record_id": str(uuid.uuid4()),
            "operation": "create",
            "after_checksum": "b" * 64,
            "before_payload_encrypted": "",
            "idempotency_key": context["idempotency_key"],
        }

    def reverse(self, tenant_id, entity, record_id, **context):
        del tenant_id, entity, record_id, context
        return {"verified": True}


@pytest.fixture(autouse=True)
def adapter_registry(monkeypatch) -> tuple[FakeSourceAdapter, FakeTargetAdapter]:
    monkeypatch.setattr("src.modules.dms.services.VersionService.get_version", lambda self, tenant, actor, version: object())
    monkeypatch.setattr("src.modules.data_migration.services._validate_connection_destination", lambda values: None)
    SOURCE_ADAPTERS.clear()
    TARGET_ADAPTERS.clear()
    source = FakeSourceAdapter()
    target = FakeTargetAdapter()
    SOURCE_ADAPTERS.register("core.csv", source)
    TARGET_ADAPTERS.register("core.record", target)
    yield source, target
    SOURCE_ADAPTERS.clear()
    TARGET_ADAPTERS.clear()


@pytest.fixture
def identities() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def job_command(name: str = "Customer import") -> dict[str, object]:
    return {
        "name": name,
        "description": "Deterministic customer import",
        "source_type": "csv",
        "source_artifact_id": uuid.uuid4(),
        "source_config": {"encoding": "utf-8", "batch_size": 2},
        "target_adapter": "core.record",
        "target_entity": "customer",
        "write_mode": "create",
        "lookup_fields": [],
    }


@pytest.mark.django_db
def test_job_create_binds_tenant_persists_version_and_outbox(identities) -> None:
    tenant, other_tenant, actor = identities
    command = {**job_command(), "tenant_id": other_tenant}
    job = MigrationJobService.create(tenant, actor, command)
    assert job.tenant_id == tenant
    version = MigrationJobVersion.objects.get(job=job, version=1)
    assert version.snapshot["name"] == job.name
    event = OutboxEvent.objects.get(aggregate_id=job.id, event_type="data_migration.job.created")
    assert event.tenant_id == tenant
    assert event.payload["payload"] == {"version": 1, "status": "draft"}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "source_type,config",
    (
        ("database", {"connection_id": str(uuid.uuid4()), "table": "users; DROP TABLE x", "columns": ["id"]}),
        ("database", {"connection_id": str(uuid.uuid4()), "table": "users", "columns": ["id"], "sql": "SELECT *"}),
        ("api", {"connection_id": str(uuid.uuid4()), "relative_path": "https://internal.test/data"}),
        ("api", {"connection_id": str(uuid.uuid4()), "relative_path": "/data", "method": "POST"}),
    ),
)
def test_unsafe_source_configuration_fails_without_persistence(identities, source_type, config) -> None:
    tenant, _, actor = identities
    command = {**job_command(), "source_type": source_type, "source_artifact_id": None, "source_config": config}
    with pytest.raises((ValueError, MigrationServiceError, ValidationError)):
        MigrationJobService.create(tenant, actor, command)
    assert not MigrationJob.objects.filter(tenant_id=tenant).exists()
    assert not OutboxEvent.objects.filter(tenant_id=tenant).exists()


@pytest.mark.django_db
def test_job_update_is_optimistic_versioned_and_revises_ready(identities) -> None:
    tenant, _, actor = identities
    job = MigrationJobService.create(tenant, actor, job_command())
    job.status = MigrationJob.Status.READY
    job.save(update_fields=("status", "updated_at"))
    updated = MigrationJobService.update(tenant, job.id, actor, {"description": "Changed"}, expected_version=1)
    assert updated.configuration_version == 2
    assert updated.status == MigrationJob.Status.DRAFT
    assert list(MigrationJobVersion.objects.filter(job=job).values_list("version", flat=True).order_by("version")) == [1, 2]
    with pytest.raises(ConfigurationConflict):
        MigrationJobService.update(tenant, job.id, actor, {"description": "Stale"}, expected_version=1)
    updated.refresh_from_db()
    assert updated.description == "Changed"


@pytest.mark.django_db
def test_mapping_and_rule_mutations_validate_and_bump_definition_version(identities) -> None:
    tenant, _, actor = identities
    job = MigrationJobService.create(tenant, actor, job_command())
    mapping = MigrationMappingService.create(
        tenant, job.id, actor,
        {"source_field": "name", "target_field": "full_name", "position": 0, "transform_type": "identity", "transform_config": {}},
    )
    job.refresh_from_db()
    assert mapping.tenant_id == tenant and job.configuration_version == 2
    rule = ValidationRuleService.create(
        tenant, job.id, actor,
        {"field_name": "full_name", "rule_type": "required", "rule_config": {}, "error_message": "Name required", "severity": "error", "position": 0},
    )
    job.refresh_from_db()
    assert rule.tenant_id == tenant and job.configuration_version == 3
    with pytest.raises((ValueError, MigrationServiceError)):
        MigrationMappingService.update(tenant, mapping.id, actor, {"transform_type": "unknown"})
    with pytest.raises((ValueError, MigrationServiceError)):
        ValidationRuleService.update(tenant, rule.id, actor, {"rule_type": "regex", "rule_config": {"pattern": "(a+)+"}})


@pytest.mark.django_db
def test_cross_tenant_parent_and_entity_access_is_not_found(identities) -> None:
    tenant_a, tenant_b, actor = identities
    job_b = MigrationJobService.create(tenant_b, actor, job_command("Tenant B"))
    with pytest.raises(NotFound):
        MigrationMappingService.create(
            tenant_a, job_b.id, actor,
            {"source_field": "name", "target_field": "full_name", "position": 0, "transform_type": "identity", "transform_config": {}},
        )
    mapping_b = MigrationMappingService.create(
        tenant_b, job_b.id, actor,
        {"source_field": "name", "target_field": "full_name", "position": 0, "transform_type": "identity", "transform_config": {}},
    )
    with pytest.raises(NotFound):
        MigrationMappingService.update(tenant_a, mapping_b.id, actor, {"source_field": "stolen"})
    mapping_b.refresh_from_db()
    assert mapping_b.source_field == "name"


@pytest.mark.django_db
def test_definition_export_import_checksum_and_identity_safety(identities) -> None:
    tenant_a, tenant_b, actor = identities
    job = MigrationJobService.create(tenant_a, actor, job_command())
    MigrationMappingService.create(
        tenant_a, job.id, actor,
        {"source_field": "name", "target_field": "full_name", "position": 0, "transform_type": "identity", "transform_config": {}},
    )
    document = MigrationJobService.export_definition(tenant_a, job.id)
    assert "tenant_id" not in document and "job_id" not in document
    imported = MigrationJobService.import_definition(tenant_b, actor, document)
    assert imported.tenant_id == tenant_b
    assert imported.mappings.count() == 1
    tampered = {**document, "description": "tampered"}
    with pytest.raises(MigrationServiceError, match="checksum"):
        MigrationJobService.import_definition(tenant_b, actor, tampered)
    with pytest.raises(MigrationServiceError):
        MigrationJobService.import_definition(tenant_b, actor, {**document, "tenant_id": str(tenant_a)})


@pytest.mark.django_db
def test_configuration_preview_update_export_import_restore_and_audit(identities) -> None:
    tenant, _, actor = identities
    config = DataMigrationConfigurationService.get(tenant)
    preview = DataMigrationConfigurationService.preview(tenant, {"batch_size": 250})
    assert preview == {"from_version": 1, "changes": [{"field": "batch_size", "before": 500, "after": 250}]}
    updated = DataMigrationConfigurationService.update(tenant, actor, {"batch_size": 250}, 1, "corr-config-1")
    assert updated.version == 2 and updated.batch_size == 250
    audit = DataMigrationConfigurationAudit.objects.get(configuration=config, version=2)
    assert audit.before["batch_size"] == 500 and audit.after["batch_size"] == 250
    assert audit.correlation_id == "corr-config-1"
    document = DataMigrationConfigurationService.export(tenant)
    DataMigrationConfigurationService.import_document(tenant, actor, document, expected_version=2)
    restored = DataMigrationConfigurationService.restore(tenant, actor, version=2, expected_version=3)
    assert restored.version == 4 and restored.batch_size == 250
    with pytest.raises(ConfigurationConflict):
        DataMigrationConfigurationService.update(tenant, actor, {"batch_size": 10}, 1)
    with pytest.raises(MigrationServiceError):
        DataMigrationConfigurationService.import_document(tenant, actor, {**document, "checksum": "0" * 64}, 4)


@pytest.mark.django_db
def test_configuration_target_adapter_allowlist_is_runtime_configurable(identities) -> None:
    tenant, _, actor = identities
    config = DataMigrationConfigurationService.get(tenant)
    updated = DataMigrationConfigurationService.update(
        tenant, actor, {"allowed_target_adapters": ["core.record", "crm.customer"]}, config.version
    )
    assert updated.allowed_target_adapters == ["core.record", "crm.customer"]
    exported = DataMigrationConfigurationService.export(tenant)
    assert exported["configuration"]["allowed_target_adapters"] == ["core.record", "crm.customer"]


@pytest.mark.django_db
def test_run_request_is_durable_idempotent_and_conflict_safe(identities, adapter_registry) -> None:
    tenant, _, actor = identities
    job = MigrationJobService.create(tenant, actor, job_command())
    MigrationMappingService.create(
        tenant, job.id, actor,
        {"source_field": "name", "target_field": "full_name", "position": 0, "transform_type": "identity", "transform_config": {}},
    )
    result = MigrationJobService.validate_definition(tenant, job.id, actor)
    assert result.valid
    run = MigrationExecutionService.request_run(tenant, job.id, actor, "dry_run", "run-key-1")
    repeated = MigrationExecutionService.request_run(tenant, job.id, actor, "dry_run", "run-key-1")
    assert repeated.id == run.id
    assert AsyncJob.objects.filter(id=run.async_job_id, status="queued").exists()
    assert OutboxEvent.objects.filter(aggregate_id=run.id, event_type="data_migration.run.queued").exists()
    with pytest.raises(MigrationServiceError, match="Idempotency"):
        MigrationExecutionService.request_run(tenant, job.id, actor, "commit", "run-key-1")
    completed = MigrationExecutionService.execute(tenant, run.id)
    assert completed.status == MigrationRun.Status.SUCCEEDED
    assert completed.processed_records == completed.succeeded_records == 1
    assert not adapter_registry[1].writes
    assert not MigrationChange.objects.filter(run=completed).exists()


@pytest.mark.django_db
def test_run_request_rejects_non_ready_job_without_async_evidence(identities) -> None:
    tenant, _, actor = identities
    job = MigrationJobService.create(tenant, actor, job_command())
    before_jobs = AsyncJob.objects.count()
    with pytest.raises(MigrationServiceError, match="ready"):
        MigrationExecutionService.request_run(tenant, job.id, actor, "commit", "not-ready")
    assert AsyncJob.objects.count() == before_jobs
    assert not MigrationRun.objects.filter(job=job).exists()


@pytest.mark.django_db
def test_external_connection_rejects_secret_material_and_cross_tenant_access(identities) -> None:
    tenant_a, tenant_b, actor = identities
    payload = {
        "name": "Warehouse", "kind": "postgresql", "host": "db.example.test", "port": 5432,
        "database": "warehouse", "username": "readonly", "credential_ref": "vault://migration/warehouse",
        "tls_mode": "verify-full", "public_options": {},
    }
    connection = ExternalConnectionService.register(tenant_b, actor, payload)
    assert connection.credential_ref == "vault://migration/warehouse"
    with pytest.raises(MigrationServiceError, match="Secret material"):
        ExternalConnectionService.register(tenant_a, actor, {**payload, "name": "Unsafe", "password": "plaintext"})
    with pytest.raises(NotFound):
        ExternalConnectionService.update(tenant_a, connection.id, actor, {"name": "Stolen"})
    connection.refresh_from_db()
    assert connection.name == "Warehouse"


@pytest.mark.parametrize(
    "operation,args",
    (
        (validate_source_config, ("xml", {"record_path": "/rows/row", "batch_size": 1})),
        (validate_transform_config, ("boolean_map", {"true_values": ["yes"], "false_values": ["no"]})),
        (validate_rule_config, ("allowed_values", {"values": ["a", "b"]})),
    ),
)
def test_schema_variants_accept_bounded_known_configuration(operation, args) -> None:
    assert operation(*args)


@pytest.mark.parametrize(
    "operation,args",
    (
        (validate_source_config, ("api", {"connection_id": str(uuid.uuid4()), "relative_path": "//internal"})),
        (validate_transform_config, ("regex_replace", {"pattern": "(a+)+", "replacement": ""})),
        (validate_rule_config, ("unknown", {})),
        (validate_rule_config, ("allowed_values", {"values": list(range(1001))})),
    ),
)
def test_schema_variants_fail_closed(operation, args) -> None:
    with pytest.raises(ValueError):
        operation(*args)
