"""Transactional service behavior and unhappy paths."""

import uuid

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from src.modules.metadata_modeling.models import MetadataConfigurationAudit, NamingSequence
from src.modules.metadata_modeling.services import (
    ConflictError,
    DynamicResourceService,
    EntityDefinitionService,
    MetadataConfigurationService,
    NamingService,
    SchemaVersionService,
    ServiceUnavailableError,
    _json_schema_matches,
    _normalize_field,
    _normalize_fields,
    _schema_hash,
    _validate_naming,
    _validate_value,
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
def test_descriptor_validation_applies_defaults_json_rules_and_reference_existence():
    tenant_id = uuid.uuid4()
    target_entity, _ = published_entity(tenant_id, code="asset")
    target = resource_for(tenant_id, target_entity, title="Laptop")
    descriptors = [
        {
            "name": "Metadata",
            "key": "metadata",
            "field_type": "json",
            "is_required": True,
            "default_value": {"kind": "ticket", "tags": ["urgent"]},
            "validation_rules": {
                "type": "object",
                "required": ["kind", "tags"],
                "properties": {
                    "kind": {"type": "string", "enum": ["ticket"]},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        {
            "name": "Asset",
            "key": "asset",
            "field_type": "reference",
            "is_required": True,
            "reference_entity_code": "asset",
            "validation_rules": {},
        },
        {
            "name": "Approved",
            "key": "approved",
            "field_type": "boolean",
            "is_required": False,
            "validation_rules": {},
        },
    ]

    cleaned, errors = DynamicResourceService.validate_descriptors(
        tenant_id,
        descriptors,
        {"asset": str(target.id), "approved": False},
    )
    assert errors == {}
    assert cleaned == {
        "metadata": {"kind": "ticket", "tags": ["urgent"]},
        "asset": str(target.id),
        "approved": False,
    }

    invalid, errors = DynamicResourceService.validate_descriptors(
        tenant_id,
        descriptors,
        {"metadata": {"kind": "ticket", "tags": [1]}, "asset": str(uuid.uuid4()), "approved": "yes"},
    )
    assert invalid == {}
    assert errors["metadata"][0]["code"] == "INVALID_JSON_SCHEMA"
    assert errors["asset"][0]["code"] == "REFERENCE_NOT_FOUND"
    assert errors["approved"][0]["code"] == "TYPE_BOOLEAN"


@pytest.mark.django_db
def test_resource_listing_handles_invalid_entity_filter_and_date_window():
    tenant_id = uuid.uuid4()
    entity, _ = published_entity(tenant_id, fields=[text_field(), text_field(required=False, key="notes", order=1)])
    first = resource_for(tenant_id, entity, title="Incident one")
    second = resource_for(tenant_id, entity, title="Incident two")

    assert not DynamicResourceService.list_resources(tenant_id, entity_id="not-a-uuid").exists()
    assert list(
        DynamicResourceService.list_resources(
            tenant_id,
            entity_code="ticket",
            search="two",
            created_after=first.created_at,
            created_before=second.created_at,
            ordering="record_key",
        )
    ) == [second]


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
def test_definition_export_import_validate_only_create_and_checksum_failure():
    source_tenant = uuid.uuid4()
    target_tenant = uuid.uuid4()
    source_entity, _ = published_entity(source_tenant)
    document = EntityDefinitionService.export_definition(source_tenant, source_entity.id)

    validation = EntityDefinitionService.import_definition(
        target_tenant,
        ACTOR_ID,
        document,
        mode="validate_only",
        idempotency_key="validate-import",
        correlation_id="corr-import-validate",
    )
    assert validation["valid"] is True
    assert validation["checksum_valid"] is True

    candidate = EntityDefinitionService.import_definition(
        target_tenant,
        ACTOR_ID,
        document,
        mode="create",
        idempotency_key="create-import",
        correlation_id="corr-import-create",
    )
    assert candidate.status == "candidate"
    assert candidate.entity_definition.tenant_id == target_tenant
    assert candidate.fields.count() == 1

    with pytest.raises(ValidationError):
        EntityDefinitionService.import_definition(
            uuid.uuid4(),
            ACTOR_ID,
            {**document, "checksum": "0" * 64},
            mode="validate_only",
            idempotency_key="tampered-import",
            correlation_id="corr-import-tampered",
        )


@pytest.mark.django_db
def test_clone_definition_copies_published_schema_as_candidate_and_is_idempotent():
    tenant_id = uuid.uuid4()
    source, _ = published_entity(tenant_id, fields=[text_field(), text_field(required=False, key="notes", order=1)])

    clone = EntityDefinitionService.clone_definition(
        tenant_id,
        ACTOR_ID,
        source.id,
        "ticket_clone",
        "Ticket Clone",
        correlation_id="corr-clone",
    )
    repeated = EntityDefinitionService.clone_definition(
        tenant_id,
        ACTOR_ID,
        source.id,
        "ticket_clone",
        "Ticket Clone",
        correlation_id="corr-clone",
    )

    assert repeated.id == clone.id
    assert clone.status == "draft"
    candidate = clone.versions.get()
    assert candidate.status == "candidate"
    assert list(candidate.fields.values_list("key", flat=True).order_by("order")) == ["title", "notes"]


@pytest.mark.django_db
def test_sequence_naming_allocation_reset_duplicate_and_restore_versions():
    tenant_id = uuid.uuid4()
    entity, _ = published_entity(tenant_id)
    entity.naming_strategy = "sequence"
    entity.naming_config = {
        "sequence_key": "default",
        "prefix_template": "CASE-{YYYY}-{###}",
        "padding": 3,
        "reset_period": "yearly",
    }
    entity.save()

    assert NamingService.preview_record_key(tenant_id, entity, {"title": "Preview"}).endswith("001")
    first = DynamicResourceService.create_resource(
        tenant_id,
        ACTOR_ID,
        entity.id,
        {"title": "Incident one"},
        idempotency_key="sequence-one",
        correlation_id="corr-seq-one",
    )
    second = DynamicResourceService.create_resource(
        tenant_id,
        ACTOR_ID,
        entity.id,
        {"title": "Incident two"},
        idempotency_key="sequence-two",
        correlation_id="corr-seq-two",
    )
    assert first.record_key.endswith("001")
    assert second.record_key.endswith("002")

    sequence = NamingSequence.objects.for_tenant(tenant_id).get(entity_definition=entity)
    NamingService.reset_sequence(tenant_id, ACTOR_ID, sequence.id, 10, correlation_id="corr-reset")
    third = DynamicResourceService.duplicate_resource(
        tenant_id,
        ACTOR_ID,
        first.id,
        correlation_id="corr-duplicate",
    )
    assert third.record_key.endswith("010")
    assert third.display_name == f"Copy of {first.display_name}"

    deleted = DynamicResourceService.soft_delete_resource(
        tenant_id,
        ACTOR_ID,
        second.id,
        expected_lock_version=1,
        correlation_id="corr-delete",
    )
    restored = DynamicResourceService.restore_resource(tenant_id, ACTOR_ID, deleted.id, correlation_id="corr-restore")
    assert restored.deleted_at is None
    assert list(
        DynamicResourceService.list_resource_versions(tenant_id, restored.id).values_list("operation", flat=True)
    ) == [
        "restore",
        "delete",
        "create",
    ]


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


def test_naming_validation_rejects_unsafe_strategies_and_normalizes_sequence() -> None:
    with pytest.raises(ValidationError) as bad_strategy:
        _validate_naming("script", {})
    assert bad_strategy.value.detail["naming_strategy"][0]["code"] == "INVALID_CHOICE"

    with pytest.raises(ValidationError) as bad_object:
        _validate_naming("uuid", [])
    assert bad_object.value.detail["naming_config"][0]["code"] == "INVALID_OBJECT"

    with pytest.raises(ValidationError) as unknown:
        _validate_naming("field", {"field_key": "case_no", "extra": True})
    assert unknown.value.detail["naming_config"][0]["code"] == "UNKNOWN_KEYS"

    with pytest.raises(ValidationError) as missing_field:
        _validate_naming("field", {"field_key": " "})
    assert missing_field.value.detail["field_key"][0]["code"] == "REQUIRED"

    with pytest.raises(ValidationError) as bad_template:
        _validate_naming("sequence", {"prefix_template": "CASE-{abc}-{###}"})
    assert bad_template.value.detail["naming_config"][0]["code"] == "INVALID_TEMPLATE"

    with pytest.raises(ValidationError) as bad_padding:
        _validate_naming("sequence", {"prefix_template": "CASE-{###}", "padding": 13})
    assert bad_padding.value.detail["naming_config"][0]["code"] == "OUT_OF_RANGE"

    with pytest.raises(ValidationError) as bad_reset:
        _validate_naming("sequence", {"prefix_template": "CASE-{###}", "reset_period": "weekly"})
    assert bad_reset.value.detail["naming_config"][0]["code"] == "INVALID_CHOICE"

    normalized = _validate_naming("sequence", {"prefix_template": "CASE-{YYYY}-{###}"})
    assert normalized == {
        "sequence_key": "default",
        "prefix_template": "CASE-{YYYY}-{###}",
        "padding": 3,
        "reset_period": "never",
    }


@pytest.mark.parametrize(
    ("raw", "field", "code"),
    [
        ("not-object", "fields", "INVALID_OBJECT"),
        ({"name": "Bad", "key": "bad", "field_type": "text", "unexpected": True}, "fields", "UNKNOWN_KEYS"),
        ({"name": "Bad", "key": "bad", "field_type": "money"}, "field_type", "INVALID_CHOICE"),
        ({"name": "Bad", "key": "Bad-Key", "field_type": "text"}, "key", "INVALID_KEY"),
        (
            {"name": "Bad", "key": "bad", "field_type": "text", "validation_rules": []},
            "validation_rules",
            "INVALID_OBJECT",
        ),
        (
            {"name": "Bad", "key": "bad", "field_type": "text", "options": ["A"]},
            "options",
            "NOT_APPLICABLE",
        ),
        ({"name": "Bad", "key": "bad", "field_type": "select", "options": ["A", "A"]}, "options", "INVALID_OPTIONS"),
        ({"name": "Bad", "key": "bad", "field_type": "reference"}, "reference_entity_code", "REQUIRED"),
        (
            {"name": "Bad", "key": "bad", "field_type": "number", "reference_entity_code": "asset"},
            "reference_entity_code",
            "NOT_APPLICABLE",
        ),
        ({"name": "Bad", "key": "bad", "field_type": "text", "order": True}, "order", "INVALID_ORDER"),
    ],
)
def test_field_descriptor_normalization_rejects_invalid_shape(
    raw: object,
    field: str,
    code: str,
) -> None:
    with pytest.raises(ValidationError) as caught:
        _normalize_field(raw, 0)
    assert caught.value.detail[field][0]["code"] == code


def test_field_collection_normalization_rejects_missing_duplicates_and_sorts() -> None:
    with pytest.raises(ValidationError) as missing:
        _normalize_fields([])
    assert missing.value.detail["fields"][0]["code"] == "REQUIRED"

    duplicate_key = [
        {"name": "First", "key": "title", "field_type": "text", "order": 0},
        {"name": "Second", "key": "title", "field_type": "text", "order": 1},
    ]
    with pytest.raises(ValidationError) as key_error:
        _normalize_fields(duplicate_key)
    assert key_error.value.detail["fields"][0]["code"] == "DUPLICATE_KEY"

    duplicate_order = [
        {"name": "First", "key": "first", "field_type": "text", "order": 1},
        {"name": "Second", "key": "second", "field_type": "text", "order": 1},
    ]
    with pytest.raises(ValidationError) as order_error:
        _normalize_fields(duplicate_order)
    assert order_error.value.detail["fields"][0]["code"] == "DUPLICATE_ORDER"

    normalized = _normalize_fields(
        [
            {"name": "Second", "key": "second", "field_type": "text", "order": 2},
            {"name": "First", "key": "first", "field_type": "text", "order": 1},
        ]
    )
    assert [field["key"] for field in normalized] == ["first", "second"]


def test_json_schema_and_value_validation_cover_typed_boundaries() -> None:
    assert _json_schema_matches({"items": ["A"]}, {"type": "object", "required": ["items"]}) is True
    assert _json_schema_matches(True, {"type": "number"}) is False
    assert _json_schema_matches({"kind": "B"}, {"properties": {"kind": {"enum": ["A"]}}}) is False
    assert _json_schema_matches([1, 2], {"items": {"type": "integer"}}) is True

    text_descriptor = {"key": "title", "field_type": "text", "validation_rules": {"min_length": 2, "max_length": 4}}
    assert _validate_value(None, text_descriptor, "Test", tenant_id=None) == "Test"
    with pytest.raises(ValueError, match="MIN_LENGTH"):
        _validate_value(None, text_descriptor, "A", tenant_id=None)

    number_descriptor = {
        "key": "amount",
        "field_type": "number",
        "validation_rules": {"integer_only": True, "minimum": 1, "maximum": 10, "decimal_places": 0},
    }
    assert _validate_value(None, number_descriptor, 5, tenant_id=None) == 5
    with pytest.raises(ValueError, match="INTEGER_ONLY"):
        _validate_value(None, number_descriptor, 1.5, tenant_id=None)
    with pytest.raises(ValueError, match="TYPE_NUMBER"):
        _validate_value(None, number_descriptor, True, tenant_id=None)

    date_descriptor = {"key": "due", "field_type": "date", "validation_rules": {"minimum": "2026-01-01"}}
    assert _validate_value(None, date_descriptor, "2026-01-02", tenant_id=None) == "2026-01-02"
    with pytest.raises(ValueError, match="MINIMUM"):
        _validate_value(None, date_descriptor, "2025-12-31", tenant_id=None)

    select_descriptor = {
        "key": "status",
        "field_type": "select",
        "options": ["open"],
        "validation_rules": {"allow_blank": True},
    }
    assert _validate_value(None, select_descriptor, "", tenant_id=None) == ""
    with pytest.raises(ValueError, match="INVALID_OPTION"):
        _validate_value(None, select_descriptor, "closed", tenant_id=None)

    reference_descriptor = {"key": "asset", "field_type": "reference", "reference_entity_code": "asset"}
    assert _validate_value(None, reference_descriptor, str(uuid.uuid4()), tenant_id=None)
    with pytest.raises(ValueError, match="TYPE_REFERENCE"):
        _validate_value(None, reference_descriptor, 1, tenant_id=None)


@pytest.mark.django_db
def test_value_validation_covers_regex_date_json_and_persisted_reference_edges() -> None:
    tenant_id = uuid.uuid4()
    asset_entity, _ = published_entity(tenant_id, code="asset")
    asset = resource_for(tenant_id, asset_entity, title="Asset one")

    regex_descriptor = {"key": "asset_tag", "field_type": "text", "validation_rules": {"regex": r"[A-Z]{3}-\d{3}"}}
    assert _validate_value(None, regex_descriptor, "AST-001", tenant_id=None) == "AST-001"
    with pytest.raises(ValueError, match="REGEX_MISMATCH"):
        _validate_value(None, regex_descriptor, "ast-001", tenant_id=None)
    with pytest.raises(ValueError, match="INVALID_REGEX"):
        _validate_value(
            None, {"key": "bad", "field_type": "text", "validation_rules": {"regex": "["}}, "x", tenant_id=None
        )
    with pytest.raises(ValueError, match="REGEX_LIMIT"):
        _validate_value(
            None,
            {"key": "bad", "field_type": "text", "validation_rules": {"regex": "x" * 257}},
            "x",
            tenant_id=None,
        )

    date_descriptor = {"key": "due", "field_type": "date", "validation_rules": {"maximum": "2026-12-31"}}
    with pytest.raises(ValueError, match="TYPE_DATE"):
        _validate_value(None, date_descriptor, 20260803, tenant_id=None)
    with pytest.raises(ValueError, match="INVALID_DATE"):
        _validate_value(None, date_descriptor, "2026-02-30", tenant_id=None)
    with pytest.raises(ValueError, match="MAXIMUM"):
        _validate_value(None, date_descriptor, "2027-01-01", tenant_id=None)

    json_descriptor = {
        "key": "payload",
        "field_type": "json",
        "validation_rules": {"type": "object", "required": ["kind"], "properties": {"kind": {"enum": ["asset"]}}},
    }
    assert _validate_value(None, json_descriptor, {"kind": "asset"}, tenant_id=None) == {"kind": "asset"}
    with pytest.raises(ValueError, match="INVALID_JSON_SCHEMA"):
        _validate_value(None, json_descriptor, {"kind": "case"}, tenant_id=None)

    reference_descriptor = {"key": "asset", "field_type": "reference", "reference_entity_code": "asset"}
    assert _validate_value(None, reference_descriptor, str(asset.id), tenant_id=tenant_id) == str(asset.id)
    with pytest.raises(ValueError, match="REFERENCE_NOT_FOUND"):
        _validate_value(None, reference_descriptor, str(uuid.uuid4()), tenant_id=tenant_id)


@pytest.mark.django_db
def test_schema_lifecycle_edges_cover_preview_import_reject_and_restore_paths() -> None:
    tenant_id = uuid.uuid4()
    entity, first = published_entity(tenant_id)

    preview = EntityDefinitionService.preview_definition(
        tenant_id,
        entity.id,
        {"fields": [text_field(), text_field(key="notes", required=False, order=1)]},
        sample_data={"title": "A"},
    )
    assert preview["sample_validation"]["valid"] is False
    assert preview["sample_validation"]["errors"][0]["field"] == "title"

    with pytest.raises(ValidationError) as bad_restore:
        EntityDefinitionService.restore_definition(
            tenant_id,
            ACTOR_ID,
            entity.id,
            idempotency_key="restore-published",
            correlation_id="corr-restore-published",
        )
    assert bad_restore.value.detail["status"][0]["code"] == "INVALID_TRANSITION"

    archived = EntityDefinitionService.archive_definition(
        tenant_id,
        ACTOR_ID,
        entity.id,
        idempotency_key="archive-schema",
        correlation_id="corr-archive-schema",
    )
    assert (
        EntityDefinitionService.archive_definition(
            tenant_id,
            ACTOR_ID,
            archived.id,
            idempotency_key="archive-schema-again",
            correlation_id="corr-archive-schema-again",
        ).id
        == archived.id
    )
    restored = EntityDefinitionService.restore_definition(
        tenant_id,
        ACTOR_ID,
        archived.id,
        idempotency_key="restore-schema",
        correlation_id="corr-restore-schema",
    )
    assert restored.status == "published"

    export = EntityDefinitionService.export_definition(tenant_id, entity.id)
    validate_only = EntityDefinitionService.import_definition(
        tenant_id,
        ACTOR_ID,
        export,
        mode="validate_only",
        idempotency_key="import-validate",
        correlation_id="corr-import-validate",
    )
    assert isinstance(validate_only, dict)
    assert validate_only["valid"] is True

    with pytest.raises(ValidationError) as bad_mode:
        EntityDefinitionService.import_definition(
            tenant_id,
            ACTOR_ID,
            export,
            mode="replace",
            idempotency_key="import-bad-mode",
            correlation_id="corr-import-bad-mode",
        )
    assert bad_mode.value.detail["mode"][0]["code"] == "INVALID_CHOICE"

    import_body = {key: value for key, value in export.items() if key != "checksum"}
    import_body["schema"]["fields"].append(text_field(key="notes", required=False, order=1))
    changed_export = {**import_body, "checksum": _schema_hash(import_body)}
    new_version = EntityDefinitionService.import_definition(
        tenant_id,
        ACTOR_ID,
        changed_export,
        mode="new_version",
        idempotency_key="import-new-version",
        correlation_id="corr-import-new-version",
    )
    rejected = SchemaVersionService.reject_candidate(
        tenant_id,
        ACTOR_ID,
        entity.id,
        new_version.id,
        "Does not match deployment plan",
        correlation_id="corr-reject",
    )
    assert rejected.status == "rejected"
    assert rejected.validation_report["rejection_reason"] == "Does not match deployment plan"

    with pytest.raises(ValidationError) as reject_again:
        SchemaVersionService.reject_candidate(
            tenant_id,
            ACTOR_ID,
            entity.id,
            first.id,
            "Published versions are immutable",
            correlation_id="corr-reject-published",
        )
    assert reject_again.value.detail["status"][0]["code"] == "INVALID_TRANSITION"


@pytest.mark.django_db
def test_definition_update_delete_publish_and_rollback_guard_branches() -> None:
    tenant_id = uuid.uuid4()
    draft = EntityDefinitionService.create_definition(
        tenant_id,
        ACTOR_ID,
        {"name": "Draft Case", "plural_name": "Draft Cases", "code": "draft_case"},
        idempotency_key="draft-create",
        correlation_id="corr-draft-create",
    )
    assert (
        EntityDefinitionService.create_definition(
            tenant_id,
            ACTOR_ID,
            {"name": "Ignored Replay", "plural_name": "Ignored", "code": "ignored"},
            idempotency_key="draft-create",
            correlation_id="corr-draft-replay",
        ).id
        == draft.id
    )

    with pytest.raises(ValidationError) as unknown_create:
        EntityDefinitionService.create_definition(
            tenant_id,
            ACTOR_ID,
            {"name": "Bad", "plural_name": "Bad", "code": "bad", "status": "published"},
            idempotency_key="bad-create",
            correlation_id="corr-bad-create",
        )
    assert unknown_create.value.detail["status"][0]["code"] == "READ_ONLY"

    changed = EntityDefinitionService.update_definition(
        tenant_id,
        ACTOR_ID,
        draft.id,
        {"name": "Renamed Case", "naming_strategy": "field", "naming_config": {"field_key": "title"}},
        expected_lock_version=draft.lock_version,
        correlation_id="corr-update",
    )
    assert changed.name == "Renamed Case"
    assert changed.naming_config == {"field_key": "title"}

    with pytest.raises(ConflictError):
        EntityDefinitionService.update_definition(
            tenant_id,
            ACTOR_ID,
            changed.id,
            {"name": "Stale"},
            expected_lock_version=changed.lock_version - 1,
            correlation_id="corr-stale",
        )
    with pytest.raises(ValidationError) as unknown_update:
        EntityDefinitionService.update_definition(
            tenant_id,
            ACTOR_ID,
            changed.id,
            {"owner_module": "other"},
            expected_lock_version=changed.lock_version,
            correlation_id="corr-unknown-update",
        )
    assert unknown_update.value.detail["owner_module"][0]["code"] == "READ_ONLY"

    candidate = SchemaVersionService.create_candidate(
        tenant_id,
        ACTOR_ID,
        changed.id,
        [text_field()],
        based_on_version_id=None,
        change_summary="Publish draft",
        correlation_id="corr-candidate",
    )
    published = SchemaVersionService.publish_candidate(
        tenant_id,
        ACTOR_ID,
        changed.id,
        candidate.id,
        idempotency_key="publish-draft",
        correlation_id="corr-publish",
    )
    assert (
        SchemaVersionService.publish_candidate(
            tenant_id,
            ACTOR_ID,
            changed.id,
            published.id,
            idempotency_key="publish-replay",
            correlation_id="corr-publish-replay",
        ).id
        == published.id
    )

    with pytest.raises(ValidationError) as immutable_code:
        EntityDefinitionService.update_definition(
            tenant_id,
            ACTOR_ID,
            changed.id,
            {"code": "new_code"},
            expected_lock_version=changed.lock_version + 1,
            correlation_id="corr-immutable",
        )
    assert immutable_code.value.detail["code"][0]["code"] == "IMMUTABLE"

    used = resource_for(tenant_id, changed, title="Used")
    with pytest.raises(ValidationError) as delete_forbidden:
        EntityDefinitionService.delete_draft_definition(
            tenant_id,
            ACTOR_ID,
            changed.id,
            correlation_id="corr-delete-published",
        )
    assert delete_forbidden.value.detail["status"][0]["code"] == "DELETE_FORBIDDEN"

    rollback = SchemaVersionService.rollback_to_version(
        tenant_id,
        ACTOR_ID,
        changed.id,
        published.id,
        idempotency_key="rollback-schema",
        correlation_id="corr-rollback",
    )
    assert rollback.status == "published"
    assert rollback.id == published.id
    assert used.entity_definition_id == changed.id


@pytest.mark.django_db
def test_schema_validation_reports_incompatible_resources_and_bounds() -> None:
    tenant_id = uuid.uuid4()
    entity, first = published_entity(tenant_id)
    resource_for(tenant_id, entity, title="Ok")
    candidate = SchemaVersionService.create_candidate(
        tenant_id,
        ACTOR_ID,
        entity.id,
        [
            {
                "name": "Title",
                "key": "title",
                "field_type": "text",
                "is_required": True,
                "validation_rules": {"min_length": 5},
            }
        ],
        based_on_version_id=first.id,
        change_summary="Tighten title",
        correlation_id="corr-tighten",
    )

    with pytest.raises(ValidationError) as sample_limit:
        SchemaVersionService.validate_candidate(tenant_id, entity.id, candidate.id, sample_limit=0)
    assert sample_limit.value.detail["sample_limit"][0]["code"] == "OUT_OF_RANGE"

    report = SchemaVersionService.validate_candidate(tenant_id, entity.id, candidate.id, sample_limit=10)
    assert report["valid"] is False
    assert report["incompatible_resources"] == 1
    assert report["errors"][0]["fields"]["title"][0]["code"] == "MIN_LENGTH"

    with pytest.raises(ValidationError) as incompatible:
        SchemaVersionService.publish_candidate(
            tenant_id,
            ACTOR_ID,
            entity.id,
            candidate.id,
            idempotency_key="publish-incompatible",
            correlation_id="corr-publish-incompatible",
        )
    assert incompatible.value.detail["schema"][0]["code"] == "INCOMPATIBLE_RESOURCES"


@pytest.mark.django_db
def test_resource_legacy_paths_field_naming_and_sequence_guards() -> None:
    tenant_id = uuid.uuid4()
    draft = EntityDefinitionService.create_definition(
        tenant_id,
        ACTOR_ID,
        {
            "name": "Legacy Case",
            "plural_name": "Legacy Cases",
            "code": "legacy_case",
            "naming_strategy": "field",
            "naming_config": {"field_key": "title"},
        },
        idempotency_key="legacy-definition",
        correlation_id="corr-legacy-definition",
    )
    with pytest.raises(ValidationError) as no_schema:
        DynamicResourceService.create_legacy_resource(
            tenant_id,
            ACTOR_ID,
            draft.id,
            {"title": "Missing schema"},
            correlation_id="corr-legacy-noschema",
        )
    assert no_schema.value.detail["schema"][0]["code"] == "SCHEMA_REQUIRED"

    candidate = SchemaVersionService.create_candidate(
        tenant_id,
        ACTOR_ID,
        draft.id,
        [text_field()],
        based_on_version_id=None,
        change_summary="Legacy migration",
        correlation_id="corr-legacy-candidate",
    )
    legacy = DynamicResourceService.create_legacy_resource(
        tenant_id,
        ACTOR_ID,
        draft.id,
        {"title": "Legacy one"},
        correlation_id="corr-legacy-create",
    )
    assert legacy.schema_version_id == candidate.id
    assert legacy.data == {"title": "Legacy one"}

    with pytest.raises(ValidationError) as missing_name:
        NamingService.preview_record_key(tenant_id, draft, {})
    assert missing_name.value.detail["title"][0]["code"] == "REQUIRED_FOR_NAMING"
    with pytest.raises(NotFound):
        NamingService.preview_record_key(uuid.uuid4(), draft, {"title": "Foreign"})

    draft.naming_strategy = "sequence"
    draft.naming_config = {
        "sequence_key": "default",
        "prefix_template": "CASE-{MM}-{##}",
        "padding": 2,
        "reset_period": "monthly",
    }
    draft.save(update_fields=("naming_strategy", "naming_config", "updated_at"))
    sequence = NamingSequence.objects.create(
        tenant_id=tenant_id,
        entity_definition=draft,
        sequence_key="default",
        period_key=timezone.now().strftime("%Y-%m"),
        prefix_template="CASE-{MM}-{##}",
        padding=2,
        reset_period="monthly",
        next_value=7,
        is_active=False,
    )
    assert NamingService.preview_record_key(tenant_id, draft, {"title": "Preview"}).endswith("01")
    with pytest.raises(ServiceUnavailableError):
        NamingService.allocate_record_key(tenant_id, draft, {"title": "Blocked"})
    with pytest.raises(ValidationError) as reset_bool:
        NamingService.reset_sequence(tenant_id, ACTOR_ID, sequence.id, True, correlation_id="corr-reset-bool")
    assert reset_bool.value.detail["next_value"][0]["code"] == "OUT_OF_RANGE"
