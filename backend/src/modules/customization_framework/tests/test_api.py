"""Black-box API v2 contract tests for the customization framework."""

from __future__ import annotations

import uuid

import pytest
from rest_framework.permissions import IsAuthenticated

from src.modules.customization_framework import api

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
pytestmark = pytest.mark.django_db

BASE = "/api/v2/customization-framework"


@pytest.fixture(autouse=True)
def isolate_controller_tests_from_policy_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise controllers after authentication; access branches have dedicated tests."""

    monkeypatch.setattr(api.GovernedTenantViewSet, "get_permissions", lambda self: [IsAuthenticated()])
    monkeypatch.setattr(api.ModuleHealthAPIView, "get_permissions", lambda self: [IsAuthenticated()])


@pytest.fixture
def api_graph(tenant_a: object) -> dict[str, object]:
    tenant_id = uuid.UUID(str(tenant_a.id))
    field = CustomFieldDefinitionFactory(tenant_id=tenant_id, status="active", activated_at="2026-01-01T00:00:00Z")
    value = CustomFieldValueFactory(tenant_id=tenant_id, definition=field)
    form = FormDefinitionFactory(tenant_id=tenant_id)
    layout = FormLayoutVersionFactory(tenant_id=tenant_id, form=form)
    rule = BusinessRuleFactory(tenant_id=tenant_id)
    version = BusinessRuleVersionFactory(tenant_id=tenant_id, rule=rule)
    execution = RuleExecutionFactory(tenant_id=tenant_id, rule=rule, rule_version=version)
    return {
        "field": field,
        "value": value,
        "form": form,
        "layout": layout,
        "rule": rule,
        "version": version,
        "execution": execution,
    }


@pytest.mark.parametrize(
    "path",
    [
        f"{BASE}/resource-contracts/",
        f"{BASE}/field-definitions/",
        f"{BASE}/field-values/?definition_id={uuid.uuid4()}",
        f"{BASE}/forms/",
        f"{BASE}/form-layouts/",
        f"{BASE}/rules/",
        f"{BASE}/rule-versions/",
        f"{BASE}/rule-executions/",
        f"{BASE}/health/",
    ],
)
def test_every_surface_requires_a_real_session(api_client: object, path: str) -> None:
    response = api_client.get(path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert response.json()["error"]["correlation_id"]


def test_all_collections_use_governed_envelopes_and_bounded_pagination(
    authenticated_tenant_a_client: object,
    api_graph: dict[str, object],
) -> None:
    paths = {
        f"{BASE}/field-definitions/?page_size=1000": api_graph["field"].id,
        f"{BASE}/field-values/?definition_id={api_graph['field'].id}&page_size=1000": api_graph["value"].id,
        f"{BASE}/forms/?page_size=1000": api_graph["form"].id,
        f"{BASE}/form-layouts/?page_size=1000": api_graph["layout"].id,
        f"{BASE}/rules/?page_size=1000": api_graph["rule"].id,
        f"{BASE}/rule-versions/?page_size=1000": api_graph["version"].id,
        f"{BASE}/rule-executions/?page_size=1000": api_graph["execution"].id,
    }
    for path, expected_id in paths.items():
        response = authenticated_tenant_a_client.get(path)
        assert response.status_code == 200, response.content
        payload = response.json()
        assert set(payload) == {"data", "meta"}
        assert str(expected_id) in {item["id"] for item in payload["data"]}
        assert payload["meta"]["pagination"]["page_size"] == 100
        assert payload["meta"]["correlation_id"]
        assert payload["meta"]["timestamp"]


def test_resource_contract_discovery_is_typed_paginated_and_validated(
    authenticated_tenant_a_client: object,
) -> None:
    response = authenticated_tenant_a_client.get(f"{BASE}/resource-contracts/?include_unavailable=false")
    assert response.status_code == 200
    contract = response.json()["data"][0]
    assert contract["module"] == "crm"
    assert contract["resource"] == "customer"
    assert contract["version"] == "1.0"
    assert contract["available"] is True
    assert "text" in contract["custom_field_types"]
    assert response.json()["meta"]["pagination"]["count"] == 1
    invalid = authenticated_tenant_a_client.get(f"{BASE}/resource-contracts/?include_unavailable=maybe")
    assert invalid.status_code == 400


def test_read_only_resources_reject_mutation(
    authenticated_tenant_a_client: object,
    api_graph: dict[str, object],
) -> None:
    for collection, row in (
        ("form-layouts", api_graph["layout"]),
        ("rule-versions", api_graph["version"]),
        ("rule-executions", api_graph["execution"]),
    ):
        detail = f"{BASE}/{collection}/{row.id}/"
        assert authenticated_tenant_a_client.patch(detail, {}, format="json").status_code == 405
        assert authenticated_tenant_a_client.delete(detail).status_code == 405
        assert authenticated_tenant_a_client.post(f"{BASE}/{collection}/", {}, format="json").status_code == 405


def test_operation_serializers_reject_server_owned_and_unknown_input() -> None:
    payload = {
        "key": "customer-tier",
        "label": "Customer tier",
        "owner_module": "crm",
        "target_resource": "customer",
        "target_contract_version": "1.0",
        "data_type": "text",
    }
    for field, value in (("tenant_id", str(uuid.uuid4())), ("status", "active"), ("created_by", str(uuid.uuid4()))):
        serializer = api.FieldDefinitionCreateSerializer(data={**payload, field: value})
        assert serializer.is_valid() is False
        assert field in serializer.errors


def test_field_create_patch_conflict_and_validation_errors_are_governed(
    authenticated_tenant_a_client: object,
    api_graph: dict[str, object],
) -> None:
    create = authenticated_tenant_a_client.post(
        f"{BASE}/field-definitions/",
        {
            "key": "customer-tier",
            "label": "Customer tier",
            "description": "A governed tier",
            "owner_module": "crm",
            "target_resource": "customer",
            "target_contract_version": "1.0",
            "data_type": "text",
            "validation_schema": {"maxLength": 20},
            "presentation_schema": {"control": "text"},
        },
        format="json",
    )
    assert create.status_code == 201, create.content
    created = create.json()["data"]
    assert created["key"] == "customer-tier"

    stale = authenticated_tenant_a_client.patch(
        f"{BASE}/field-definitions/{created['id']}/",
        {"label": "Changed", "expected_lock_version": 999},
        format="json",
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "CONFLICT"
    assert stale.json()["error"]["correlation_id"]

    invalid = authenticated_tenant_a_client.post(
        f"{BASE}/field-definitions/",
        {"key": "x", "tenant_id": str(api_graph["field"].tenant_id)},
        format="json",
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"]["correlation_id"]


@pytest.mark.parametrize(
    "path",
    [
        f"{BASE}/field-definitions/?ordering=secret",
        f"{BASE}/forms/?ordering=secret",
        f"{BASE}/rules/?ordering=secret",
        f"{BASE}/rule-executions/?ordering=secret",
        f"{BASE}/field-values/",
    ],
)
def test_unbounded_or_non_allowlisted_queries_fail_safely(
    authenticated_tenant_a_client: object,
    path: str,
) -> None:
    response = authenticated_tenant_a_client.get(path)
    assert response.status_code == 400, response.content
    assert response.json()["error"]["correlation_id"]


def test_search_filter_and_ordering_are_server_side(
    authenticated_tenant_a_client: object,
    api_graph: dict[str, object],
) -> None:
    field = api_graph["field"]
    visible = authenticated_tenant_a_client.get(
        f"{BASE}/field-definitions/?search={field.key}&status=active&ordering=-updated_at"
    )
    hidden = authenticated_tenant_a_client.get(f"{BASE}/field-definitions/?search=does-not-exist")
    assert [row["id"] for row in visible.json()["data"]] == [str(field.id)]
    assert hidden.json()["data"] == []


def test_health_is_governed_and_sanitized(authenticated_tenant_a_client: object) -> None:
    response = authenticated_tenant_a_client.get(f"{BASE}/health/")
    assert response.status_code in {200, 503}
    payload = response.json()
    assert set(payload) == {"data", "meta"}
    serialized = str(payload).lower()
    assert "select " not in serialized
    assert "password" not in serialized
    assert payload["meta"]["correlation_id"]


def test_complete_field_and_value_http_workflow(authenticated_tenant_a_client: object) -> None:
    field = authenticated_tenant_a_client.post(
        f"{BASE}/field-definitions/",
        {
            "key": "http-workflow-field",
            "label": "HTTP workflow field",
            "owner_module": "crm",
            "target_resource": "customer",
            "target_contract_version": "1.0",
            "data_type": "text",
            "required": True,
            "validation_schema": {"minLength": 2},
            "presentation_schema": {"control": "text"},
        },
        format="json",
    ).json()["data"]
    detail = f"{BASE}/field-definitions/{field['id']}/"
    retrieved = authenticated_tenant_a_client.get(detail)
    assert retrieved.status_code == 200
    assert retrieved.json()["data"]["id"] == field["id"]

    updated = authenticated_tenant_a_client.patch(
        detail,
        {"label": "Updated HTTP field", "expected_lock_version": field["lock_version"]},
        format="json",
    ).json()["data"]
    activated = authenticated_tenant_a_client.post(
        f"{detail}activate/", {"transition_key": "activate-http-field"}, format="json"
    ).json()["data"]
    assert activated["status"] == "active"
    assert activated["lock_version"] > updated["lock_version"]

    invalid = authenticated_tenant_a_client.post(
        f"{detail}validate-value/", {"value": "x"}, format="json"
    )
    valid = authenticated_tenant_a_client.post(
        f"{detail}validate-value/", {"value": "valid"}, format="json"
    )
    assert invalid.status_code == 400
    assert valid.status_code == 200 and valid.json()["data"]["valid"] is True

    target = uuid.uuid4()
    created_value = authenticated_tenant_a_client.post(
        f"{BASE}/field-values/",
        {"definition_id": field["id"], "target_record_id": str(target), "value": "valid", "source": "api"},
        format="json",
    ).json()["data"]
    value_detail = f"{BASE}/field-values/{created_value['id']}/"
    assert authenticated_tenant_a_client.get(value_detail).json()["data"]["value"] == "valid"
    changed_value = authenticated_tenant_a_client.patch(
        value_detail,
        {"value": "changed", "source": "ui", "expected_lock_version": created_value["lock_version"]},
        format="json",
    ).json()["data"]
    assert changed_value["value"] == "changed"
    duplicate = authenticated_tenant_a_client.post(
        f"{BASE}/field-values/",
        {"definition_id": field["id"], "target_record_id": str(target), "value": "duplicate", "source": "api"},
        format="json",
    )
    assert duplicate.status_code == 409
    impact = authenticated_tenant_a_client.get(f"{detail}impact/").json()["data"]
    assert impact["value_count"] == 1 and impact["blocking"] is True
    removed = authenticated_tenant_a_client.delete(
        value_detail, {"expected_lock_version": changed_value["lock_version"]}, format="json"
    )
    assert removed.status_code == 200

    deprecated = authenticated_tenant_a_client.post(
        f"{detail}deprecate/", {"transition_key": "deprecate-http-field"}, format="json"
    ).json()["data"]
    retired = authenticated_tenant_a_client.post(
        f"{detail}retire/", {"transition_key": "retire-http-field"}, format="json"
    ).json()["data"]
    assert deprecated["status"] == "deprecated" and retired["status"] == "retired"
    deleted = authenticated_tenant_a_client.delete(
        detail, {"expected_lock_version": retired["lock_version"]}, format="json"
    )
    assert deleted.status_code == 200
    assert authenticated_tenant_a_client.get(detail).status_code == 404


def test_complete_form_version_publication_rollback_and_archive_http_workflow(
    authenticated_tenant_a_client: object,
) -> None:
    created = authenticated_tenant_a_client.post(
        f"{BASE}/forms/",
        {
            "key": "http-intake",
            "name": "HTTP intake",
            "description": "Created through the governed API",
            "owner_module": "crm",
            "target_resource": "customer",
            "target_contract_version": "1.0",
        },
        format="json",
    ).json()["data"]
    detail = f"{BASE}/forms/{created['id']}/"
    updated = authenticated_tenant_a_client.patch(
        detail,
        {"name": "Updated HTTP intake", "expected_lock_version": created["lock_version"]},
        format="json",
    ).json()["data"]
    layout = {
        "schema_version": 1,
        "sections": [{"id": "main", "title": "Main", "components": []}],
    }
    candidate = authenticated_tenant_a_client.post(
        f"{detail}layout-versions/",
        {"layout": layout, "change_summary": "Initial layout"},
        format="json",
    ).json()["data"]
    versions = authenticated_tenant_a_client.get(f"{detail}layout-versions/")
    assert candidate["id"] in {item["id"] for item in versions.json()["data"]}
    assert authenticated_tenant_a_client.get(
        f"{BASE}/form-layouts/{candidate['id']}/"
    ).json()["data"]["content_hash"]
    published = authenticated_tenant_a_client.post(
        f"{detail}publish/",
        {"layout_version_id": candidate["id"], "transition_key": "publish-http-form"},
        format="json",
    ).json()["data"]
    assert published["status"] == "published"
    assert authenticated_tenant_a_client.get(
        f"{BASE}/form-layouts/{published['id']}/"
    ).json()["data"]["status"] == "published"
    render = authenticated_tenant_a_client.get(f"{detail}render-schema/").json()["data"]
    assert render["layout"] == layout
    assert authenticated_tenant_a_client.get(f"{detail}impact/").status_code == 200

    second = authenticated_tenant_a_client.post(
        f"{detail}layout-versions/",
        {
            "layout": {
                "schema_version": 1,
                "sections": [{"id": "other", "title": "Other", "components": []}],
            },
            "change_summary": "Second layout",
        },
        format="json",
    ).json()["data"]
    assert authenticated_tenant_a_client.post(
        f"{detail}publish/",
        {"layout_version_id": second["id"], "transition_key": "publish-second-http-form"},
        format="json",
    ).status_code == 200
    rollback = authenticated_tenant_a_client.post(
        f"{detail}publish/",
        {"layout_version_id": published["id"], "transition_key": "republish-http-form"},
        format="json",
    )
    assert rollback.status_code == 200
    assert rollback.json()["data"]["version"] > second["version"]
    archived = authenticated_tenant_a_client.post(
        f"{detail}archive/", {"transition_key": "archive-http-form"}, format="json"
    ).json()["data"]
    assert archived["status"] == "archived"
    deleted = authenticated_tenant_a_client.delete(
        detail, {"expected_lock_version": archived["lock_version"]}, format="json"
    )
    assert deleted.status_code == 200


def test_complete_rule_version_evaluation_lifecycle_and_rollback_http_workflow(
    authenticated_tenant_a_client: object,
) -> None:
    created = authenticated_tenant_a_client.post(
        f"{BASE}/rules/",
        {
            "key": "http-status-rule",
            "name": "HTTP status rule",
            "owner_module": "crm",
            "target_resource": "customer",
            "target_contract_version": "1.0",
            "trigger": "validate",
            "priority": 20,
            "stop_on_match": False,
        },
        format="json",
    ).json()["data"]
    detail = f"{BASE}/rules/{created['id']}/"
    updated = authenticated_tenant_a_client.patch(
        detail,
        {"description": "Updated through PATCH", "expected_lock_version": created["lock_version"]},
        format="json",
    ).json()["data"]
    assert updated["description"] == "Updated through PATCH"
    version = authenticated_tenant_a_client.post(
        f"{detail}versions/",
        {
            "condition_ast": {"operator": "eq", "field": "status", "value": "active"},
            "action_ast": [{"type": "emit-field-diagnostic", "field": "status", "message": "Active"}],
            "change_summary": "Initial rule",
        },
        format="json",
    ).json()["data"]
    assert version["id"] in {
        item["id"] for item in authenticated_tenant_a_client.get(f"{detail}versions/").json()["data"]
    }
    assert authenticated_tenant_a_client.get(
        f"{BASE}/rule-versions/{version['id']}/"
    ).status_code == 200
    published = authenticated_tenant_a_client.post(
        f"{detail}publish/",
        {"version_id": version["id"], "transition_key": "publish-http-rule"},
        format="json",
    ).json()["data"]
    assert published["status"] == "published"

    matched = authenticated_tenant_a_client.post(
        f"{detail}evaluate/",
        {
            "record": {"status": "active"},
            "changed_fields": ["status"],
            "target_record_id": str(uuid.uuid4()),
            "idempotency_key": "http-match",
        },
        format="json",
    ).json()["data"]
    not_matched_response = authenticated_tenant_a_client.post(
        f"{detail}evaluate/",
        {"record": {"status": "inactive"}, "changed_fields": [], "idempotency_key": "http-no-match"},
        format="json",
    )
    assert not_matched_response.status_code == 200, not_matched_response.json()
    not_matched = not_matched_response.json()["data"]
    assert matched["status"] == "matched" and not_matched["status"] == "not_matched"
    assert authenticated_tenant_a_client.get(
        f"{BASE}/rule-executions/{matched['id']}/"
    ).json()["data"]["correlation_id"]
    assert authenticated_tenant_a_client.get(f"{detail}impact/").json()["data"]["execution_count"] == 2

    paused = authenticated_tenant_a_client.post(
        f"{detail}pause/", {"transition_key": "pause-http-rule"}, format="json"
    ).json()["data"]
    resumed = authenticated_tenant_a_client.post(
        f"{detail}resume/", {"transition_key": "resume-http-rule"}, format="json"
    ).json()["data"]
    assert paused["status"] == "paused" and resumed["status"] == "published"
    second = authenticated_tenant_a_client.post(
        f"{detail}versions/",
        {
            "condition_ast": {"operator": "eq", "field": "status", "value": "inactive"},
            "action_ast": [
                {"type": "emit-field-diagnostic", "field": "status", "message": "Inactive"}
            ],
            "change_summary": "Second rule",
        },
        format="json",
    ).json()["data"]
    assert authenticated_tenant_a_client.post(
        f"{detail}publish/",
        {"version_id": second["id"], "transition_key": "publish-second-http-rule"},
        format="json",
    ).status_code == 200
    rollback = authenticated_tenant_a_client.post(
        f"{detail}publish/",
        {"version_id": published["id"], "transition_key": "republish-http-rule"},
        format="json",
    )
    assert rollback.status_code == 200
    assert rollback.json()["data"]["version"] > second["version"]
    retired = authenticated_tenant_a_client.post(
        f"{detail}retire/", {"transition_key": "retire-http-rule"}, format="json"
    ).json()["data"]
    assert retired["status"] == "retired"
    assert authenticated_tenant_a_client.delete(
        detail, {"expected_lock_version": retired["lock_version"]}, format="json"
    ).status_code == 200
