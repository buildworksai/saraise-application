"""Tenant isolation at the v2 HTTP and worker boundaries."""

from __future__ import annotations

import uuid

import pytest
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.core.testing.tenant_contract import TenantIsolationContract

from ..models import OrchestrationDefinition

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def allow_access_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    def allow(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="allowed for isolation contract",
            tenant_id=uuid.UUID(str(tenant_id)),
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", allow)


class TestDefinitionIsolation(TenantIsolationContract):
    model = OrchestrationDefinition
    list_url = "/api/v2/automation-orchestration/definitions/"
    detail_url_template = "/api/v2/automation-orchestration/definitions/{pk}/"
    create_payload = {"key": "spoof-attempt", "name": "Spoof attempt"}
    update_payload = {"name": "Cross-tenant mutation"}
    read_denial_statuses = frozenset({status.HTTP_404_NOT_FOUND})

    @pytest.fixture(autouse=True)
    def isolation_context(self, tenant_a_client, tenant_a, tenant_b):
        actor = uuid.uuid4()
        self.client = tenant_a_client
        self.tenant_a_row = OrchestrationDefinition.objects.create(
            tenant_id=tenant_a.id, key="tenant-a", version=1, name="Tenant A", created_by=actor, updated_by=actor
        )
        self.tenant_b_row = OrchestrationDefinition.objects.create(
            tenant_id=tenant_b.id, key="tenant-b", version=1, name="Tenant B", created_by=actor, updated_by=actor
        )

    def get_list_items(self, response):
        return response.json()["data"]


def test_cross_tenant_lifecycle_actions_are_404_and_unchanged(tenant_a_client, tenant_b) -> None:
    actor = uuid.uuid4()
    target = OrchestrationDefinition.objects.create(
        tenant_id=tenant_b.id,
        key="tenant-b-action",
        version=1,
        name="Tenant B action",
        created_by=actor,
        updated_by=actor,
    )
    before = (target.status, target.version, target.is_deleted, target.updated_at)
    for suffix, payload in (
        ("validate", {}),
        ("publish", {"transition_key": "publish"}),
        ("clone", {}),
        ("retire", {"transition_key": "retire"}),
    ):
        response = tenant_a_client.post(
            f"/api/v2/automation-orchestration/definitions/{target.id}/{suffix}/", payload, format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    target.refresh_from_db()
    assert (target.status, target.version, target.is_deleted, target.updated_at) == before


def test_cross_tenant_run_initiation_does_not_create_history(tenant_a_client, tenant_b) -> None:
    definition = OrchestrationDefinition.objects.create(
        tenant_id=tenant_b.id,
        key="tenant-b-run",
        version=1,
        name="Tenant B run",
        status="published",
        is_current=True,
        created_by=uuid.uuid4(),
        updated_by=uuid.uuid4(),
    )
    response = tenant_a_client.post(
        "/api/v2/automation-orchestration/runs/",
        {
            "definition_id": str(definition.id),
            "input": {},
            "idempotency_key": "cross-tenant-run",
            "trigger_type": "manual",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert definition.runs.count() == 0
