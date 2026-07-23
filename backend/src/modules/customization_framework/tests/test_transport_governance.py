"""Regression proof for fail-closed transport and manifest-owned governance."""

from __future__ import annotations

import uuid
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from django.apps import apps
from rest_framework.permissions import IsAuthenticated

from src.modules.customization_framework import api
from src.modules.customization_framework.models import (
    BusinessRule,
    BusinessRuleVersion,
    CustomFieldDefinition,
    CustomFieldValue,
    FormDefinition,
    FormLayoutVersion,
    RuleExecution,
)
from src.modules.customization_framework.permissions import ACTION_ACCESS, PERMISSIONS, SOD_ACTIONS
from src.modules.customization_framework.serializers import (
    RuleExecutionDetailSerializer,
    RuleExecutionListSerializer,
)
from src.modules.customization_framework.services import (
    BusinessRuleService,
    CustomFieldService,
    CustomizationValidationError,
    FormService,
    default_configuration_document,
)
from src.modules.customization_framework.urls import router

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


@pytest.mark.parametrize(
    ("viewset", "model"),
    (
        (api.FieldDefinitionViewSet, CustomFieldDefinition),
        (api.FieldValueViewSet, CustomFieldValue),
        (api.FormDefinitionViewSet, FormDefinition),
        (api.FormLayoutVersionViewSet, FormLayoutVersion),
        (api.BusinessRuleViewSet, BusinessRule),
        (api.BusinessRuleVersionViewSet, BusinessRuleVersion),
        (api.RuleExecutionViewSet, RuleExecution),
    ),
)
def test_every_tenant_queryset_is_explicitly_empty_without_context(
    monkeypatch: pytest.MonkeyPatch,
    viewset: type,
    model: type,
) -> None:
    monkeypatch.setattr(api, "get_current_tenant_id", lambda: None)
    view = viewset()
    view.action = "list"
    view.request = SimpleNamespace(
        tenant_id=None,
        query_params={},
        user=SimpleNamespace(profile=None),
    )

    queryset = view.get_queryset()

    assert queryset.model is model
    assert queryset.query.is_empty()


def test_field_value_query_construction_is_service_owned_and_tenant_scoped(
    tenant_a: object,
    tenant_b: object,
) -> None:
    own_definition = CustomFieldDefinitionFactory(tenant_id=tenant_a.id)
    foreign_definition = CustomFieldDefinitionFactory(tenant_id=tenant_b.id)
    own = CustomFieldValueFactory(
        tenant_id=tenant_a.id,
        definition=own_definition,
        source="ui",
    )
    CustomFieldValueFactory(
        tenant_id=tenant_b.id,
        definition=foreign_definition,
        source="ui",
    )
    service = CustomFieldService()

    values = service.list_values(
        uuid.UUID(str(tenant_a.id)),
        filters={"definition_id": own_definition.id, "source": "ui"},
        ordering="-created_at",
    )

    assert list(values.values_list("id", flat=True)) == [own.id]
    with pytest.raises(CustomizationValidationError) as invalid_datetime:
        service.list_values(
            uuid.UUID(str(tenant_a.id)),
            filters={
                "definition_id": own_definition.id,
                "updated_at_after": "not-a-datetime",
            },
        )
    assert invalid_datetime.value.detail == {"updated_at_after": ["Must be an ISO-8601 datetime."]}


def test_nested_version_queries_are_service_owned_and_tenant_scoped(
    tenant_a: object,
    tenant_b: object,
) -> None:
    own_form = FormDefinitionFactory(tenant_id=tenant_a.id)
    foreign_form = FormDefinitionFactory(tenant_id=tenant_b.id)
    own_layout = FormLayoutVersionFactory(tenant_id=tenant_a.id, form=own_form)
    FormLayoutVersionFactory(tenant_id=tenant_b.id, form=foreign_form)
    own_rule = BusinessRuleFactory(tenant_id=tenant_a.id)
    foreign_rule = BusinessRuleFactory(tenant_id=tenant_b.id)
    own_version = BusinessRuleVersionFactory(tenant_id=tenant_a.id, rule=own_rule)
    BusinessRuleVersionFactory(tenant_id=tenant_b.id, rule=foreign_rule)

    layouts = FormService().list_layout_versions(
        uuid.UUID(str(tenant_a.id)),
        filters={"form_id": own_form.id},
    )
    versions = BusinessRuleService().list_rule_versions(
        uuid.UUID(str(tenant_a.id)),
        filters={"rule_id": own_rule.id},
    )

    assert list(layouts.values_list("id", flat=True)) == [own_layout.id]
    assert list(versions.values_list("id", flat=True)) == [own_version.id]


