"""Domain-service evidence for validation, lifecycle, publication, and evaluation."""

from __future__ import annotations

import uuid
from copy import deepcopy

import pytest
from django.core.exceptions import ValidationError

from src.core.async_jobs.models import OutboxEvent
from src.modules.customization_framework.models import (
    CustomFieldDefinition,
    CustomFieldDefinitionVersion,
    RuleExecution,
)
from src.modules.customization_framework.services import (
    BusinessRuleService,
    CustomFieldService,
    CustomizationConfigurationService,
    CustomizationNotFound,
    CustomizationRegistry,
    CustomizationValidationError,
    EvaluationIdempotencyConflict,
    FormService,
    OptimisticLockConflict,
    _definition_schema,
    _evaluate_condition,
    _EvaluationBudget,
    _validate_actions,
    _validate_condition,
    default_configuration_document,
    validate_configuration_document,
)

pytestmark = pytest.mark.django_db


def field_payload(**overrides):
    return {
        "key": "customer-reference",
        "label": "Customer reference",
        "description": "Stable customer reference",
        "owner_module": "crm",
        "target_resource": "customer",
        "target_contract_version": "1.0",
        "data_type": "text",
        "required": True,
        "validation_schema": {"maxLength": 64},
        "presentation_schema": {"control": "text"},
        **overrides,
    }


def form_payload(**overrides):
    return {
        "key": "customer-intake",
        "name": "Customer intake",
        "description": "Accessible customer intake",
        "owner_module": "crm",
        "target_resource": "customer",
        "target_contract_version": "1.0",
        **overrides,
    }


def rule_payload(**overrides):
    return {
        "key": "require-status",
        "name": "Require status",
        "description": "Explains active status",
        "owner_module": "crm",
        "target_resource": "customer",
        "target_contract_version": "1.0",
        "trigger": "validate",
        "priority": 10,
        **overrides,
    }


def test_registry_rejects_incompatible_duplicates_and_marks_unavailable(tenant_a) -> None:
    contract = CustomizationRegistry.resolve_resource_contract(tenant_a.id, "crm", "customer", "1.0")
    assert contract.available is True
    with pytest.raises(CustomizationValidationError):
        CustomizationRegistry.register_resource_contract(
            "crm",
            "customer",
            "1.0",
            {},
            {"custom_field_types": ["text"], "rule_triggers": ["validate"]},
        )
    unavailable = CustomizationRegistry.unregister_resource_contract("crm", "customer", "1.0")
    assert unavailable is not None and unavailable.available is False
    with pytest.raises(Exception) as caught:
        CustomizationRegistry.resolve_resource_contract(tenant_a.id, "crm", "customer", "1.0")
    assert getattr(caught.value, "status_code", None) == 503


def test_configuration_document_validation_rejects_unsafe_policy_and_default_shapes() -> None:
    document = default_configuration_document()
    duplicated = deepcopy(document)
    duplicated["policies"]["field_types"] = ["text", "text", "integer"]
    assert validate_configuration_document(duplicated)["policies"]["field_types"] == ["text", "integer"]

    invalid_documents = [
        [],
        {k: v for k, v in document.items() if k != "rbac"},
        {**deepcopy(document), "limits": {**document["limits"], "json_bytes": True}},
        {**deepcopy(document), "policies": {**document["policies"], "slug_pattern": ".*"}},
        {**deepcopy(document), "policies": {**document["policies"], "field_types": ["python"]}},
        {**deepcopy(document), "policies": {**document["policies"], "field_transitions": {"wrong": {}}}},
        {**deepcopy(document), "defaults": {**document["defaults"], "field_required": "yes"}},
        {
            **deepcopy(document),
            "defaults": {**document["defaults"], "form_layout": {"schema_version": 2, "sections": []}},
        },
        {**deepcopy(document), "list_preferences": {**document["list_preferences"], "rule_ordering": "drop table"}},
        {
            **deepcopy(document),
            "navigation": {**document["navigation"], "forms_order": document["navigation"]["fields_order"]},
        },
        {**deepcopy(document), "rollout": {**document["rollout"], "roles": ["admin", ""]}},
        {**deepcopy(document), "rbac": {**document["rbac"], "sod_actions": {}}},
    ]
    for invalid in invalid_documents:
        with pytest.raises(CustomizationValidationError):
            validate_configuration_document(invalid)


