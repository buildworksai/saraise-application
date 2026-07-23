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


@pytest.mark.parametrize("resource", ("integrations", "webhooks", "data-mappings"))
def test_user_cannot_update_or_delete_other_tenant_mutable_resources(
    tenant_a_client, tenant_b, resource
) -> None:
    if resource == "integrations":
        record = IntegrationFactory(tenant_id=tenant_b.id)
    elif resource == "webhooks":
        record = WebhookFactory(tenant_id=tenant_b.id)
    else:
        record = DataMappingFactory(
            integration=IntegrationFactory(tenant_id=tenant_b.id)
        )

    update = tenant_a_client.patch(
        f"{BASE}/{resource}/{record.id}/", {"name": "ownership takeover"}, format="json"
    )
    delete = tenant_a_client.delete(f"{BASE}/{resource}/{record.id}/")

    assert update.status_code == status.HTTP_404_NOT_FOUND
    assert delete.status_code == status.HTTP_404_NOT_FOUND
    record.refresh_from_db()
    assert record.is_deleted is False
    assert record.name != "ownership takeover"


@pytest.mark.parametrize(
    ("path", "payload"),
    (
        (
            "integrations",
            {
                "connector_id": str(uuid.uuid4()),
                "name": "Injected integration",
                "integration_type": "api",
                "config": {},
            },
        ),
        (
            "webhooks",
            {
                "name": "Injected webhook",
                "direction": "inbound",
                "events": ["test.event"],
            },
        ),
        (
            "data-mappings",
            {
                "integration_id": str(uuid.uuid4()),
                "name": "Injected mapping",
                "source_field": "source",
                "target_field": "target",
                "transform": {},
            },
        ),
    ),
)
def test_create_rejects_tenant_ownership_injection(
    tenant_a_client, tenant_b, path, payload
) -> None:
    payload["tenant_id"] = str(tenant_b.id)
    response = tenant_a_client.post(f"{BASE}/{path}/", payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
