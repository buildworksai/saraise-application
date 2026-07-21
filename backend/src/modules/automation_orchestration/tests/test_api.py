"""Black-box contracts for the governed v2 orchestration API."""

from __future__ import annotations

import uuid

import pytest
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessReasonCode

from ..api import DefinitionViewSet, EdgeViewSet, NodeViewSet, RunViewSet, ScheduleViewSet, TaskRunViewSet
from ..models import OrchestrationDefinition

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def allow_access_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep real session/CSRF authentication while replacing remote policy IO."""

    def allow(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="test policy allows declared capability",
            tenant_id=uuid.UUID(str(tenant_id)),
            remaining_quota=100,
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", allow)


def _payload(response):
    return response.json()["data"]


def test_unauthenticated_definition_list_is_401(api_client) -> None:
    response = api_client.get("/api/v2/automation-orchestration/definitions/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_definition_crud_uses_v2_envelope_and_pagination(tenant_a_client, tenant_a) -> None:
    create = tenant_a_client.post(
        "/api/v2/automation-orchestration/definitions/",
        {
            "key": "daily-ledger",
            "name": "Daily ledger",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            "output_schema": {"type": "object", "properties": {}, "additionalProperties": True},
        },
        format="json",
    )
    assert create.status_code == status.HTTP_201_CREATED
    created = _payload(create)
    assert created["tenant_id"] == str(tenant_a.id)
    assert create.json()["meta"]["correlation_id"]

    listing = tenant_a_client.get("/api/v2/automation-orchestration/definitions/?search=ledger&page_size=1")
    assert listing.status_code == status.HTTP_200_OK
    assert listing.json()["meta"]["pagination"]["page_size"] == 1
    assert [item["id"] for item in _payload(listing)] == [created["id"]]

    update = tenant_a_client.patch(
        f"/api/v2/automation-orchestration/definitions/{created['id']}/",
        {"name": "Daily general ledger", "transition_key": "api-edit"},
        format="json",
    )
    assert update.status_code == status.HTTP_200_OK
    assert _payload(update)["name"] == "Daily general ledger"

    delete = tenant_a_client.delete(f"/api/v2/automation-orchestration/definitions/{created['id']}/")
    assert delete.status_code == status.HTTP_204_NO_CONTENT
    assert OrchestrationDefinition.objects.get(pk=created["id"]).is_deleted is True


def test_unknown_and_protected_definition_fields_are_rejected(tenant_a_client, tenant_b) -> None:
    response = tenant_a_client.post(
        "/api/v2/automation-orchestration/definitions/",
        {"key": "spoof", "name": "Spoof", "tenant_id": str(tenant_b.id), "status": "published"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unsafe_action_requires_csrf(tenant_a_user) -> None:
    from src.core.testing.factories import authenticated_api_client

    client = authenticated_api_client(tenant_a_user, enforce_csrf_checks=False)
    # Re-enable enforcement with a fresh client/session and deliberately omit the token.
    from rest_framework.test import APIClient

    csrf_client = APIClient(enforce_csrf_checks=True)
    assert csrf_client.login(username=tenant_a_user.username, password="saraise-test-password")
    response = csrf_client.post(
        "/api/v2/automation-orchestration/definitions/", {"key": "csrf", "name": "CSRF"}, format="json"
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    del client


@pytest.mark.parametrize(
    ("viewset", "actions"),
    [
        (
            DefinitionViewSet,
            {
                "list",
                "retrieve",
                "create",
                "partial_update",
                "destroy",
                "validate_graph",
                "publish",
                "clone",
                "retire",
                "nodes",
                "edges",
                "snapshot",
            },
        ),
        (NodeViewSet, {"retrieve", "partial_update", "destroy"}),
        (EdgeViewSet, {"retrieve", "partial_update", "destroy"}),
        (ScheduleViewSet, {"list", "retrieve", "create", "partial_update", "destroy", "pause", "resume", "retire"}),
        (RunViewSet, {"list", "retrieve", "create", "pause", "resume", "cancel", "retry", "task_runs", "events"}),
        (TaskRunViewSet, {"retrieve", "retry"}),
    ],
)
def test_every_action_has_explicit_access_metadata(viewset, actions) -> None:
    assert set(viewset.access_by_action) == actions
    assert all(requirement.permission and requirement.entitlement for requirement in viewset.access_by_action.values())


def test_cross_tenant_definition_identifier_is_404(tenant_a_client, tenant_b) -> None:
    definition = OrchestrationDefinition.objects.create(
        tenant_id=tenant_b.id,
        key="private",
        version=1,
        name="Private",
        created_by=uuid.uuid4(),
        updated_by=uuid.uuid4(),
    )
    response = tenant_a_client.get(f"/api/v2/automation-orchestration/definitions/{definition.id}/")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_node_catalog_exposes_real_core_descriptor(tenant_a_client) -> None:
    response = tenant_a_client.get("/api/v2/automation-orchestration/node-types/")
    assert response.status_code == status.HTTP_200_OK
    descriptors = _payload(response)
    assert any(item["key"] == "core.passthrough" for item in descriptors)