def test_definition_schema_derives_format_defaults_and_rejects_type_drift(tenant_a, actor_id) -> None:
    date_field = CustomFieldDefinition(
        tenant_id=tenant_a.id,
        created_by=actor_id,
        updated_by=actor_id,
        key="invoice-date",
        label="Invoice date",
        owner_module="crm",
        target_resource="customer",
        target_contract_version="1.0",
        data_type="date",
        validation_schema={},
    )
    assert _definition_schema(date_field)["format"] == "date"

    multi_choice = CustomFieldDefinition(
        tenant_id=tenant_a.id,
        created_by=actor_id,
        updated_by=actor_id,
        key="tags",
        label="Tags",
        owner_module="crm",
        target_resource="customer",
        target_contract_version="1.0",
        data_type="multi_choice",
        validation_schema={},
    )
    schema = _definition_schema(multi_choice)
    assert schema["items"] == {"type": "string"}
    assert schema["uniqueItems"] is True

    conflicting = CustomFieldDefinition(
        tenant_id=tenant_a.id,
        created_by=actor_id,
        updated_by=actor_id,
        key="bad",
        label="Bad",
        owner_module="crm",
        target_resource="customer",
        target_contract_version="1.0",
        data_type="integer",
        validation_schema={"type": "string"},
    )
    with pytest.raises(CustomizationValidationError, match="type conflicts"):
        _definition_schema(conflicting)


def test_configuration_service_update_import_rollback_and_idempotency_are_audited(tenant_a, actor_id) -> None:
    service = CustomizationConfigurationService()
    correlation_id = uuid.uuid4()
    document = default_configuration_document()
    document["list_preferences"]["page_size"] = 50
    preview = service.preview(tenant_a.id, document=document)
    assert preview["valid"] is True
    assert preview["changes"]["list_preferences"]["after"]["page_size"] == 50

    updated = service.update(
        tenant_a.id,
        actor_id=actor_id,
        correlation_id=correlation_id,
        idempotency_key="configuration-update-1",
        expected_version=0,
        document=document,
    )
    replayed = service.update(
        tenant_a.id,
        actor_id=actor_id,
        correlation_id=correlation_id,
        idempotency_key="configuration-update-1",
        expected_version=0,
        document=document,
    )
    assert replayed.id == updated.id
    assert service.export_document(tenant_a.id)["version"] == 1
    assert service.list_versions(tenant_a.id).count() == 1
    assert service.list_audit(tenant_a.id).filter(action="update", version=1).exists()

    with pytest.raises(OptimisticLockConflict):
        service.update(
            tenant_a.id,
            actor_id=actor_id,
            correlation_id=uuid.uuid4(),
            idempotency_key="configuration-update-stale",
            expected_version=0,
            document=default_configuration_document(),
        )
    with pytest.raises(EvaluationIdempotencyConflict):
        service.update(
            tenant_a.id,
            actor_id=actor_id,
            correlation_id=correlation_id,
            idempotency_key="configuration-update-1",
            expected_version=1,
            document=default_configuration_document(),
        )
    with pytest.raises(CustomizationValidationError):
        service.import_document(
            tenant_a.id,
            actor_id=actor_id,
            correlation_id=uuid.uuid4(),
            idempotency_key="bad",
            expected_version=1,
            payload={},
        )
    with pytest.raises(CustomizationNotFound):
        service.rollback(
            tenant_a.id,
            actor_id=actor_id,
            correlation_id=uuid.uuid4(),
            idempotency_key="missing-rollback",
            expected_version=1,
            target_version=99,
        )

    exported = service.export_document(tenant_a.id)
    imported = service.import_document(
        tenant_a.id,
        actor_id=actor_id,
        correlation_id=uuid.uuid4(),
        idempotency_key="configuration-import-1",
        expected_version=1,
        payload=exported,
    )
    rolled_back = service.rollback(
        tenant_a.id,
        actor_id=actor_id,
        correlation_id=uuid.uuid4(),
        idempotency_key="configuration-rollback-1",
        expected_version=imported.version,
        target_version=1,
    )
    assert rolled_back.version == 3
    assert service.list_audit(tenant_a.id).filter(action="rollback:1", version=3).exists()


