"""Tenant-safe factories for integration-platform domain and API tests."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from src.core.encryption.service import EncryptionService

from ..models import Connector, DataMapping, Integration, IntegrationCredential, Webhook, WebhookDelivery


def connector_factory(**overrides: Any) -> Connector:
    identity = uuid.uuid4().hex[:10]
    values: dict[str, Any] = {
        "key": f"connector-{identity}",
        "name": f"Connector {identity}",
        "connector_type": "api",
        "adapter_key": f"tests.integration_platform.{identity}",
        "version": "1.0.0",
        "schema": {"type": "object", "properties": {"base_url": {"type": "string", "format": "uri"}}, "additionalProperties": False},
        "credential_schema": {"type": "object", "properties": {"api_key": {"type": "string", "writeOnly": True}}, "additionalProperties": False},
        "capabilities": ["test", "pull", "push"],
    }
    values.update(overrides)
    return Connector.objects.create(**values)


def integration_factory(**overrides: Any) -> Integration:
    connector = overrides.pop("connector", None) or connector_factory()
    values: dict[str, Any] = {
        "tenant_id": uuid.uuid4(),
        "connector": connector,
        "name": f"Integration {uuid.uuid4().hex[:8]}",
        "integration_type": connector.connector_type,
        "config": {},
        "created_by": uuid.uuid4(),
    }
    values.update(overrides)
    return Integration.objects.create(**values)


def credential_factory(integration: Integration | None = None, **overrides: Any) -> IntegrationCredential:
    integration = integration or integration_factory()
    plaintext = str(overrides.pop("plaintext", "test-credential-value"))
    values: dict[str, Any] = {
        "tenant_id": integration.tenant_id,
        "integration": integration,
        "credential_type": "api_key",
        "encrypted_value": EncryptionService.encrypt(plaintext),
        "display_hint": f"••••{plaintext[-4:]}",
        "created_by": integration.created_by,
    }
    values.update(overrides)
    return IntegrationCredential.objects.create(**values)


def webhook_factory(**overrides: Any) -> Webhook:
    direction = overrides.get("direction", "outbound")
    values: dict[str, Any] = {
        "tenant_id": uuid.uuid4(),
        "name": f"Webhook {uuid.uuid4().hex[:8]}",
        "direction": direction,
        "url": "https://webhooks.example.test/events" if direction == "outbound" else "",
        "events": ["integration.updated"],
        "encrypted_signing_secret": EncryptionService.encrypt("test-signing-secret"),
        "created_by": uuid.uuid4(),
    }
    values.update(overrides)
    return Webhook.objects.create(**values)


def delivery_factory(webhook: Webhook | None = None, **overrides: Any) -> WebhookDelivery:
    webhook = webhook or webhook_factory()
    payload = overrides.pop("payload", {"record_id": "example"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    values: dict[str, Any] = {
        "tenant_id": webhook.tenant_id,
        "webhook": webhook,
        "event": webhook.events[0],
        "payload": payload,
        "payload_hash": hashlib.sha256(canonical).hexdigest(),
        "idempotency_key": f"delivery-{uuid.uuid4()}",
        "max_attempts": webhook.max_attempts,
        "job_id": uuid.uuid4(),
        "correlation_id": uuid.uuid4().hex,
    }
    values.update(overrides)
    return WebhookDelivery.objects.create(**values)


def mapping_factory(integration: Integration | None = None, **overrides: Any) -> DataMapping:
    integration = integration or integration_factory()
    identity = uuid.uuid4().hex[:8]
    values: dict[str, Any] = {
        "tenant_id": integration.tenant_id,
        "integration": integration,
        "name": f"Mapping {identity}",
        "source_field": f"source_{identity}",
        "target_field": f"target_{identity}",
        "transform": {"operation": "trim", "options": {}},
        "created_by": integration.created_by,
    }
    values.update(overrides)
    return DataMapping.objects.create(**values)


# Class-like aliases keep serializer/API tests terse without introducing a
# factory-boy dependency into this module's public test extension surface.
ConnectorFactory = connector_factory
IntegrationFactory = integration_factory
CredentialFactory = credential_factory
WebhookFactory = webhook_factory
DeliveryFactory = delivery_factory
DataMappingFactory = mapping_factory


__all__ = [
    "ConnectorFactory", "CredentialFactory", "DataMappingFactory", "DeliveryFactory", "IntegrationFactory",
    "WebhookFactory", "connector_factory", "credential_factory", "delivery_factory", "integration_factory",
    "mapping_factory", "webhook_factory",
]
