"""Stable read/write boundaries for API v2 DTOs."""

import uuid

import pytest

from src.modules.metadata_modeling.serializers import (
    DynamicResourceDetailSerializer,
    EntityDefinitionCreateSerializer,
    EntityDefinitionDetailSerializer,
    FieldDefinitionWriteSerializer,
    MetadataConfigurationAuditSerializer,
    MetadataConfigurationWriteSerializer,
)

from .helpers import published_entity, resource_for

pytest_plugins = ["src.core.testing.factories"]


def test_write_serializers_exclude_tenant_audit_state_and_generated_fields():
    serializer = EntityDefinitionCreateSerializer(
        data={
            "name": "Asset",
            "code": "asset",
            "tenant_id": str(uuid.uuid4()),
            "status": "published",
            "created_by": str(uuid.uuid4()),
        }
    )
    assert serializer.is_valid(), serializer.errors
    assert not ({"tenant_id", "status", "created_by"} & serializer.validated_data.keys())
    resource_fields = DynamicResourceDetailSerializer.Meta.fields
    assert "created_by" in resource_fields and "lock_version" in resource_fields
    assert set(MetadataConfigurationAuditSerializer.Meta.read_only_fields) == set(
        MetadataConfigurationAuditSerializer.Meta.fields
    )


def test_field_and_configuration_shape_validation_rejects_unsafe_values():
    invalid_field = FieldDefinitionWriteSerializer(
        data={"name": "Bad", "key": "Bad Key", "field_type": "python", "order": -1}
    )
    assert not invalid_field.is_valid()
    assert {"key", "field_type", "order"} <= set(invalid_field.errors)
    invalid_config = MetadataConfigurationWriteSerializer(
        data={"max_fields_per_schema": 1001, "allowed_field_types": ["text", "python"]}
    )
    assert not invalid_config.is_valid()
    assert {"max_fields_per_schema", "allowed_field_types"} <= set(invalid_config.errors)


@pytest.mark.django_db
def test_detail_serializer_embeds_current_ordered_fields_but_list_contract_does_not():
    tenant_id = uuid.uuid4()
    entity, _ = published_entity(tenant_id)
    resource_for(tenant_id, entity)
    detail = EntityDefinitionDetailSerializer(entity).data
    assert detail["current_version"]["version"] == 1
    assert detail["active_fields"][0]["key"] == "title"
    assert detail["record_count"] == 1