def test_field_definition_lifecycle_value_and_impact_are_real(tenant_a, actor_id) -> None:
    service = CustomFieldService()
    definition = service.create_definition(tenant_a.id, actor_id=actor_id, data=field_payload(default_value="CUST-1"))
    assert definition.status == "draft"
    assert (
        OutboxEvent.objects.for_tenant(tenant_a.id)
        .filter(
            aggregate_id=definition.id,
            event_type="customization_framework.field_definition.created",
        )
        .exists()
    )

    definition = service.transition_definition(
        tenant_a.id,
        definition_id=definition.id,
        command="activate",
        transition_key="activate-1",
        actor_id=actor_id,
    )
    assert definition.status == "active"
    assert definition.activated_at is not None
    assert service.validate_value(tenant_a.id, definition_id=definition.id, value="CUST-2")["valid"] is True

    record_id = uuid.uuid4()
    value = service.upsert_value(
        tenant_a.id,
        definition_id=definition.id,
        target_record_id=record_id,
        value="CUST-2",
        source="api",
        expected_lock_version=None,
        actor_id=actor_id,
    )
    assert value.definition_revision == definition.lock_version
    assert service.get_value(tenant_a.id, definition_id=definition.id, target_record_id=record_id).id == value.id
    assert service.get_definition_impact(tenant_a.id, definition_id=definition.id)["blocking"] is True
    with pytest.raises(CustomizationValidationError):
        service.delete_definition(
            tenant_a.id,
            definition_id=definition.id,
            expected_lock_version=definition.lock_version,
            actor_id=actor_id,
        )


def test_form_listing_and_lookup_fail_closed_for_unknown_filters_and_ids(tenant_a, actor_id) -> None:
    service = FormService()
    form = service.create_form(tenant_a.id, actor_id=actor_id, data=form_payload())

    assert list(service.list_forms(tenant_a.id, filters={"status": "draft"})) == [form]
    with pytest.raises(CustomizationValidationError, match="unsupported form filter"):
        list(service.list_forms(tenant_a.id, filters={"tenant_id": tenant_a.id}))
    with pytest.raises(CustomizationNotFound):
        service.get_form(tenant_a.id, form_id=uuid.uuid4())
    with pytest.raises(CustomizationValidationError, match="unsupported layout version filter"):
        list(service.list_layout_versions(tenant_a.id, filters={"owner_module": "crm"}))


def test_registry_extension_helpers_validate_schema_and_dependency_impact(tenant_a, actor_id) -> None:
    service = CustomFieldService()
    required = service.create_definition(
        tenant_a.id,
        actor_id=actor_id,
        data=field_payload(
            key="customer-status",
            label="Customer status",
            required=True,
            validation_schema={"enum": ["active", "inactive"]},
        ),
    )
    service.transition_definition(
        tenant_a.id,
        definition_id=required.id,
        command="activate",
        transition_key="activate-status",
        actor_id=actor_id,
    )

    schema = CustomizationRegistry.get_active_field_schema(tenant_a.id, "crm", "customer")
    missing = CustomizationRegistry.validate_record_extensions(tenant_a.id, "crm", "customer", uuid.uuid4(), {})
    unknown = CustomizationRegistry.validate_record_extensions(
        tenant_a.id,
        "crm",
        "customer",
        uuid.uuid4(),
        {"customer-status": "retired", "unknown-field": "x"},
    )
    valid = CustomizationRegistry.validate_record_extensions(
        tenant_a.id,
        "crm",
        "customer",
        uuid.uuid4(),
        {"customer-status": "active"},
    )

    assert schema["customer-status"]["enum"] == ["active", "inactive"]
    assert missing == {"valid": False, "diagnostics": [{"code": "required", "field": "customer-status"}]}
    assert {item["code"] for item in unknown["diagnostics"]} == {"unknown_field", "invalid_value"}
    assert valid == {"valid": True, "diagnostics": []}
    assert (
        CustomizationRegistry.get_dependency_impact(tenant_a.id, "crm", "customer", "customer-status")["blocking"]
        is False
    )
    with pytest.raises(CustomizationNotFound):
        CustomizationRegistry.get_dependency_impact(tenant_a.id, "crm", "customer", "missing-field")


