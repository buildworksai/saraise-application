"""Versioned outbox event content, redaction, and atomic evidence."""

import uuid

import pytest

from src.core.async_jobs.models import OutboxEvent
from src.modules.metadata_modeling.services import DynamicResourceService, EntityDefinitionService

from .helpers import ACTOR_ID, published_entity

pytest_plugins = ["src.core.testing.factories"]


@pytest.mark.django_db
def test_schema_created_event_is_versioned_correlated_and_redacted():
    tenant_id = uuid.uuid4()
    entity = EntityDefinitionService.create_definition(
        tenant_id,
        ACTOR_ID,
        {"name": "Secret Asset", "code": "asset", "description": "classified"},
        idempotency_key="create-asset",
        correlation_id="corr-create",
    )
    event = OutboxEvent.objects.for_tenant(tenant_id).get(aggregate_id=entity.id)
    assert event.event_type == "metadata_modeling.schema.created.v1"
    assert event.payload["correlation_id"] == "corr-create"
    assert event.payload["tenant_id"] == str(tenant_id)
    serialized = str(event.payload)
    assert "classified" not in serialized
    assert "Secret Asset" not in serialized


@pytest.mark.django_db
def test_resource_event_and_history_share_correlation_without_full_record_payload():
    tenant_id = uuid.uuid4()
    entity, _ = published_entity(tenant_id)
    resource = DynamicResourceService.create_resource(
        tenant_id,
        ACTOR_ID,
        entity.id,
        {"title": "Sensitive customer value"},
        idempotency_key="create-sensitive",
        correlation_id="corr-sensitive",
    )
    event = OutboxEvent.objects.for_tenant(tenant_id).get(
        event_type="metadata_modeling.resource.created.v1", aggregate_id=resource.id
    )
    history = resource.versions.get()
    assert event.payload["changed_fields"] == ["title"]
    assert event.payload["correlation_id"] == history.correlation_id == "corr-sensitive"
    assert "Sensitive customer value" not in str(event.payload)
