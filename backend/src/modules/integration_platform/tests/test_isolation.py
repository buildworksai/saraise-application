"""Black-box tenant-isolation contracts for Integration Platform API v2."""

import uuid

import pytest
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessReasonCode

from .factories import ConnectorFactory, DataMappingFactory, IntegrationFactory, WebhookFactory

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db

BASE = "/api/v2/integration-platform"


@pytest.fixture(autouse=True)
def allow_access_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
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


def _ids(response) -> set[str]:
    return {item["id"] for item in response.json()["data"]}


def test_user_cannot_list_other_tenant_integrations(tenant_a_client, tenant_a, tenant_b) -> None:
    connector = ConnectorFactory()
    integration_a = IntegrationFactory(tenant_id=tenant_a.id, connector=connector)
    integration_b = IntegrationFactory(tenant_id=tenant_b.id, connector=connector)

    response = tenant_a_client.get(f"{BASE}/integrations/")

    assert response.status_code == status.HTTP_200_OK
    assert str(integration_a.id) in _ids(response)
    assert str(integration_b.id) not in _ids(response)


def test_user_cannot_get_other_tenant_integration_by_id(tenant_a_client, tenant_b) -> None:
    integration_b = IntegrationFactory(tenant_id=tenant_b.id)

    response = tenant_a_client.get(f"{BASE}/integrations/{integration_b.id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_user_cannot_list_other_tenant_webhooks(tenant_a_client, tenant_a, tenant_b) -> None:
    webhook_a = WebhookFactory(tenant_id=tenant_a.id)
    webhook_b = WebhookFactory(tenant_id=tenant_b.id)

    response = tenant_a_client.get(f"{BASE}/webhooks/")

    assert response.status_code == status.HTTP_200_OK
    assert str(webhook_a.id) in _ids(response)
    assert str(webhook_b.id) not in _ids(response)


def test_user_cannot_list_other_tenant_data_mappings(tenant_a_client, tenant_a, tenant_b) -> None:
    connector = ConnectorFactory()
    integration_a = IntegrationFactory(tenant_id=tenant_a.id, connector=connector)
    integration_b = IntegrationFactory(tenant_id=tenant_b.id, connector=connector)
    mapping_a = DataMappingFactory(integration=integration_a)
    mapping_b = DataMappingFactory(integration=integration_b)

    response = tenant_a_client.get(f"{BASE}/data-mappings/")

    assert response.status_code == status.HTTP_200_OK
    assert str(mapping_a.id) in _ids(response)
    assert str(mapping_b.id) not in _ids(response)