def test_field_definition_rollback_restores_versioned_mutable_snapshot(tenant_a, actor_id) -> None:
    service = CustomFieldService()
    definition = service.create_definition(
        tenant_a.id,
        actor_id=actor_id,
        data=field_payload(label="Original label", validation_schema={"maxLength": 12}),
    )
    updated = service.update_definition(
        tenant_a.id,
        definition_id=definition.id,
        expected_lock_version=definition.lock_version,
        actor_id=actor_id,
        data={"label": "Updated label", "validation_schema": {"maxLength": 24}},
    )

    rolled_back = service.rollback_definition(
        tenant_a.id,
        definition_id=definition.id,
        target_version=1,
        expected_lock_version=updated.lock_version,
        actor_id=actor_id,
    )

    assert rolled_back.label == "Original label"
    assert rolled_back.validation_schema == {"maxLength": 12}
    assert rolled_back.lock_version == updated.lock_version + 1
    assert CustomFieldDefinitionVersion.objects.filter(tenant_id=tenant_a.id, definition=definition).count() == 3


def test_field_value_validation_rejects_type_source_and_duplicate_create(tenant_a, actor_id) -> None:
    service = CustomFieldService()
    definition = service.create_definition(
        tenant_a.id,
        actor_id=actor_id,
        data=field_payload(data_type="integer", validation_schema={"minimum": 1}),
    )
    definition = service.transition_definition(
        tenant_a.id,
        definition_id=definition.id,
        command="activate",
        transition_key="activate-integer",
        actor_id=actor_id,
    )
    with pytest.raises(CustomizationValidationError):
        service.validate_value(tenant_a.id, definition_id=definition.id, value="1")
    with pytest.raises(CustomizationValidationError):
        service.upsert_value(
            tenant_a.id,
            definition_id=definition.id,
            target_record_id=uuid.uuid4(),
            value=1,
            source="rule",
            expected_lock_version=None,
            actor_id=actor_id,
        )


def test_field_value_update_delete_and_filters_are_tenant_scoped_and_fail_closed(tenant_a, actor_id) -> None:
    service = CustomFieldService()
    definition = service.create_definition(tenant_a.id, actor_id=actor_id, data=field_payload())
    definition = service.transition_definition(
        tenant_a.id,
        definition_id=definition.id,
        command="activate",
        transition_key="activate-value-filters",
        actor_id=actor_id,
    )
    record_id = uuid.uuid4()
    created = service.upsert_value(
        tenant_a.id,
        definition_id=definition.id,
        target_record_id=record_id,
        value="CUST-10",
        source="api",
        expected_lock_version=None,
        actor_id=actor_id,
    )

    updated = service.upsert_value(
        tenant_a.id,
        definition_id=definition.id,
        target_record_id=record_id,
        value="CUST-11",
        source="import",
        expected_lock_version=created.lock_version,
        actor_id=actor_id,
    )

    assert updated.value == "CUST-11"
    assert updated.lock_version == created.lock_version + 1
    assert list(service.list_values(tenant_a.id, filters={"definition_id": definition.id})) == [updated]
    assert list(service.list_values(tenant_a.id, filters={"target_record_id": record_id, "source": "import"})) == [
        updated
    ]
    assert list(
        service.list_values(
            tenant_a.id,
            filters={"definition_id": definition.id, "updated_at_after": updated.updated_at.isoformat()},
            ordering="created_at",
        )
    ) == [updated]
    with pytest.raises(CustomizationValidationError, match="target_record_id or definition_id"):
        list(service.list_values(tenant_a.id))
    with pytest.raises(CustomizationValidationError, match="unsupported field value filter"):
        list(service.list_values(tenant_a.id, filters={"definition_id": definition.id, "tenant_id": tenant_a.id}))
    with pytest.raises(CustomizationValidationError, match="unsupported field value source"):
        list(service.list_values(tenant_a.id, filters={"definition_id": definition.id, "source": "worker"}))
    with pytest.raises(CustomizationValidationError, match="updated_at_before"):
        list(service.list_values(tenant_a.id, filters={"definition_id": definition.id, "updated_at_before": "bad"}))

    deleted = service.delete_value(
        tenant_a.id,
        value_id=updated.id,
        expected_lock_version=updated.lock_version,
        actor_id=actor_id,
    )

    assert deleted.deleted_at is not None
    with pytest.raises(CustomizationNotFound):
        service.get_value(tenant_a.id, definition_id=definition.id, target_record_id=record_id)


