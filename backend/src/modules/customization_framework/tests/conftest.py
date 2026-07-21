"""Shared customization framework fixtures with real tenant identities."""

from __future__ import annotations

import uuid

import pytest

from src.core.testing.factories import authenticated_api_client
from src.modules.customization_framework.services import CustomizationRegistry

from .factories import (
    BusinessRuleFactory,
    BusinessRuleVersionFactory,
    CustomFieldDefinitionFactory,
    CustomFieldValueFactory,
    FormDefinitionFactory,
    FormLayoutVersionFactory,
    RuleExecutionFactory,
)

pytest_plugins = ["src.core.testing.factories"]


@pytest.fixture(autouse=True)
def registered_resource_contract():
    """Expose one real free-module contract without leaking registry state."""

    CustomizationRegistry._contracts.clear()
    CustomizationRegistry.register_resource_contract(
        "crm",
        "customer",
        "1.0",
        {"status": {"type": "string"}},
        {
            "custom_field_types": [
                "text",
                "long_text",
                "integer",
                "decimal",
                "boolean",
                "date",
                "datetime",
                "uuid",
                "choice",
                "multi_choice",
                "json",
            ],
            "form_surfaces": ["default"],
            "rule_triggers": [
                "validate",
                "before_create",
                "before_update",
                "form_change",
            ],
            "available": True,
        },
    )
    yield
    CustomizationRegistry._contracts.clear()


@pytest.fixture
def actor_id(tenant_a_user):
    return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{tenant_a_user.pk}")


@pytest.fixture
def authenticated_tenant_a_client(tenant_a, tenant_a_user):
    del tenant_a
    return authenticated_api_client(tenant_a_user)


@pytest.fixture
def tenant_b_client(tenant_b, tenant_b_user):
    del tenant_b
    return authenticated_api_client(tenant_b_user)


@pytest.fixture
def field_pair(tenant_a, tenant_b):
    return (
        CustomFieldDefinitionFactory(tenant_id=tenant_a.id),
        CustomFieldDefinitionFactory(tenant_id=tenant_b.id),
    )


@pytest.fixture
def value_pair(field_pair):
    own, foreign = field_pair
    return (
        CustomFieldValueFactory(definition=own, tenant_id=own.tenant_id),
        CustomFieldValueFactory(definition=foreign, tenant_id=foreign.tenant_id),
    )


@pytest.fixture
def form_pair(tenant_a, tenant_b):
    return (
        FormDefinitionFactory(tenant_id=tenant_a.id),
        FormDefinitionFactory(tenant_id=tenant_b.id),
    )


@pytest.fixture
def layout_pair(form_pair):
    own, foreign = form_pair
    return (
        FormLayoutVersionFactory(form=own, tenant_id=own.tenant_id),
        FormLayoutVersionFactory(form=foreign, tenant_id=foreign.tenant_id),
    )


@pytest.fixture
def rule_pair(tenant_a, tenant_b):
    return (
        BusinessRuleFactory(tenant_id=tenant_a.id),
        BusinessRuleFactory(tenant_id=tenant_b.id),
    )


@pytest.fixture
def rule_version_pair(rule_pair):
    own, foreign = rule_pair
    return (
        BusinessRuleVersionFactory(rule=own, tenant_id=own.tenant_id),
        BusinessRuleVersionFactory(rule=foreign, tenant_id=foreign.tenant_id),
    )


@pytest.fixture
def execution_pair(rule_version_pair):
    own, foreign = rule_version_pair
    return (
        RuleExecutionFactory(rule_version=own, tenant_id=own.tenant_id),
        RuleExecutionFactory(rule_version=foreign, tenant_id=foreign.tenant_id),
    )
