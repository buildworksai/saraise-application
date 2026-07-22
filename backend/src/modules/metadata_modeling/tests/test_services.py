"""Transactional service behavior and unhappy paths."""

import uuid

import pytest
from rest_framework.exceptions import ValidationError

from src.modules.metadata_modeling.models import MetadataConfigurationAudit
from src.modules.metadata_modeling.services import (
    ConflictError,
    DynamicResourceService,
    MetadataConfigurationService,
    SchemaVersionService,
)

from .helpers import ACTOR_ID, published_entity, resource_for, text_field

pytest_plugins = ["src.core.testing.factories"]


@pytest.mark.django_db
def test_schema_publication_creates_ordered_immutable_history_and_diff():
    tenant_id = uuid.uuid4()
    entity, first = published_entity(tenant_id)
    second = SchemaVersionService.create_candidate(
        tenant_id,
        ACTOR_ID,
        entity.id,
        [text_field(), text_field(required=False, key="notes", order=1)],
        based_on_version_id=first.id,
        change_summary="Add notes",
        correlation_id="corr-2",
    )
    diff = SchemaVersionService.diff_versions(tenant_id, entity.id, first.id, second.id)
    assert diff["added"] == ["notes"]
    assert diff["compatibility"] == "compatible"
    published = SchemaVersionService.publish_candidate(
        tenant_id,
        ACTOR_ID,
        entity.id,
        second.id,
        idempotency_key="publish-second",
        correlation_id="corr-2",
    )
    first.refresh_from_db()
    assert first.status == "superseded"
    assert published.status == "published"
    assert list(published.fields.values_list("key", flat=True)) == ["title", "notes"]


@pytest.mark.django_db
def test_record_validation_rejects_unknown_date_number_and_stale_write():
    tenant_id = uuid.uuid4()
    fields = [
        text_field(),
        {
            "name": "Due",
            "key": "due",
            "field_type": "date",
            "is_required": True,
            "validation_rules": {},
            "order": 1,
        },
        {
            "name": "Score",
            "key": "score",
            "field_type": "number",
            "validation_rules": {"minimum": 0},
            "order": 2,
        },
    ]
    entity, _ = published_entity(tenant_id, fields=fields)
    with pytest.raises(ValidationError) as exc:
        DynamicResourceService.create_resource(
            tenant_id,
            ACTOR_ID,
            entity.id,
            {"title": "OK", "due": "2026-02-30", "score": True, "unknown": 1},
            idempotency_key="invalid-record",
            correlation_id="corr-invalid",
        )
    assert {"due", "score", "unknown"} <= set(exc.value.detail)

    resource = DynamicResourceService.create_resource(
        tenant_id,
        ACTOR_ID,
        entity.id,
        {"title": "OK", "due": "2026-02-28", "score": 0},
        idempotency_key="valid-record",
        correlation_id="corr-valid",
    )
    with pytest.raises(ConflictError):
        DynamicResourceService.patch_resource(
            tenant_id,
            ACTOR_ID,
            resource.id,
            {"title": "Changed"},
            expected_lock_version=99,
            correlation_id="corr-stale",
        )
    resource.refresh_from_db()
    assert resource.data["title"] == "OK"
    assert resource.versions.count() == 1


@pytest.mark.django_db
def test_record_submit_cancel_and_soft_delete_restrictions():
    tenant_id = uuid.uuid4()
    entity, _ = published_entity(tenant_id, is_submittable=True)
    resource = resource_for(tenant_id, entity)
    submitted = DynamicResourceService.submit_resource(
        tenant_id,
        ACTOR_ID,
        resource.id,
        expected_lock_version=1,
        idempotency_key="submit-one",
        correlation_id="corr-submit",
    )
    assert submitted.state == "submitted"
    with pytest.raises(ValidationError):
        DynamicResourceService.soft_delete_resource(
            tenant_id,
            ACTOR_ID,
            resource.id,
            expected_lock_version=2,
            correlation_id="corr-delete",
        )
    cancelled = DynamicResourceService.cancel_resource(
        tenant_id,
        ACTOR_ID,
        resource.id,
        "Superseded request",
        expected_lock_version=2,
        idempotency_key="cancel-one",
        correlation_id="corr-cancel",
    )
    assert cancelled.state == "cancelled"
    assert list(cancelled.versions.values_list("operation", flat=True)) == ["cancel", "submit", "create"]


@pytest.mark.django_db
def test_configuration_preview_update_history_rollback_and_invalid_bounds():
    tenant_id = uuid.uuid4()
    rollout = {
        "schema_publication": {
            "enabled": True,
            "tenant_percentage": 25,
            "roles": ["metadata_admin"],
            "cohorts": [],
        }
    }
    preview = MetadataConfigurationService.preview_configuration(
        tenant_id, "production", {"max_fields_per_schema": 40, "rollout": rollout}
    )
    assert preview["valid"] is True
    # A first-use preview compares a complete defaulted document with no prior
    # document, so every effective setting is a change.
    assert {"max_fields_per_schema", "rollout"} <= set(preview["changed_fields"])
    config = MetadataConfigurationService.update_configuration(
        tenant_id,
        ACTOR_ID,
        "production",
        {"max_fields_per_schema": 40},
        expected_version=None,
        correlation_id="corr-config-1",
    )
    MetadataConfigurationService.update_configuration(
        tenant_id,
        ACTOR_ID,
        "production",
        {"max_fields_per_schema": 80},
        expected_version=config.version,
        correlation_id="corr-config-2",
    )
    rolled_back = MetadataConfigurationService.rollback_configuration(
        tenant_id,
        ACTOR_ID,
        "production",
        1,
        correlation_id="corr-config-3",
    )
    assert rolled_back.max_fields_per_schema == 40
    assert rolled_back.version == 3
    assert MetadataConfigurationAudit.objects.for_tenant(tenant_id).count() == 3
    assert MetadataConfigurationAudit.objects.for_tenant(tenant_id).first().operation == "rollback"
    with pytest.raises(ValidationError):
        MetadataConfigurationService.preview_configuration(tenant_id, "production", {"max_fields_per_schema": 0})