def test_optimistic_lock_and_cross_tenant_not_found(field_pair, actor_id) -> None:
    own, foreign = field_pair
    service = CustomFieldService()
    with pytest.raises(OptimisticLockConflict):
        service.update_definition(
            own.tenant_id,
            definition_id=own.id,
            expected_lock_version=own.lock_version + 1,
            actor_id=actor_id,
            data={"label": "Conflict"},
        )
    with pytest.raises(CustomizationNotFound):
        service.get_definition(own.tenant_id, definition_id=foreign.id)


def test_form_layout_publication_is_atomic_versioned_and_renderable(tenant_a, actor_id) -> None:
    service = FormService()
    form = service.create_form(tenant_a.id, actor_id=actor_id, data=form_payload())
    layout = {
        "schema_version": 1,
        "sections": [
            {
                "id": "main",
                "title": "Main details",
                "components": [],
            }
        ],
    }
    version = service.create_layout_version(
        tenant_a.id,
        form_id=form.id,
        actor_id=actor_id,
        layout=layout,
        change_summary="Initial accessible layout",
    )
    published = service.publish_layout(
        tenant_a.id,
        form_id=form.id,
        layout_version_id=version.id,
        transition_key="publish-layout-1",
        actor_id=actor_id,
    )
    form.refresh_from_db()
    assert published.status == "published"
    assert form.status == "published"
    assert form.published_version == published.version
    render = service.get_render_schema(tenant_a.id, form_id=form.id)
    assert render["content_hash"] == published.content_hash
    assert render["layout"] == layout


def test_form_render_schema_supports_contract_lookup_and_rejects_missing_locator(tenant_a, actor_id) -> None:
    service = FormService()
    form = service.create_form(tenant_a.id, actor_id=actor_id, data=form_payload(key="support-intake"))
    version = service.create_layout_version(
        tenant_a.id,
        form_id=form.id,
        actor_id=actor_id,
        layout={"schema_version": 1, "sections": [{"id": "main", "components": []}]},
        change_summary="Contract lookup layout",
    )
    service.publish_layout(
        tenant_a.id,
        form_id=form.id,
        layout_version_id=version.id,
        transition_key="publish-contract-lookup",
        actor_id=actor_id,
    )

    by_contract = CustomizationRegistry.get_published_form(tenant_a.id, "crm", "customer", "support-intake")

    assert by_contract["form_key"] == "support-intake"
    assert by_contract["version"] == 2
    with pytest.raises(CustomizationValidationError):
        service.get_render_schema(tenant_a.id)
    with pytest.raises(CustomizationNotFound):
        CustomizationRegistry.get_published_form(tenant_a.id, "crm", "customer", "missing-form")


