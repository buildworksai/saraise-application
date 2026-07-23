"""Persistence proof for tenant configuration and immutable evidence."""

from __future__ import annotations

import importlib
import uuid

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from src.core.module_registry_models import ModuleRegistryEntry
from src.core.tenancy import TenantScopedModel
from src.modules.customization_framework.models import (
    ConfigurationAuditRecord,
    CustomFieldDefinitionVersion,
    IdempotentCommand,
    LifecycleTransitionRecord,
    PublicationRecord,
    RuntimeConfiguration,
    RuntimeConfigurationVersion,
)

from .factories import CustomFieldDefinitionFactory

pytestmark = pytest.mark.django_db

EVIDENCE_MODELS = (
    RuntimeConfigurationVersion,
    ConfigurationAuditRecord,
    CustomFieldDefinitionVersion,
    IdempotentCommand,
    LifecycleTransitionRecord,
    PublicationRecord,
)


def _configuration(
    tenant_id: uuid.UUID | None = None,
    *,
    actor_id: uuid.UUID | None = None,
) -> RuntimeConfiguration:
    return RuntimeConfiguration.objects.create(
        tenant_id=tenant_id or uuid.uuid4(),
        document={"limits": {"max_json_bytes": 65536}},
        version=1,
        environment="development",
        updated_by=actor_id or uuid.uuid4(),
    )


def test_runtime_configuration_uses_unique_indexed_tenant_uuid() -> None:
    assert issubclass(RuntimeConfiguration, TenantScopedModel)
    tenant_field = RuntimeConfiguration._meta.get_field("tenant_id")
    assert tenant_field.get_internal_type() == "UUIDField"
    assert tenant_field.db_index is True
    assert tenant_field.unique is True

    configuration = _configuration()
    with pytest.raises((IntegrityError, ValidationError)), transaction.atomic():
        _configuration(configuration.tenant_id)


@pytest.mark.parametrize("model", EVIDENCE_MODELS)
def test_every_evidence_model_is_tenant_scoped_and_indexed(model: type) -> None:
    assert issubclass(model, TenantScopedModel)
    tenant_field = model._meta.get_field("tenant_id")
    assert tenant_field.get_internal_type() == "UUIDField"
    assert tenant_field.db_index is True


