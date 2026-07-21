"""Persistence contracts for every customization domain entity."""

from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from src.core.tenancy import TenantScopedModel, TimestampedModel
from src.modules.customization_framework.models import (
    BusinessRule,
    BusinessRuleVersion,
    CustomFieldDefinition,
    CustomFieldValue,
    FormDefinition,
    FormLayoutVersion,
    RuleExecution,
)

from .factories import (
    BusinessRuleFactory,
    BusinessRuleVersionFactory,
    CustomFieldDefinitionFactory,
    CustomFieldValueFactory,
    FormDefinitionFactory,
    FormLayoutVersionFactory,
    RuleExecutionFactory,
)

pytestmark = pytest.mark.django_db

TENANT_MODELS = (
    CustomFieldDefinition,
    CustomFieldValue,
    FormDefinition,
    FormLayoutVersion,
    BusinessRule,
    BusinessRuleVersion,
    RuleExecution,
)


@pytest.mark.parametrize("model", TENANT_MODELS)
def test_all_domain_models_use_canonical_tenant_uuid_identity(model: type) -> None:
    assert issubclass(model, TenantScopedModel)
    assert model._meta.get_field("tenant_id").get_internal_type() == "UUIDField"
    assert model._meta.get_field("tenant_id").db_index is True
    identity = model._meta.pk
    assert identity is not None
    assert identity.get_internal_type() == "UUIDField"
    assert identity.editable is False


@pytest.mark.parametrize(
    ("model", "table"),
    (
        (CustomFieldDefinition, "customization_field_definitions"),
        (CustomFieldValue, "customization_field_values"),
        (FormDefinition, "customization_form_definitions"),
        (FormLayoutVersion, "customization_form_layout_versions"),
        (BusinessRule, "customization_business_rules"),
        (BusinessRuleVersion, "customization_business_rule_versions"),
        (RuleExecution, "customization_rule_executions"),
    ),
)
def test_domain_table_contract_is_stable(model: type, table: str) -> None:
    assert model._meta.db_table == table
    assert all(len(index.name) <= 63 for index in model._meta.indexes)
    assert all(len(constraint.name) <= 63 for constraint in model._meta.constraints)


def test_mutable_aggregates_expose_audit_soft_delete_and_lock_contract() -> None:
    for model in (CustomFieldDefinition, CustomFieldValue, FormDefinition, BusinessRule):
        assert issubclass(model, TimestampedModel)
        names = {field.name for field in model._meta.fields}
        assert {"created_by", "updated_by", "deleted_at", "deleted_by", "lock_version"} <= names
        instance = {
            CustomFieldDefinition: CustomFieldDefinitionFactory,
            CustomFieldValue: CustomFieldValueFactory,
            FormDefinition: FormDefinitionFactory,
            BusinessRule: BusinessRuleFactory,
        }[model]()
        assert instance.lock_version == 1
        assert instance.deleted_at is None


def test_uuid_defaults_and_human_readable_labels() -> None:
    field = CustomFieldDefinitionFactory()
    form = FormDefinitionFactory()
    rule = BusinessRuleFactory()
    assert isinstance(field.id, uuid.UUID)
    assert field.key in str(field)
    assert form.key in str(form)
    assert rule.key in str(rule)


def test_duplicate_live_field_definition_key_is_rejected() -> None:
    original = CustomFieldDefinitionFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        CustomFieldDefinitionFactory(
            tenant_id=original.tenant_id,
            owner_module=original.owner_module,
            target_resource=original.target_resource,
            key=original.key,
        )


def test_duplicate_live_value_is_rejected() -> None:
    original = CustomFieldValueFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        CustomFieldValueFactory(
            definition=original.definition,
            tenant_id=original.tenant_id,
            target_record_id=original.target_record_id,
        )


def test_duplicate_form_and_rule_versions_are_rejected() -> None:
    layout = FormLayoutVersionFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        FormLayoutVersionFactory(
            form=layout.form,
            tenant_id=layout.tenant_id,
            version=layout.version,
            content_hash="d" * 64,
        )

    version = BusinessRuleVersionFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        BusinessRuleVersionFactory(
            rule=version.rule,
            tenant_id=version.tenant_id,
            version=version.version,
            content_hash="e" * 64,
        )


def test_duplicate_execution_idempotency_key_is_rejected() -> None:
    execution = RuleExecutionFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        RuleExecutionFactory(
            rule=execution.rule,
            rule_version=execution.rule_version,
            tenant_id=execution.tenant_id,
            idempotency_key=execution.idempotency_key,
        )


@pytest.mark.parametrize(
    "instance",
    (
        pytest.param(
            lambda: CustomFieldValueFactory.build(
                tenant_id=uuid.uuid4(), definition=CustomFieldDefinitionFactory()
            ),
            id="field-value",
        ),
        pytest.param(
            lambda: FormLayoutVersionFactory.build(
                tenant_id=uuid.uuid4(), form=FormDefinitionFactory()
            ),
            id="layout",
        ),
        pytest.param(
            lambda: BusinessRuleVersionFactory.build(
                tenant_id=uuid.uuid4(), rule=BusinessRuleFactory()
            ),
            id="rule-version",
        ),
    ),
)
def test_cross_tenant_parent_relations_fail_validation(instance) -> None:
    with pytest.raises(ValidationError):
        instance().full_clean()


def test_append_only_versions_and_executions_reject_update_and_delete() -> None:
    for row in (FormLayoutVersionFactory(), BusinessRuleVersionFactory(), RuleExecutionFactory()):
        with pytest.raises((ValidationError, TypeError, RuntimeError)):
            row.save()
        with pytest.raises((ValidationError, TypeError, RuntimeError)):
            row.delete()


def test_business_rule_priority_database_constraint() -> None:
    rule = BusinessRuleFactory.build(priority=0)
    with pytest.raises(ValidationError):
        rule.full_clean()