def test_layout_rejects_duplicate_and_unresolved_field_references(tenant_a, actor_id) -> None:
    service = FormService()
    form = service.create_form(tenant_a.id, actor_id=actor_id, data=form_payload())
    invalid = {
        "schema_version": 1,
        "sections": [
            {
                "id": "main",
                "components": [
                    {"type": "field", "field_key": "missing-field"},
                    {"type": "field", "field_key": "missing-field"},
                ],
            }
        ],
    }
    report = service.validate_layout(tenant_a.id, form_id=form.id, layout=invalid)
    assert report["valid"] is False
    assert {item["code"] for item in report["diagnostics"]} == {
        "duplicate_field_reference",
        "unresolved_or_retired_field",
    }


def test_rule_version_rejects_dangerous_ast_and_evaluates_idempotently(tenant_a, actor_id) -> None:
    service = BusinessRuleService()
    rule = service.create_rule(tenant_a.id, actor_id=actor_id, data=rule_payload())
    with pytest.raises(CustomizationValidationError):
        service.create_rule_version(
            tenant_a.id,
            rule_id=rule.id,
            actor_id=actor_id,
            condition_ast={"operator": "eval", "value": "__import__('os')"},
            action_ast=[{"type": "set-derived-value", "field": "status", "value": "x"}],
            change_summary="Unsafe",
        )

    version = service.create_rule_version(
        tenant_a.id,
        rule_id=rule.id,
        actor_id=actor_id,
        condition_ast={"operator": "eq", "field": "status", "value": "active"},
        action_ast=[
            {
                "type": "emit-field-diagnostic",
                "field": "status",
                "message": "Status is active",
            }
        ],
        change_summary="Initial deterministic rule",
    )
    service.publish_rule_version(
        tenant_a.id,
        rule_id=rule.id,
        version_id=version.id,
        transition_key="publish-rule-1",
        actor_id=actor_id,
    )
    first = service.evaluate(
        tenant_a.id,
        rule_id=rule.id,
        record={"status": "active", "secret": "not persisted"},
        changed_fields=["status"],
        target_record_id=uuid.uuid4(),
        actor_id=actor_id,
        idempotency_key="evaluation-1",
    )
    second = service.evaluate(
        tenant_a.id,
        rule_id=rule.id,
        record={"status": "active", "secret": "not persisted"},
        changed_fields=["status"],
        target_record_id=first.target_record_id,
        actor_id=actor_id,
        idempotency_key="evaluation-1",
    )
    assert first.id == second.id
    assert first.status == "matched"
    assert RuleExecution.objects.get(id=first.id).input_fingerprint != ""
    assert "secret" not in str(first.result)
    assert "not persisted" not in str(first.diagnostics)
    with pytest.raises(EvaluationIdempotencyConflict):
        service.evaluate(
            tenant_a.id,
            rule_id=rule.id,
            record={"status": "inactive"},
            changed_fields=["status"],
            target_record_id=first.target_record_id,
            actor_id=actor_id,
            idempotency_key="evaluation-1",
        )


def test_rule_evaluation_records_not_matched_rejected_and_fail_closed_filter_errors(tenant_a, actor_id) -> None:
    service = BusinessRuleService()
    rule = service.create_rule(
        tenant_a.id,
        actor_id=actor_id,
        data=rule_payload(key="reject-inactive-status"),
    )
    version = service.create_rule_version(
        tenant_a.id,
        rule_id=rule.id,
        actor_id=actor_id,
        condition_ast={"operator": "eq", "field": "status", "value": "inactive"},
        action_ast=[{"type": "reject-with-message", "message": "Inactive customers are blocked"}],
        change_summary="Reject inactive customers",
    )
    published = service.publish_rule_version(
        tenant_a.id,
        rule_id=rule.id,
        version_id=version.id,
        transition_key="publish-reject-inactive",
        actor_id=actor_id,
    )

    not_matched = service.evaluate(
        tenant_a.id,
        rule_id=rule.id,
        record={"status": "active"},
        changed_fields=["status"],
        target_record_id=uuid.uuid4(),
        actor_id=actor_id,
        idempotency_key="rule-not-matched",
    )
    rejected = service.evaluate(
        tenant_a.id,
        rule_id=rule.id,
        record={"status": "inactive"},
        changed_fields=["status"],
        target_record_id=uuid.uuid4(),
        actor_id=actor_id,
        idempotency_key="rule-rejected",
    )

    assert published.status == "published"
    assert not_matched.status == "not_matched"
    assert not_matched.result == {"matched": False, "actions": []}
    assert rejected.status == "rejected"
    assert rejected.result["actions"] == [{"type": "reject-with-message", "message": "Inactive customers are blocked"}]
    assert list(service.list_executions(tenant_a.id, filters={"status": "rejected"})) == [rejected]
    with pytest.raises(CustomizationValidationError, match="unsupported execution filter"):
        list(service.list_executions(tenant_a.id, filters={"tenant_id": tenant_a.id}))
    with pytest.raises(CustomizationValidationError, match="unsupported ordering field"):
        list(service.list_executions(tenant_a.id, ordering="rule_id"))
    with pytest.raises(CustomizationNotFound):
        service.get_execution(tenant_a.id, execution_id=uuid.uuid4())