def test_configuration_versions_and_audits_preserve_actor_and_correlation() -> None:
    actor_id = uuid.uuid4()
    correlation_id = uuid.uuid4()
    configuration = _configuration(actor_id=actor_id)
    version = RuntimeConfigurationVersion.objects.create(
        tenant_id=configuration.tenant_id,
        configuration=configuration,
        version=1,
        document=configuration.document,
        environment=configuration.environment,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    audit = ConfigurationAuditRecord.objects.create(
        tenant_id=configuration.tenant_id,
        configuration=configuration,
        version=1,
        action="create",
        before=None,
        after=configuration.document,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )

    assert version.document == configuration.document
    assert version.actor_id == actor_id
    assert version.correlation_id == correlation_id
    assert audit.before is None
    assert audit.after == configuration.document
    assert audit.actor_id == actor_id
    assert audit.correlation_id == correlation_id


def test_configuration_evidence_rejects_cross_tenant_parent_references() -> None:
    configuration = _configuration()
    version = RuntimeConfigurationVersion(
        tenant_id=uuid.uuid4(),
        configuration=configuration,
        version=1,
        document=configuration.document,
        environment=configuration.environment,
        actor_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
    )
    audit = ConfigurationAuditRecord(
        tenant_id=uuid.uuid4(),
        configuration=configuration,
        version=1,
        action="create",
        before=None,
        after=configuration.document,
        actor_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
    )

    with pytest.raises(ValidationError):
        version.full_clean()
    with pytest.raises(ValidationError):
        audit.full_clean()


def test_field_definition_versions_are_tenant_isolated_snapshots() -> None:
    own = CustomFieldDefinitionFactory()
    foreign = CustomFieldDefinitionFactory()
    own_version = CustomFieldDefinitionVersion.objects.create(
        tenant_id=own.tenant_id,
        definition=own,
        version=1,
        document={"key": own.key, "label": own.label},
        content_hash="a" * 64,
        actor_id=own.updated_by,
        correlation_id=uuid.uuid4(),
    )
    CustomFieldDefinitionVersion.objects.create(
        tenant_id=foreign.tenant_id,
        definition=foreign,
        version=1,
        document={"key": foreign.key, "label": foreign.label},
        content_hash="b" * 64,
        actor_id=foreign.updated_by,
        correlation_id=uuid.uuid4(),
    )

    visible = CustomFieldDefinitionVersion.objects.for_tenant(own.tenant_id)
    assert list(visible.values_list("id", flat=True)) == [own_version.id]
    cross_tenant = CustomFieldDefinitionVersion(
        tenant_id=own.tenant_id,
        definition=foreign,
        version=2,
        document={"key": foreign.key},
        content_hash="c" * 64,
        actor_id=own.updated_by,
        correlation_id=uuid.uuid4(),
    )
    with pytest.raises(ValidationError):
        cross_tenant.full_clean()


def test_idempotency_keys_are_unique_per_tenant_not_globally() -> None:
    shared_key = "field-definition:create:request-1"
    first_tenant = uuid.uuid4()
    second_tenant = uuid.uuid4()

    def create(tenant_id: uuid.UUID) -> IdempotentCommand:
        return IdempotentCommand.objects.create(
            tenant_id=tenant_id,
            idempotency_key=shared_key,
            command_type="field_definition.create",
            request_fingerprint="d" * 64,
            response_payload={"id": str(uuid.uuid4())},
            response_status=201,
            resource_type="field_definition",
            resource_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            correlation_id=uuid.uuid4(),
        )

    create(first_tenant)
    create(second_tenant)
    with pytest.raises((IntegrityError, ValidationError)), transaction.atomic():
        create(first_tenant)


def test_append_only_guards_block_instance_and_queryset_tampering() -> None:
    configuration = _configuration()
    row = RuntimeConfigurationVersion.objects.create(
        tenant_id=configuration.tenant_id,
        configuration=configuration,
        version=1,
        document=configuration.document,
        environment=configuration.environment,
        actor_id=configuration.updated_by,
        correlation_id=uuid.uuid4(),
    )

    row.document = {"tampered": True}
    with pytest.raises(ValidationError):
        row.save()
    with pytest.raises(ValidationError):
        row.delete()
    with pytest.raises(ValidationError):
        RuntimeConfigurationVersion.objects.filter(pk=row.pk).update(document={"tampered": True})
    with pytest.raises(ValidationError):
        RuntimeConfigurationVersion.objects.filter(pk=row.pk).delete()


def test_lifecycle_and_publication_evidence_are_tenant_isolated() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    aggregate_id = uuid.uuid4()
    correlation_id = uuid.uuid4()
    transition = LifecycleTransitionRecord.objects.create(
        tenant_id=tenant_a,
        aggregate_type="field_definition",
        aggregate_id=aggregate_id,
        version=1,
        transition_key="activate-1",
        command="activate",
        from_state="draft",
        to_state="active",
        metadata={},
        actor_id=uuid.uuid4(),
        correlation_id=correlation_id,
        occurred_at=timezone.now(),
    )
    publication = PublicationRecord.objects.create(
        tenant_id=tenant_b,
        aggregate_type="form",
        aggregate_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        version=1,
        event_type="published",
        publication_key="publish-1",
        actor_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
        occurred_at=timezone.now(),
    )

    assert list(LifecycleTransitionRecord.objects.for_tenant(tenant_a).values_list("id", flat=True)) == [transition.id]
    assert not PublicationRecord.objects.for_tenant(tenant_a).filter(id=publication.id).exists()


def test_configuration_migration_is_reversible_and_covers_all_new_tables() -> None:
    migration = importlib.import_module("src.modules.customization_framework.migrations.0004_configuration_evidence")
    run_python_operations = [
        operation for operation in migration.Migration.operations if operation.__class__.__name__ == "RunPython"
    ]
    assert any(
        operation.code is migration.convert_legacy_tenant_to_uuid
        and operation.reverse_code is migration.restore_legacy_tenant_text
        for operation in run_python_operations
    )
    assert any(
        operation.code is migration.install_evidence_guards
        and operation.reverse_code is migration.remove_evidence_guards
        for operation in run_python_operations
    )
    assert any(
        operation.code is migration.register_configuration_resource_contract
        and operation.reverse_code is migration.unregister_configuration_resource_contract
        for operation in run_python_operations
    )
    contract = migration.CONFIGURATION_RESOURCE_CONTRACT
    assert (
        contract["module"],
        contract["resource"],
        contract["version"],
    ) == ("customization-framework", "configuration", "1.0")
    assert contract["available"] is True
    assert contract["discovery"] == {"source": "module_registry"}
    created_tables = {
        operation.options["db_table"]
        for operation in migration.Migration.operations
        if operation.__class__.__name__ == "CreateModel"
    }
    assert created_tables == set(migration.NEW_TENANT_TABLES)


def test_contract_registration_reverse_restores_only_owned_metadata() -> None:
    migration = importlib.import_module("src.modules.customization_framework.migrations.0004_configuration_evidence")
    entry = ModuleRegistryEntry.objects.get(name="customization-framework", version="2.0.0")
    previous_contract = {
        "module": "crm",
        "resource": "customer",
        "version": "1.0",
    }
    original_metadata = {
        "unrelated": {"preserve": True},
        "customization_resource_contracts": [previous_contract],
    }
    ModuleRegistryEntry.objects.filter(pk=entry.pk).update(metadata=original_metadata)

    migration.register_configuration_resource_contract(django_apps, None)
    entry.refresh_from_db()
    assert entry.metadata["unrelated"] == {"preserve": True}
    contracts = entry.metadata["customization_resource_contracts"]
    assert previous_contract in contracts
    assert migration.CONFIGURATION_RESOURCE_CONTRACT in contracts
    assert migration.CONTRACT_SEED_MARKER in entry.metadata

    migration.unregister_configuration_resource_contract(django_apps, None)
    entry.refresh_from_db()
    assert entry.metadata == original_metadata
