"""Reusable and action-level tenant-isolation proofs for customization v2."""

from __future__ import annotations

import uuid

import pytest
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from src.core.testing.tenant_contract import TenantIsolationContract
from src.modules.customization_framework import api
from src.modules.customization_framework.models import (
    BusinessRule,
    CustomFieldDefinition,
    CustomFieldValue,
    FormDefinition,
)

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db

BASE = "/api/v2/customization-framework"


@pytest.fixture(autouse=True)
def isolate_http_isolation_from_policy_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api.GovernedTenantViewSet, "get_permissions", lambda self: [IsAuthenticated()])


class GovernedEnvelopeIsolationContract(TenantIsolationContract):
    read_denial_statuses = frozenset({status.HTTP_404_NOT_FOUND})

    def get_list_items(self, response: object) -> list[dict[str, object]]:
        return response.json()["data"]


class TestFieldDefinitionIsolation(GovernedEnvelopeIsolationContract):
    model = CustomFieldDefinition
    list_url = f"{BASE}/field-definitions/"
    detail_url_template = f"{BASE}/field-definitions/{{pk}}/"
    create_payload = {
        "key": "spoofed-field",
        "label": "Spoofed field",
        "owner_module": "crm",
        "target_resource": "customer",
        "target_contract_version": "1.0",
        "data_type": "text",
    }
    update_payload = {"label": "Cross tenant", "expected_lock_version": 1}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, field_pair) -> None:
        self.client = authenticated_tenant_a_client
        self.tenant_a_row, self.tenant_b_row = field_pair


class TestFieldValueIsolation(GovernedEnvelopeIsolationContract):
    model = CustomFieldValue
    detail_url_template = f"{BASE}/field-values/{{pk}}/"
    update_payload = {"value": "cross-tenant", "source": "api", "expected_lock_version": 1}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, value_pair) -> None:
        self.client = authenticated_tenant_a_client
        self.tenant_a_row, self.tenant_b_row = value_pair
        CustomFieldDefinition.objects.filter(id=self.tenant_a_row.definition_id).update(
            status="active", activated_at="2026-01-01T00:00:00Z"
        )

    def get_list_url(self) -> str:
        return f"{BASE}/field-values/?definition_id={self.tenant_a_row.definition_id}"

    def get_create_payload(self) -> dict[str, object]:
        return {
            "definition_id": str(self.tenant_a_row.definition_id),
            "target_record_id": str(uuid.uuid4()),
            "value": "safe",
            "source": "api",
        }


class TestFormDefinitionIsolation(GovernedEnvelopeIsolationContract):
    model = FormDefinition
    list_url = f"{BASE}/forms/"
    detail_url_template = f"{BASE}/forms/{{pk}}/"
    create_payload = {
        "key": "spoofed-form",
        "name": "Spoofed form",
        "owner_module": "crm",
        "target_resource": "customer",
        "target_contract_version": "1.0",
    }
    update_payload = {"name": "Cross tenant", "expected_lock_version": 1}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, form_pair) -> None:
        self.client = authenticated_tenant_a_client
        self.tenant_a_row, self.tenant_b_row = form_pair


class TestBusinessRuleIsolation(GovernedEnvelopeIsolationContract):
    model = BusinessRule
    list_url = f"{BASE}/rules/"
    detail_url_template = f"{BASE}/rules/{{pk}}/"
    create_payload = {
        "key": "spoofed-rule",
        "name": "Spoofed rule",
        "owner_module": "crm",
        "target_resource": "customer",
        "target_contract_version": "1.0",
        "trigger": "validate",
        "priority": 500,
        "stop_on_match": False,
    }
    update_payload = {"name": "Cross tenant", "expected_lock_version": 1}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, rule_pair) -> None:
        self.client = authenticated_tenant_a_client
        self.tenant_a_row, self.tenant_b_row = rule_pair


@pytest.mark.parametrize(
    ("collection", "fixture_name"),
    [
        ("form-layouts", "layout_pair"),
        ("rule-versions", "rule_version_pair"),
        ("rule-executions", "execution_pair"),
    ],
)
def test_append_only_resources_are_tenant_scoped_and_immutable(
    request: pytest.FixtureRequest,
    authenticated_tenant_a_client: object,
    collection: str,
    fixture_name: str,
) -> None:
    own, foreign = request.getfixturevalue(fixture_name)
    listing = authenticated_tenant_a_client.get(f"{BASE}/{collection}/")
    assert listing.status_code == 200
    identities = {row["id"] for row in listing.json()["data"]}
    assert str(own.id) in identities
    assert str(foreign.id) not in identities
    detail = f"{BASE}/{collection}/{foreign.id}/"
    assert authenticated_tenant_a_client.get(detail).status_code == 404
    assert authenticated_tenant_a_client.post(f"{BASE}/{collection}/", {"tenant_id": str(foreign.tenant_id)}, format="json").status_code == 405
    assert authenticated_tenant_a_client.patch(detail, {}, format="json").status_code == 405
    assert authenticated_tenant_a_client.delete(detail).status_code == 405


def test_cross_tenant_domain_actions_are_invisible_and_leave_rows_unchanged(
    authenticated_tenant_a_client: object,
    field_pair: tuple[object, object],
    form_pair: tuple[object, object],
    rule_pair: tuple[object, object],
) -> None:
    _, field = field_pair
    _, form = form_pair
    _, rule = rule_pair
    cases = (
        (field, f"{BASE}/field-definitions/{field.id}/activate/", {"transition_key": "foreign"}),
        (field, f"{BASE}/field-definitions/{field.id}/impact/", None),
        (form, f"{BASE}/forms/{form.id}/render-schema/", None),
        (form, f"{BASE}/forms/{form.id}/impact/", None),
        (rule, f"{BASE}/rules/{rule.id}/impact/", None),
        (
            rule,
            f"{BASE}/rules/{rule.id}/evaluate/",
            {"record": {}, "changed_fields": [], "idempotency_key": "foreign-evaluation"},
        ),
    )
    for row, path, payload in cases:
        before = tuple((field.attname, getattr(row, field.attname)) for field in row._meta.concrete_fields)
        response = authenticated_tenant_a_client.get(path) if payload is None else authenticated_tenant_a_client.post(path, payload, format="json")
        assert response.status_code == 404, response.content
        row.refresh_from_db()
        after = tuple((field.attname, getattr(row, field.attname)) for field in row._meta.concrete_fields)
        assert after == before


def test_cross_tenant_child_identifiers_are_rejected(
    authenticated_tenant_a_client: object,
    form_pair: tuple[object, object],
    rule_pair: tuple[object, object],
) -> None:
    _, foreign_form = form_pair
    _, foreign_rule = rule_pair
    layout = authenticated_tenant_a_client.post(
        f"{BASE}/forms/{foreign_form.id}/layout-versions/",
        {"layout": {"schema_version": 1, "sections": []}, "change_summary": "Foreign"},
        format="json",
    )
    version = authenticated_tenant_a_client.post(
        f"{BASE}/rules/{foreign_rule.id}/versions/",
        {
            "condition_ast": {"operator": "eq", "field": "status", "value": "active"},
            "action_ast": [{"type": "emit-field-diagnostic", "field": "status", "message": "Active"}],
            "change_summary": "Foreign",
        },
        format="json",
    )
    assert layout.status_code == 404
    assert version.status_code == 404