def test_evaluate_for_resource_respects_priority_and_stop_on_match(tenant_a, actor_id) -> None:
    service = BusinessRuleService()
    first = service.create_rule(
        tenant_a.id,
        actor_id=actor_id,
        data=rule_payload(key="first-match", priority=1, stop_on_match=True),
    )
    first_version = service.create_rule_version(
        tenant_a.id,
        rule_id=first.id,
        actor_id=actor_id,
        condition_ast={"operator": "eq", "field": "status", "value": "active"},
        action_ast=[{"type": "emit-field-diagnostic", "field": "status", "message": "First"}],
        change_summary="First match",
    )
    service.publish_rule_version(
        tenant_a.id,
        rule_id=first.id,
        version_id=first_version.id,
        transition_key="publish-first-match",
        actor_id=actor_id,
    )
    second = service.create_rule(
        tenant_a.id,
        actor_id=actor_id,
        data=rule_payload(key="second-match", priority=2, stop_on_match=False),
    )
    second_version = service.create_rule_version(
        tenant_a.id,
        rule_id=second.id,
        actor_id=actor_id,
        condition_ast={"operator": "eq", "field": "status", "value": "active"},
        action_ast=[{"type": "emit-field-diagnostic", "field": "status", "message": "Second"}],
        change_summary="Second match",
    )
    service.publish_rule_version(
        tenant_a.id,
        rule_id=second.id,
        version_id=second_version.id,
        transition_key="publish-second-match",
        actor_id=actor_id,
    )

    executions = CustomizationRegistry.evaluate_rules(
        tenant_a.id,
        "crm",
        "customer",
        "validate",
        {"status": "active"},
        ["status"],
        actor_id,
        "resource-eval",
    )

    assert [execution.rule_id for execution in executions] == [first.id]
    assert executions[0].status == "matched"
    with pytest.raises(CustomizationValidationError):
        service.evaluate_for_resource(
            tenant_a.id,
            module="crm",
            resource="customer",
            trigger="unsupported",
            record={},
            changed_fields=[],
            target_record_id=None,
            actor_id=actor_id,
            idempotency_key="unsupported-trigger",
        )


def test_append_only_evidence_cannot_be_changed_through_orm(
    execution_pair,
) -> None:
    own, _foreign = execution_pair
    with pytest.raises(ValidationError):
        RuleExecution.objects.filter(id=own.id).update(status="failed")
    with pytest.raises(ValidationError):
        own.delete()