def test_execution_public_dto_is_named_and_omits_replay_security_evidence() -> None:
    execution = RuleExecutionFactory()

    list_payload = RuleExecutionListSerializer(execution).data
    detail_payload = RuleExecutionDetailSerializer(execution).data

    assert list_payload["rule_name"] == execution.rule.name
    assert detail_payload["rule_name"] == execution.rule.name
    assert {
        "tenant_id",
        "rule",
        "rule_version",
        "executed_by",
        "idempotency_key",
        "input_fingerprint",
    }.isdisjoint(detail_payload)


def test_configuration_api_exposes_seed_and_versioned_rollback(
    authenticated_tenant_a_client: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        api.RuntimeConfigurationViewSet,
        "get_permissions",
        lambda self: [IsAuthenticated()],
    )
    base = "/api/v2/customization-framework/configuration"
    initial = authenticated_tenant_a_client.get(f"{base}/")
    assert initial.status_code == 200
    assert initial.json()["data"]["version"] == 0
    assert initial.json()["data"]["id"] is None

    document = default_configuration_document()
    preview = authenticated_tenant_a_client.post(
        f"{base}/preview/",
        {"document": document},
        format="json",
    )
    assert preview.status_code == 200
    assert preview.json()["data"]["valid"] is True

    first = authenticated_tenant_a_client.patch(
        f"{base}/update/",
        {
            "document": document,
            "environment": "default",
            "expected_version": 0,
        },
        format="json",
    )
    assert first.status_code == 200, first.json()
    assert first.json()["data"]["version"] == 1

    changed = deepcopy(document)
    changed["list_preferences"]["page_size"] = 30
    second = authenticated_tenant_a_client.patch(
        f"{base}/update/",
        {
            "document": changed,
            "environment": "default",
            "expected_version": 1,
        },
        format="json",
    )
    assert second.status_code == 200, second.json()
    assert second.json()["data"]["version"] == 2

    rolled_back = authenticated_tenant_a_client.post(
        f"{base}/rollback/",
        {
            "target_version": 1,
            "expected_version": 2,
        },
        format="json",
    )
    assert rolled_back.status_code == 200, rolled_back.json()
    assert rolled_back.json()["data"]["version"] == 3
    assert rolled_back.json()["data"]["document"]["list_preferences"]["page_size"] == 25

    history = authenticated_tenant_a_client.get(f"{base}/history/")
    assert history.status_code == 200
    assert [item["version"] for item in history.json()["data"]] == [3, 2, 1]
    exported = authenticated_tenant_a_client.get(f"{base}/export/")
    assert exported.status_code == 200
    assert exported.json()["data"]["version"] == 3


def test_manifest_is_the_exact_runtime_inventory_and_policy_source() -> None:
    manifest_path = Path(api.__file__).with_name("manifest.yaml")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    metadata = manifest["metadata"]
    app_config = apps.get_app_config("customization_framework")

    assert set(metadata["entities"]) == {model._meta.db_table for model in app_config.get_models()}
    declared_router = {
        endpoint["prefix"]: (endpoint["basename"], endpoint["viewset"])
        for endpoint in metadata["endpoints"]
        if endpoint["registration"] == "router"
    }
    actual_router = {prefix: (basename, viewset.__name__) for prefix, viewset, basename in router.registry}
    assert declared_router == actual_router
    assert tuple(manifest["permissions"]) == PERMISSIONS
    assert set(metadata["access_policy"]) == set(ACTION_ACCESS)
    assert tuple(tuple(pair["actions"]) for pair in metadata["sod_pairs"]) == SOD_ACTIONS
