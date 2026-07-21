"""Domain-service evidence for validation, lifecycle, publication, and evaluation."""

from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError

from src.core.async_jobs.models import OutboxEvent
from src.modules.customization_framework.models import RuleExecution
from src.modules.customization_framework.services import (
    BusinessRuleService,
    CustomFieldService,
    CustomizationNotFound,
    CustomizationRegistry,
    CustomizationValidationError,
    EvaluationIdempotencyConflict,
    FormService,
    OptimisticLockConflict,
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
    contract = CustomizationRegistry.resolve_resource_contract(
        tenant_a.id, "crm", "customer", "1.0"
    )
    assert contract.available is True
    with pytest.raises(CustomizationValidationError):
        CustomizationRegistry.register_resource_contract(
            "crm",
            "customer",
            "1.0",
            {},
            {"custom_field_types": ["text"], "rule_triggers": ["validate"]},
        )
    unavailable = CustomizationRegistry.unregister_resource_contract(
        "crm", "customer", "1.0"
    )
    assert unavailable is not None and unavailable.available is False
    with pytest.raises(Exception) as caught:
        CustomizationRegistry.resolve_resource_contract(
            tenant_a.id, "crm", "customer", "1.0"
        )
    assert getattr(caught.value, "status_code", None) == 503


def test_field_definition_lifecycle_value_and_impact_are_real(tenant_a, actor_id) -> None:
    service = CustomFieldService()
    definition = service.create_definition(
        tenant_a.id, actor_id=actor_id, data=field_payload(default_value="CUST-1")
    )
    assert definition.status == "draft"
    assert OutboxEvent.objects.for_tenant(tenant_a.id).filter(
        aggregate_id=definition.id,
        event_type="customization_framework.field_definition.created",
    ).exists()

    definition = service.transition_definition(
        tenant_a.id,
        definition_id=definition.id,
        command="activate",
        transition_key="activate-1",
        actor_id=actor_id,
    )
    assert definition.status == "active"
    assert definition.activated_at is not None
    assert service.validate_value(
        tenant_a.id, definition_id=definition.id, value="CUST-2"
    )["valid"] is True

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
    assert service.get_value(
        tenant_a.id, definition_id=definition.id, target_record_id=record_id
    ).id == value.id
    assert service.get_definition_impact(
        tenant_a.id, definition_id=definition.id
    )["blocking"] is True
    with pytest.raises(CustomizationValidationError):
        service.delete_definition(
            tenant_a.id,
            definition_id=definition.id,
            expected_lock_version=definition.lock_version,
            actor_id=actor_id,
        )


def test_field_value_validation_rejects_type_source_and_duplicate_create(
    tenant_a, actor_id
) -> None:
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


def test_form_layout_publication_is_atomic_versioned_and_renderable(
    tenant_a, actor_id
) -> None:
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


def test_layout_rejects_duplicate_and_unresolved_field_references(
    tenant_a, actor_id
) -> None:
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


def test_rule_version_rejects_dangerous_ast_and_evaluates_idempotently(
    tenant_a, actor_id
) -> None:
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


def test_append_only_evidence_cannot_be_changed_through_orm(
    execution_pair,
) -> None:
    own, _foreign = execution_pair
    with pytest.raises(ValidationError):
        RuleExecution.objects.filter(id=own.id).update(status="failed")
    with pytest.raises(ValidationError):
        own.delete()