def test_rule_condition_engine_covers_boolean_comparison_membership_and_string_operators(tenant_a) -> None:
    diagnostics: list[dict[str, object]] = []
    budget = _EvaluationBudget(tenant_a.id)
    record = {"status": "active", "amount": 10, "tags": ["vip", "north"], "note": "invoice-ready"}
    changed = frozenset({"status"})

    assert _evaluate_condition(
        {
            "operator": "and",
            "operands": [
                {"operator": "changed", "field": "status"},
                {"operator": "gte", "field": "amount", "value": 10},
                {"operator": "lte", "field": "amount", "value": 10},
                {"operator": "contains", "field": "tags", "value": "vip"},
                {"operator": "starts_with", "field": "note", "value": "invoice"},
                {"operator": "ends_with", "field": "note", "value": "ready"},
                {"operator": "not_null", "field": "note"},
                {"operator": "not", "operand": {"operator": "is_null", "field": "note"}},
            ],
        },
        record,
        changed,
        budget,
        diagnostics,
    )
    assert _evaluate_condition(
        {
            "operator": "or",
            "operands": [
                {"operator": "lt", "field": "amount", "value": 1},
                {"operator": "in", "field": "status", "values": ["active", "pending"]},
            ],
        },
        record,
        changed,
        budget,
        diagnostics,
    )
    assert _evaluate_condition(
        {"operator": "not_in", "field": "status", "values": ["retired"]},
        record,
        changed,
        budget,
        diagnostics,
    )
    assert _evaluate_condition({"operator": "ne", "field": "status", "value": "inactive"}, record, changed, budget, [])
    assert (
        _evaluate_condition({"operator": "gt", "field": "amount", "value": "bad"}, record, changed, budget, []) is False
    )
    assert {item["operator"] for item in diagnostics} >= {"and", "or", "contains", "starts_with", "ends_with"}


def test_rule_ast_validation_rejects_unknown_keys_empty_operands_and_bad_action_shapes(tenant_a) -> None:
    budget = _EvaluationBudget(tenant_a.id)

    with pytest.raises(CustomizationValidationError, match="condition nodes"):
        _validate_condition([], budget)
    with pytest.raises(CustomizationValidationError, match="dangerous keys"):
        _validate_condition({"operator": "eq", "field": "status", "import": "os"}, budget)
    with pytest.raises(CustomizationValidationError, match="and requires operands"):
        _validate_condition({"operator": "and", "operands": []}, budget)
    with pytest.raises(CustomizationValidationError, match="simple slug"):
        _validate_condition({"operator": "eq", "field": "../status", "value": "active"}, budget)

    with pytest.raises(CustomizationValidationError, match="non-empty array"):
        _validate_actions([], budget)
    with pytest.raises(CustomizationValidationError, match="actions must be objects"):
        _validate_actions(["bad"], budget)
    with pytest.raises(CustomizationValidationError, match="dangerous keys"):
        _validate_actions([{"type": "set-visible", "field": "status", "call": "eval"}], budget)
    with pytest.raises(CustomizationValidationError, match="action message"):
        _validate_actions([{"type": "reject-with-message", "message": ""}], budget)


def test_published_rule_identity_is_immutable_and_draft_rule_can_be_deleted(tenant_a, actor_id) -> None:
    service = BusinessRuleService()
    rule = service.create_rule(tenant_a.id, actor_id=actor_id, data=rule_payload(key="immutable-rule"))
    version = service.create_rule_version(
        tenant_a.id,
        rule_id=rule.id,
        actor_id=actor_id,
        condition_ast={"operator": "eq", "field": "status", "value": "active"},
        action_ast=[{"type": "emit-field-diagnostic", "field": "status", "message": "Active"}],
        change_summary="Publish immutable rule",
    )
    service.publish_rule_version(
        tenant_a.id,
        rule_id=rule.id,
        version_id=version.id,
        transition_key="publish-immutable-rule",
        actor_id=actor_id,
    )
    rule.refresh_from_db()

    with pytest.raises(CustomizationValidationError, match="immutable"):
        service.update_rule(
            tenant_a.id,
            rule_id=rule.id,
            expected_lock_version=rule.lock_version,
            actor_id=actor_id,
            data={"trigger": "before_update"},
        )

    draft = service.create_rule(tenant_a.id, actor_id=actor_id, data=rule_payload(key="delete-draft-rule"))
    deleted = service.delete_rule(
        tenant_a.id,
        rule_id=draft.id,
        expected_lock_version=draft.lock_version,
        actor_id=actor_id,
    )
    assert deleted.deleted_at is not None
