"""Typed factories for customization framework domain tests."""

from __future__ import annotations

import uuid

import factory

from src.modules.customization_framework.models import (
    BusinessRule,
    BusinessRuleVersion,
    CustomFieldDefinition,
    CustomFieldValue,
    FormDefinition,
    FormLayoutVersion,
    RuleExecution,
)


class CustomFieldDefinitionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomFieldDefinition

    tenant_id = factory.LazyFunction(uuid.uuid4)
    created_by = factory.LazyFunction(uuid.uuid4)
    updated_by = factory.SelfAttribute("created_by")
    key = factory.Sequence(lambda number: f"customer_reference_{number}")
    label = factory.Sequence(lambda number: f"Customer reference {number}")
    description = "A tenant-owned, contract-bound custom field."
    owner_module = "crm"
    target_resource = "customer"
    target_contract_version = "1.0"
    data_type = "text"
    validation_schema = factory.LazyFunction(lambda: {"maxLength": 120})
    presentation_schema = factory.LazyFunction(lambda: {"control": "text"})


class CustomFieldValueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomFieldValue

    definition = factory.SubFactory(CustomFieldDefinitionFactory)
    tenant_id = factory.SelfAttribute("definition.tenant_id")
    target_record_id = factory.LazyFunction(uuid.uuid4)
    value = "CUST-001"
    definition_revision = 1
    source = "ui"
    created_by = factory.SelfAttribute("definition.created_by")
    updated_by = factory.SelfAttribute("definition.updated_by")


class FormDefinitionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FormDefinition

    tenant_id = factory.LazyFunction(uuid.uuid4)
    created_by = factory.LazyFunction(uuid.uuid4)
    updated_by = factory.SelfAttribute("created_by")
    key = factory.Sequence(lambda number: f"customer_intake_{number}")
    name = factory.Sequence(lambda number: f"Customer intake {number}")
    owner_module = "crm"
    target_resource = "customer"
    target_contract_version = "1.0"


class FormLayoutVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FormLayoutVersion

    form = factory.SubFactory(FormDefinitionFactory)
    tenant_id = factory.SelfAttribute("form.tenant_id")
    version = 1
    layout = factory.LazyFunction(
        lambda: {
            "schema_version": 1,
            "sections": [
                {
                    "id": "main",
                    "label": "Main details",
                    "rows": [],
                }
            ],
        }
    )
    content_hash = factory.LazyFunction(lambda: "a" * 64)
    change_summary = "Initial accessible layout"
    created_by = factory.SelfAttribute("form.created_by")


class BusinessRuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BusinessRule

    tenant_id = factory.LazyFunction(uuid.uuid4)
    created_by = factory.LazyFunction(uuid.uuid4)
    updated_by = factory.SelfAttribute("created_by")
    key = factory.Sequence(lambda number: f"require_reference_{number}")
    name = factory.Sequence(lambda number: f"Require customer reference {number}")
    owner_module = "crm"
    target_resource = "customer"
    target_contract_version = "1.0"
    trigger = "validate"
    priority = factory.Sequence(lambda number: 100 + number)


class BusinessRuleVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BusinessRuleVersion

    rule = factory.SubFactory(BusinessRuleFactory)
    tenant_id = factory.SelfAttribute("rule.tenant_id")
    version = 1
    condition_ast = factory.LazyFunction(
        lambda: {"operator": "equals", "field": "status", "value": "active"}
    )
    action_ast = factory.LazyFunction(
        lambda: {
            "actions": [
                {"type": "emit-field-diagnostic", "field": "status", "message": "Status is active"}
            ]
        }
    )
    dependencies = factory.LazyFunction(list)
    content_hash = factory.LazyFunction(lambda: "b" * 64)
    change_summary = "Initial deterministic rule"
    created_by = factory.SelfAttribute("rule.created_by")


class RuleExecutionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RuleExecution

    rule_version = factory.SubFactory(BusinessRuleVersionFactory)
    rule = factory.SelfAttribute("rule_version.rule")
    tenant_id = factory.SelfAttribute("rule.tenant_id")
    target_record_id = factory.LazyFunction(uuid.uuid4)
    trigger = "validate"
    idempotency_key = factory.LazyFunction(lambda: f"evaluation:{uuid.uuid4()}")
    status = "matched"
    input_fingerprint = factory.LazyFunction(lambda: "c" * 64)
    result = factory.LazyFunction(lambda: {"mutations": []})
    diagnostics = factory.LazyFunction(list)
    duration_ms = 1
    correlation_id = factory.LazyFunction(uuid.uuid4)
    executed_by = factory.LazyFunction(uuid.uuid4)
