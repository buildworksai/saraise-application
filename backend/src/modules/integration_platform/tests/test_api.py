"""Black-box contracts for the governed Integration Platform API v2."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from types import SimpleNamespace

import pytest
from django.urls import resolve
from rest_framework import status
from rest_framework.test import APIClient

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.core.api import OperationFailed, OperationResult
from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue
from src.core.encryption.service import EncryptionService

from ..adapter_registry import connector_adapter_registry
from ..adapters import AdapterDescriptor, ConnectorAdapter
from ..api import DataMappingViewSet, IntegrationViewSet, WebhookViewSet
from ..models import Integration
from ..services import (
    INBOUND_NONCE_HEADER,
    INBOUND_SIGNATURE_HEADER,
    INBOUND_TIMESTAMP_HEADER,
    MappingFailure,
    SecretOnce,
    TransformResult,
)
from .factories import (
    ConnectorFactory,
    CredentialFactory,
    DataMappingFactory,
    DeliveryFactory,
    IntegrationFactory,
    WebhookFactory,
)

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


def _data(response):
    return response.json()["data"]


def _assert_no_secret_fields(value) -> None:
    forbidden = {
        "tenant_id",
        "encrypted_value",
        "encrypted_signing_secret",
        "plaintext",
        "authorization",
    }
    if isinstance(value, dict):
        assert forbidden.isdisjoint({str(key).lower() for key in value})
        for child in value.values():
            _assert_no_secret_fields(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_secret_fields(child)


def test_all_collection_endpoints_require_authentication(api_client) -> None:
    for path in (
        "/connectors/",
        "/integrations/",
        "/integration-credentials/",
        "/webhooks/",
        "/webhook-deliveries/",
        "/data-mappings/",
        "/health/",
    ):
        response = api_client.get(f"{BASE}{path}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED, path
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_unsafe_methods_enforce_csrf(tenant_a_user, tenant_a) -> None:
    connector = ConnectorFactory()
    client = APIClient(enforce_csrf_checks=True)
    assert client.login(username=tenant_a_user.username, password="saraise-test-password")
    response = client.post(
        f"{BASE}/integrations/",
        {
            "connector_id": str(connector.id),
            "name": "CSRF blocked",
            "integration_type": "api",
            "config": {},
        },
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Integration.objects.filter(tenant_id=tenant_a.id, name="CSRF blocked").exists() is False


@pytest.mark.parametrize(
    "reason_code",
    [
        AccessReasonCode.POLICY_DENIED,
        AccessReasonCode.ENTITLEMENT_REQUIRED,
        AccessReasonCode.QUOTA_EXCEEDED,
        AccessReasonCode.DENY_DEFAULT,
    ],
)
def test_policy_entitlement_quota_and_default_denials_are_403(
    monkeypatch,
    tenant_a_client,
    reason_code,
) -> None:
    def deny(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision.deny(reason_code, "denied for test", tenant_id=uuid.UUID(str(tenant_id)))

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", deny)
    response = tenant_a_client.get(f"{BASE}/integrations/")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_connector_catalog_schema_filters_and_pagination(tenant_a_client) -> None:
    shown = ConnectorFactory(name="Open CRM", connector_type="api", module_id="crm")
    ConnectorFactory(name="Warehouse", connector_type="database", module_id="warehouse")
    response = tenant_a_client.get(
        f"{BASE}/connectors/?connector_type=api&module_id=crm&search=open&page_size=1"
    )
    assert response.status_code == status.HTTP_200_OK
    assert [item["id"] for item in _data(response)] == [str(shown.id)]
    assert response.json()["meta"]["pagination"] == {
        "count": 1,
        "page": 1,
        "page_size": 1,
        "total_pages": 1,
        "has_next": False,
        "has_previous": False,
    }
    descriptor = _data(response)[0]
    assert descriptor["is_entitled"] is True
    assert descriptor["adapter_available"] is False
    assert descriptor["entitlement_reason"] == "adapter_not_registered"

    schema = tenant_a_client.get(f"{BASE}/connectors/{shown.id}/schema/")
    assert schema.status_code == status.HTTP_200_OK
    assert _data(schema) == {
        "connector_id": str(shown.id),
        "config_schema": shown.schema,
        "credential_schema": shown.credential_schema,
    }


def test_invalid_boolean_filter_is_rejected(tenant_a_client) -> None:
    response = tenant_a_client.get(f"{BASE}/connectors/?is_active=definitely")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_integration_list_filter_search_order_and_secret_safe_detail(tenant_a_client, tenant_a, tenant_b) -> None:
    connector = ConnectorFactory()
    alpha = IntegrationFactory(
        tenant_id=tenant_a.id,
        connector=connector,
        name="Alpha API",
        description="find me",
        config={"base_url": "https://api.example.test"},
    )
    IntegrationFactory(tenant_id=tenant_a.id, connector=connector, name="Zulu API")
    IntegrationFactory(tenant_id=tenant_b.id, connector=connector, name="Other tenant")
    response = tenant_a_client.get(
        f"{BASE}/integrations/?search=find&connector_id={connector.id}&ordering=name"
    )
    assert response.status_code == status.HTTP_200_OK
    assert [item["id"] for item in _data(response)] == [str(alpha.id)]
    assert "connector_key" not in _data(response)[0]
    detail = tenant_a_client.get(f"{BASE}/integrations/{alpha.id}/")
    assert detail.status_code == status.HTTP_200_OK
    assert _data(detail)["config"] == {"base_url": "https://api.example.test"}
    _assert_no_secret_fields(_data(detail))


def test_integration_create_passes_connector_id_to_service(monkeypatch, tenant_a_client, tenant_a) -> None:
    connector = ConnectorFactory(schema={"type": "object", "properties": {}, "additionalProperties": False})
    observed = {}

    def create(tenant_id, actor_id, data):
        observed.update(data)
        return IntegrationFactory(
            tenant_id=tenant_id,
            connector=connector,
            name=data["name"],
            description=data.get("description", ""),
            config=data["config"],
            created_by=actor_id,
        )

    monkeypatch.setattr(IntegrationViewSet.service, "create", create)
    response = tenant_a_client.post(
        f"{BASE}/integrations/",
        {
            "connector_id": str(connector.id),
            "name": "Delegated",
            "integration_type": "api",
            "config": {},
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert observed["connector_id"] == connector.id
    assert "connector" not in observed
    assert Integration.objects.get(pk=_data(response)["id"]).tenant_id == tenant_a.id


@pytest.mark.parametrize("protected", ["tenant_id", "status", "created_by", "encrypted_value"])
def test_create_rejects_server_owned_and_secret_fields(tenant_a_client, protected) -> None:
    connector = ConnectorFactory(schema={"type": "object", "properties": {}, "additionalProperties": False})
    payload = {
        "connector_id": str(connector.id),
        "name": "Rejected",
        "integration_type": "api",
        "config": {},
        protected: str(uuid.uuid4()),
    }
    response = tenant_a_client.post(f"{BASE}/integrations/", payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_config_rejects_secret_sql_and_unknown_schema_fields(tenant_a_client) -> None:
    connector = ConnectorFactory(
        schema={
            "type": "object",
            "properties": {"base_url": {"type": "string"}},
            "additionalProperties": False,
        }
    )
    for config in (
        {"api_key": "not-here"},
        {"base_url": "https://example.test", "sql": "select 1"},
        {"unexpected": True},
    ):
        response = tenant_a_client.post(
            f"{BASE}/integrations/",
            {
                "connector_id": str(connector.id),
                "name": f"Rejected {uuid.uuid4()}",
                "integration_type": "api",
                "config": config,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_test_action_returns_202_only_for_persisted_job_and_outbox(monkeypatch, tenant_a_client, tenant_a) -> None:
    integration = IntegrationFactory(tenant_id=tenant_a.id)
    job = enqueue(
        tenant_a.id,
        uuid.uuid4(),
        "integration_platform.integration.test",
        {"integration_id": str(integration.id)},
        f"api-test-{uuid.uuid4()}",
    )
    monkeypatch.setattr(IntegrationViewSet.service, "request_test", lambda *args: job)
    response = tenant_a_client.post(
        f"{BASE}/integrations/{integration.id}/test/",
        {"idempotency_key": "api-test"},
        format="json",
    )
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert _data(response)["job_id"] == str(job.id)
    assert OutboxEvent.objects.filter(aggregate_type="async_job", aggregate_id=job.id).exists()

    non_durable = SimpleNamespace(
        id=uuid.uuid4(),
        status="queued",
        correlation_id="not-durable",
        created_at=job.created_at,
    )
    monkeypatch.setattr(IntegrationViewSet.service, "request_test", lambda *args: non_durable)
    failed = tenant_a_client.post(
        f"{BASE}/integrations/{integration.id}/test/",
        {"idempotency_key": "api-test-not-durable"},
        format="json",
    )
    assert failed.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.parametrize(
    ("error_status", "error_code"),
    [
        (status.HTTP_409_CONFLICT, "ILLEGAL_TRANSITION"),
        (status.HTTP_422_UNPROCESSABLE_ENTITY, "PROVIDER_REJECTED"),
        (status.HTTP_503_SERVICE_UNAVAILABLE, "CAPABILITY_UNAVAILABLE"),
    ],
)
def test_governed_operation_failures_keep_exact_status(monkeypatch, tenant_a_client, tenant_a, error_status, error_code):
    integration = IntegrationFactory(tenant_id=tenant_a.id)

    def fail(*args):
        raise OperationFailed(error_code=error_code, message="Public failure", http_status=error_status)

    monkeypatch.setattr(IntegrationViewSet.service, "request_test", fail)
    response = tenant_a_client.post(
        f"{BASE}/integrations/{integration.id}/test/",
        {"idempotency_key": str(uuid.uuid4())},
        format="json",
    )
    assert response.status_code == error_status
    assert response.json()["error"]["code"] == error_code


def test_credential_endpoints_emit_metadata_only(tenant_a_client, tenant_a) -> None:
    integration = IntegrationFactory(tenant_id=tenant_a.id)
    credential = CredentialFactory(integration=integration, plaintext="super-sensitive-value")
    listing = tenant_a_client.get(f"{BASE}/integrations/{integration.id}/credentials/")
    assert listing.status_code == status.HTTP_200_OK
    assert [item["id"] for item in _data(listing)] == [str(credential.id)]
    detail = tenant_a_client.get(f"{BASE}/integration-credentials/{credential.id}/")
    assert detail.status_code == status.HTTP_200_OK
    _assert_no_secret_fields(_data(detail))
    assert "super-sensitive-value" not in json.dumps(detail.json())


def test_webhook_create_returns_secret_once_and_read_never_replays_it(monkeypatch, tenant_a_client, tenant_a) -> None:
    secret = "one-time-signing-secret"

    def create(tenant_id, actor_id, data):
        record = WebhookFactory(
            tenant_id=tenant_id,
            created_by=actor_id,
            name=data["name"],
            direction=data["direction"],
            url=data.get("url", ""),
            events=data["events"],
        )
        return SecretOnce(record, secret)

    monkeypatch.setattr(WebhookViewSet.service, "create", create)
    response = tenant_a_client.post(
        f"{BASE}/webhooks/",
        {
            "name": "Inbound",
            "direction": "inbound",
            "events": ["integration.updated"],
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert _data(response)["signing_secret"] == secret
    assert _data(response)["shown_once"] is True
    webhook_id = _data(response)["webhook"]["id"]
    read = tenant_a_client.get(f"{BASE}/webhooks/{webhook_id}/")
    assert read.status_code == status.HTTP_200_OK
    assert secret not in json.dumps(read.json())
    _assert_no_secret_fields(_data(read))


def test_webhook_rejects_unsafe_outbound_destination(tenant_a_client) -> None:
    response = tenant_a_client.post(
        f"{BASE}/webhooks/",
        {
            "name": "Internal",
            "direction": "outbound",
            "url": "http://127.0.0.1/admin",
            "events": ["integration.updated"],
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_delivery_filters_and_detail_are_tenant_scoped(tenant_a_client, tenant_a) -> None:
    webhook = WebhookFactory(tenant_id=tenant_a.id)
    delivered = DeliveryFactory(webhook=webhook, status="delivered", response_code=204)
    DeliveryFactory(webhook=webhook, status="queued")
    response = tenant_a_client.get(
        f"{BASE}/webhook-deliveries/?webhook_id={webhook.id}&status=delivered&event={webhook.events[0]}"
    )
    assert response.status_code == status.HTTP_200_OK
    assert [item["id"] for item in _data(response)] == [str(delivered.id)]
    detail = tenant_a_client.get(f"{BASE}/webhook-deliveries/{delivered.id}/")
    assert detail.status_code == status.HTTP_200_OK
    assert _data(detail)["payload_hash"] == delivered.payload_hash


def test_mapping_validate_preview_and_invalid_transformation(monkeypatch, tenant_a_client, tenant_a) -> None:
    integration = IntegrationFactory(tenant_id=tenant_a.id)
    mapping = DataMappingFactory(
        integration=integration,
        source_field="source",
        target_field="target",
        transform={"operation": "trim", "options": {}},
    )
    validation = tenant_a_client.post(
        f"{BASE}/data-mappings/validate/",
        {
            "integration_id": str(integration.id),
            "mappings": [
                {
                    "integration_id": str(integration.id),
                    "name": "Preview",
                    "source_field": "source",
                    "target_field": "target",
                    "transform": {"operation": "trim", "options": {}},
                }
            ],
            "source_schema": {"type": "object", "properties": {"source": {"type": "string"}}},
            "target_schema": {"type": "object", "properties": {"target": {"type": "string"}}},
        },
        format="json",
    )
    assert validation.status_code == status.HTTP_200_OK
    assert _data(validation) == {"valid": True, "errors": [], "mapping_count": 1}

    result = TransformResult(
        ({"target": "value"},),
        (
            MappingFailure(
                0,
                mapping.id,
                "source",
                "target",
                "example_warning",
                "Example bounded failure",
            ),
        ),
    )
    monkeypatch.setattr(DataMappingViewSet.service, "preview", lambda *args: result)
    preview = tenant_a_client.post(
        f"{BASE}/data-mappings/preview/",
        {
            "integration_id": str(integration.id),
            "mapping_ids": [str(mapping.id)],
            "sample": {"source": " value "},
        },
        format="json",
    )
    assert preview.status_code == status.HTTP_200_OK
    assert _data(preview)["records"] == [{"target": "value"}]
    assert _data(preview)["failures"][0]["mapping_id"] == str(mapping.id)

    invalid = tenant_a_client.post(
        f"{BASE}/data-mappings/",
        {
            "integration_id": str(integration.id),
            "name": "Executable",
            "source_field": "source",
            "target_field": "target",
            "transform": {"operation": "python", "options": {"script": "pass"}},
        },
        format="json",
    )
    assert invalid.status_code == status.HTTP_400_BAD_REQUEST


def test_canonical_inbound_signature_vector_is_durable_and_replay_safe(api_client, tenant_a) -> None:
    secret = "signature-vector-secret"
    webhook = WebhookFactory(
        tenant_id=tenant_a.id,
        direction="inbound",
        url="",
        status="active",
        encrypted_signing_secret=EncryptionService.encrypt(secret),
    )
    raw_body = b'{"event":"integration.updated","record_id":"42"}'
    timestamp = str(int(time.time()))
    nonce = "vector-nonce-0001"
    canonical = f"v1.{timestamp}.{nonce}.".encode("ascii") + raw_body
    signature = f"sha256={hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()}"
    headers = {
        f"HTTP_{INBOUND_TIMESTAMP_HEADER.upper().replace('-', '_')}": timestamp,
        f"HTTP_{INBOUND_NONCE_HEADER.upper().replace('-', '_')}": nonce,
        f"HTTP_{INBOUND_SIGNATURE_HEADER.upper().replace('-', '_')}": signature,
    }
    response = api_client.generic(
        "POST",
        f"{BASE}/webhooks/inbound/{webhook.public_id}/",
        raw_body,
        content_type="application/json",
        **headers,
    )
    assert response.status_code == status.HTTP_202_ACCEPTED
    job = AsyncJob.objects.get(pk=_data(response)["job_id"])
    assert job.tenant_id == tenant_a.id
    assert job.payload["webhook_id"] == str(webhook.id)
    assert OutboxEvent.objects.filter(aggregate_type="async_job", aggregate_id=job.id).exists()

    replay = api_client.generic(
        "POST",
        f"{BASE}/webhooks/inbound/{webhook.public_id}/",
        raw_body,
        content_type="application/json",
        **headers,
    )
    assert replay.status_code == status.HTTP_409_CONFLICT
    assert replay.json()["error"]["code"] == "nonce_replayed"


def test_invalid_inbound_signature_is_401_and_creates_nothing(api_client, tenant_a) -> None:
    webhook = WebhookFactory(
        tenant_id=tenant_a.id,
        direction="inbound",
        url="",
        status="active",
    )
    before = AsyncJob.objects.count()
    response = api_client.generic(
        "POST",
        f"{BASE}/webhooks/inbound/{webhook.public_id}/",
        b"{}",
        content_type="application/json",
        HTTP_X_SARAISE_WEBHOOK_TIMESTAMP=str(int(time.time())),
        HTTP_X_SARAISE_WEBHOOK_NONCE="invalid-signature-01",
        HTTP_X_SARAISE_WEBHOOK_SIGNATURE=f"sha256={'0' * 64}",
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert AsyncJob.objects.count() == before


def test_missing_connector_adapter_health_is_explicit_503(tenant_a_client) -> None:
    connector = ConnectorFactory()
    response = tenant_a_client.get(f"{BASE}/connectors/{connector.id}/health/")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()["error"]["code"] == "CAPABILITY_UNAVAILABLE"


def test_registered_connector_health_requires_verified_state(tenant_a_client) -> None:
    class HealthyAdapter(ConnectorAdapter):
        descriptor = AdapterDescriptor("tests.api.health", "1.0", frozenset({"test"}))

        def validate_config(self, config):
            return OperationResult.succeeded(config, evidence={"validated": True})

        def test_connection(self, config, credential):
            return OperationResult.succeeded({"connected": True}, evidence={"connected": True})

        def pull(self, config, credential, cursor, limit):
            raise NotImplementedError

        def push(self, config, credential, records, idempotency_key):
            raise NotImplementedError

        def health(self):
            return OperationResult.succeeded(
                {"status": "healthy", "circuit_state": "closed"},
                evidence={"circuit_state": "closed", "provider_acknowledged": True},
            )

    connector_adapter_registry.register("tests.api.health", HealthyAdapter())
    try:
        connector = ConnectorFactory(adapter_key="tests.api.health", capabilities=["test"])
        response = tenant_a_client.get(f"{BASE}/connectors/{connector.id}/health/")
        assert response.status_code == status.HTTP_200_OK
        assert _data(response)["status"] == "healthy"
        assert _data(response)["circuit_state"] == "closed"
        assert _data(response)["adapter_registered"] is True
    finally:
        connector_adapter_registry.unregister("tests.api.health", reason="test_cleanup")


@pytest.mark.parametrize(
    ("url", "method"),
    [
        (f"{BASE}/connectors/", "post"),
        (f"{BASE}/integrations/00000000-0000-0000-0000-000000000000/", "put"),
        (f"{BASE}/integration-credentials/00000000-0000-0000-0000-000000000000/", "patch"),
        (f"{BASE}/integration-credentials/00000000-0000-0000-0000-000000000000/", "delete"),
        (f"{BASE}/webhooks/00000000-0000-0000-0000-000000000000/", "put"),
        (f"{BASE}/webhook-deliveries/00000000-0000-0000-0000-000000000000/", "delete"),
        (f"{BASE}/data-mappings/00000000-0000-0000-0000-000000000000/", "put"),
    ],
)
def test_forbidden_methods_are_not_exposed(tenant_a_client, url, method) -> None:
    response = getattr(tenant_a_client, method)(url, {}, format="json")
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


def test_every_required_route_resolves_to_the_intended_action() -> None:
    resource_id = "00000000-0000-0000-0000-000000000001"
    routes = {
        f"{BASE}/connectors/": "list",
        f"{BASE}/connectors/{resource_id}/": "retrieve",
        f"{BASE}/connectors/{resource_id}/schema/": "schema",
        f"{BASE}/connectors/{resource_id}/health/": "health",
        f"{BASE}/integrations/": "list",
        f"{BASE}/integrations/{resource_id}/": "retrieve",
        f"{BASE}/integrations/{resource_id}/activate/": "activate",
        f"{BASE}/integrations/{resource_id}/deactivate/": "deactivate",
        f"{BASE}/integrations/{resource_id}/test/": "test_connection",
        f"{BASE}/integrations/{resource_id}/sync/": "sync",
        f"{BASE}/integrations/{resource_id}/jobs/{resource_id}/": "job",
        f"{BASE}/integrations/{resource_id}/credentials/": "list",
        f"{BASE}/integration-credentials/{resource_id}/": "retrieve",
        f"{BASE}/integration-credentials/{resource_id}/rotate/": "rotate",
        f"{BASE}/integration-credentials/{resource_id}/revoke/": "revoke",
        f"{BASE}/webhooks/": "list",
        f"{BASE}/webhooks/{resource_id}/": "retrieve",
        f"{BASE}/webhooks/{resource_id}/activate/": "activate",
        f"{BASE}/webhooks/{resource_id}/deactivate/": "deactivate",
        f"{BASE}/webhooks/{resource_id}/rotate-secret/": "rotate_secret",
        f"{BASE}/webhooks/inbound/{resource_id}/": "create",
        f"{BASE}/webhook-deliveries/": "list",
        f"{BASE}/webhook-deliveries/{resource_id}/": "retrieve",
        f"{BASE}/webhook-deliveries/{resource_id}/redrive/": "redrive",
        f"{BASE}/data-mappings/": "list",
        f"{BASE}/data-mappings/{resource_id}/": "retrieve",
        f"{BASE}/data-mappings/validate/": "validate_mappings",
        f"{BASE}/data-mappings/preview/": "preview",
    }
    for url, action_name in routes.items():
        match = resolve(url)
        assert action_name in match.func.actions.values(), url
