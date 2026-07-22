"""Tenant-first service behavior and truthful operation evidence."""

import uuid

import pytest
from cryptography.fernet import Fernet

from src.core.api.results import OperationResult
from src.core.async_jobs.models import OutboxEvent

from ..adapter_registry import connector_adapter_registry
from ..adapters import AdapterDescriptor, ConnectorAdapter, PushEvidence, RecordBatch, RecordCursor
from ..services import CredentialService, DataMappingService, IntegrationPlatformError, IntegrationService
from .factories import connector_factory, integration_factory, mapping_factory

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db


class ProvenAdapter(ConnectorAdapter):
    def __init__(self, key: str, *, batch: RecordBatch | None = None):
        self.descriptor = AdapterDescriptor(key, "1.0.0", frozenset({"test", "pull", "push"}))
        self.batch = batch or RecordBatch((), source_exhausted=True, source_count=0)

    def validate_config(self, config):
        return OperationResult.succeeded(dict(config), evidence={"validated": True})

    def test_connection(self, config, credential):
        return OperationResult.succeeded({"connected": True}, evidence={"provider_ack": "ok"})

    def pull(self, config, credential, cursor, limit):
        return OperationResult.succeeded(self.batch, evidence={"source_count": self.batch.source_count})

    def push(self, config, credential, records, idempotency_key):
        evidence = PushEvidence(len(records), 0, "provider-1")
        return OperationResult.succeeded(evidence, evidence={"accepted_count": len(records)})

    def health(self):
        return OperationResult.succeeded({"status": "healthy"}, evidence={"probe": "real"})


class AllowQuota:
    class Result:
        allowed = True

    def consume(self, tenant_id, resource, cost=1):
        return self.Result()


@pytest.fixture(autouse=True)
def domain_setup(settings):
    settings.SARAISE_ENCRYPTION_KEY = Fernet.generate_key().decode()
    connector_adapter_registry.clear()
    yield
    connector_adapter_registry.clear()


def test_create_test_and_outbox_evidence():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    connector = connector_factory(schema={"type": "object", "additionalProperties": False})
    connector_adapter_registry.register(connector.adapter_key, ProvenAdapter(connector.adapter_key))
    service = IntegrationService(quotas=AllowQuota())
    integration = service.create(tenant, actor, {"connector": connector, "name": "Accounting", "config": {}})
    job = service.request_test(tenant, actor, integration.id, "test-once")
    assert job.payload == {"integration_id": str(integration.id)}
    assert OutboxEvent.objects.for_tenant(tenant).filter(aggregate_id=job.id).exists()
    result = service.execute_test(tenant, job)
    assert result.status == "succeeded"
    integration.refresh_from_db()
    assert integration.status == "active"


def test_missing_adapter_is_explicitly_unavailable():
    connector = connector_factory()
    service = IntegrationService()
    with pytest.raises(Exception) as exc:
        service.create(uuid.uuid4(), uuid.uuid4(), {"connector": connector, "name": "Unavailable", "config": {}})
    assert getattr(exc.value, "status_code", None) == 503


def test_credentials_are_encrypted_metadata_only_and_rotate_atomically():
    integration = integration_factory()
    service = CredentialService()
    old = service.create(integration.tenant_id, integration.created_by, integration.id, "api_key", "clear-secret")
    assert "clear-secret" not in old.encrypted_value
    assert list(service.list_metadata(integration.tenant_id, integration.id))[0].display_hint.endswith("cret")
    new = service.rotate(integration.tenant_id, integration.created_by, old.id, "next-secret", "rotate-once")
    old.refresh_from_db()
    assert old.status == "revoked" and new.version == 2
    assert service.rotate(integration.tenant_id, integration.created_by, old.id, "ignored", "rotate-once").id == new.id


def test_mapping_preview_is_deterministic_and_reports_per_record_failures():
    integration = integration_factory()
    mapping = mapping_factory(
        integration,
        source_field="name",
        target_field="display_name",
        transform={"operations": [{"operation": "trim", "options": {}}, {"operation": "string_case", "options": {"case": "upper"}}]},
    )
    result = DataMappingService().preview(
        integration.tenant_id,
        integration.id,
        [mapping.id],
        [{"name": "  alpha "}, {"name": " beta"}],
    )
    assert result.records == ({"display_name": "ALPHA"}, {"display_name": "BETA"})
    assert result.failures == ()


def test_zero_source_batch_is_a_proven_success_without_sink_counts():
    connector = connector_factory()
    connector_adapter_registry.register(connector.adapter_key, ProvenAdapter(connector.adapter_key))
    integration = integration_factory(connector=connector, status="active")
    service = IntegrationService(quotas=AllowQuota())
    job = service.request_sync(integration.tenant_id, integration.created_by, integration.id, "pull", [], "sync-zero")
    result = service.execute_sync(integration.tenant_id, job)
    assert result.status == "succeeded"
    assert result.evidence["records_read"] == result.evidence["records_written"] == 0


def test_push_without_governed_source_fails_instead_of_fabricating_records():
    connector = connector_factory()
    connector_adapter_registry.register(connector.adapter_key, ProvenAdapter(connector.adapter_key))
    integration = integration_factory(connector=connector, status="active")
    service = IntegrationService(quotas=AllowQuota())
    job = service.request_sync(integration.tenant_id, integration.created_by, integration.id, "push", [], "sync-push")
    result = service.execute_sync(integration.tenant_id, job)
    assert result.status == "failed" and result.error_code == "sync_source_unavailable"
