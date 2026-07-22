"""Persistence invariants for the metadata kernel."""

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from src.modules.metadata_modeling.models import (
    DynamicResource,
    DynamicResourceVersion,
    EntityDefinition,
    FieldDefinition,
    ImmutableEvidenceError,
    MetadataConfigurationAudit,
    MetadataModelingConfiguration,
    NamingSequence,
)

from .helpers import ACTOR_ID, published_entity, resource_for

pytest_plugins = ["src.core.testing.factories"]


@pytest.mark.django_db
def test_tenant_columns_are_indexed_uuid_fields_and_defaults_are_safe():
    tenant_id = uuid.uuid4()
    entity = EntityDefinition.objects.create(tenant_id=tenant_id, name="Asset", plural_name="Assets", code="asset")
    for model in (
        EntityDefinition,
        FieldDefinition,
        DynamicResource,
        DynamicResourceVersion,
        NamingSequence,
        MetadataModelingConfiguration,
        MetadataConfigurationAudit,
    ):
        field = model._meta.get_field("tenant_id")
        assert field.get_internal_type() == "UUIDField"
        assert field.db_index is True
    assert entity.plural_name == "Assets"
    assert entity.status == "draft"
    assert entity.lock_version == 1
    assert str(entity) == "Asset (asset)"


@pytest.mark.django_db
def test_entity_code_is_unique_only_within_tenant():
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    EntityDefinition.objects.create(tenant_id=tenant_a, name="Asset", plural_name="Assets", code="asset")
    EntityDefinition.objects.create(tenant_id=tenant_b, name="Asset", plural_name="Assets", code="asset")
    with pytest.raises(IntegrityError), transaction.atomic():
        EntityDefinition.objects.create(tenant_id=tenant_a, name="Duplicate", plural_name="Duplicates", code="asset")


@pytest.mark.django_db
def test_versioned_schema_fields_and_resource_history_are_immutable():
    tenant_id = uuid.uuid4()
    entity, version = published_entity(tenant_id)
    field = version.fields.get()
    field.name = "Rewritten"
    with pytest.raises(ImmutableEvidenceError):
        field.save()
    version.change_summary = "Rewritten"
    with pytest.raises(ImmutableEvidenceError):
        version.save()

    resource = resource_for(tenant_id, entity)
    history = resource.versions.get()
    history.display_name = "Rewritten"
    with pytest.raises(ImmutableEvidenceError):
        history.save()
    with pytest.raises(ImmutableEvidenceError):
        history.delete()


@pytest.mark.django_db
def test_configuration_allow_lists_and_audit_evidence_fail_closed():
    tenant_id = uuid.uuid4()
    config = MetadataModelingConfiguration(
        tenant_id=tenant_id,
        allowed_field_types=["text", "shell_script"],
    )
    with pytest.raises(ValidationError):
        config.full_clean()
    config.allowed_field_types = ["text"]
    config.rollout = {"percentage": 101}
    with pytest.raises(ValidationError):
        config.full_clean()

    config.rollout = {"percentage": 25}
    config.save()
    audit = MetadataConfigurationAudit.objects.create(
        tenant_id=tenant_id,
        configuration=config,
        version=1,
        operation="create",
        before={},
        after={"max_fields_per_schema": 250},
        changed_by=ACTOR_ID,
        correlation_id="corr-config",
    )
    audit.correlation_id = "tampered"
    with pytest.raises(ImmutableEvidenceError):
        audit.save()
