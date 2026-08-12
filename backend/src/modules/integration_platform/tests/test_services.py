"""Tenant-first service behavior and truthful operation evidence."""

import hashlib
import hmac
import json
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from django.core.cache import cache
from django.utils import timezone

from src.core.api.results import OperationFailed, OperationResult
from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue

from ..adapter_registry import connector_adapter_registry
from ..adapters import AdapterDescriptor, ConnectorAdapter, PushEvidence, RecordBatch
from ..configuration import default_configuration
from ..models import ConnectorAccessPolicy, CredentialStatus, DeliveryStatus, WebhookDirection, WebhookStatus
from ..services import (
    INBOUND_NONCE_HEADER,
    INBOUND_SIGNATURE_HEADER,
    INBOUND_SIGNATURE_VERSION,
    INBOUND_TIMESTAMP_HEADER,
    ConfigurationService,
    ConnectorService,
    CredentialService,
    DataMappingService,
    IntegrationService,
    WebhookDeliveryWorker,
    WebhookService,
    _redact,
    _safe_mapping,
    _uuid,
    durable_job_state,
)
from ..state_machines import DELIVERY_STATE_MACHINE, WEBHOOK_STATE_MACHINE
from .factories import (
    connector_factory,
    credential_factory,
    delivery_factory,
    integration_factory,
    mapping_factory,
    webhook_factory,
)

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


class DenyEntitlement:
    def check(self, tenant_id, entitlement):
        return SimpleNamespace(entitled=False)


class RaisingEntitlement:
    def check(self, tenant_id, entitlement):
        raise RuntimeError("entitlement store down")


class PersistingPullAdapter(ProvenAdapter):
    def __init__(self, key: str):
        super().__init__(
            key,
            batch=RecordBatch(({"name": " alpha "}, {"name": "beta"}), source_exhausted=True, source_count=2),
        )

    def pull(self, config, credential, cursor, limit):
        del config, credential, cursor
        return OperationResult.succeeded(self.batch, evidence={"persisted_count": min(limit, self.batch.source_count)})


class InvalidContractAdapter(ProvenAdapter):
    def validate_config(self, config):
        del config
        return {"invalid": "contract"}

    def health(self):
        return {"status": "not-an-operation-result"}


class NonMappingValidationAdapter(ProvenAdapter):
    def validate_config(self, config):
        del config
        return OperationResult.succeeded(["not", "a", "mapping"], evidence={"validated": False})


class FailingTestAdapter(ProvenAdapter):
    def test_connection(self, config, credential):
        del config, credential
        raise TimeoutError("provider unavailable")


class InvalidPullAdapter(ProvenAdapter):
    def pull(self, config, credential, cursor, limit):
        del config, credential, cursor, limit
        return {"invalid": "record batch"}


class ResponseClient:
    def __init__(self, status_code):
        self.status_code = status_code
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return SimpleNamespace(status_code=self.status_code)


class RaisingClient:
    def post(self, *args, **kwargs):
        del args, kwargs
        raise TimeoutError("provider timeout")


@pytest.fixture(autouse=True)
def domain_setup(settings):
    settings.SARAISE_ENCRYPTION_KEY = Fernet.generate_key().decode()
    connector_adapter_registry.clear()
    cache.clear()
    yield
    cache.clear()
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


def test_connector_catalog_filters_entitlements_and_adapter_contracts():
    tenant = uuid.uuid4()
    shown = connector_factory(name="CRM", connector_type="api", module_id="crm")
    hidden = connector_factory(
        name="Paid",
        access_policy=ConnectorAccessPolicy.ENTITLEMENT_REQUIRED,
        required_entitlement="paid.integration",
    )
    connector_adapter_registry.register(shown.adapter_key, ProvenAdapter(shown.adapter_key))

    service = ConnectorService(entitlements=DenyEntitlement())
    descriptors = service.list_connectors(tenant, {"search": "crm", "connector_type": "api", "module_id": "crm"})
    assert [item["id"] for item in descriptors] == [shown.id]
    assert descriptors[0]["available"] is True
    assert service.get_schema(tenant, shown.id)["config_schema"] == shown.schema
    assert service.adapter_health(tenant, shown.id).status == "succeeded"
    with pytest.raises(Exception) as exc:
        service.get_connector(tenant, hidden.id)
    assert getattr(exc.value, "status_code", None) == 404

    invalid = connector_factory()
    connector_adapter_registry.register(invalid.adapter_key, InvalidContractAdapter(invalid.adapter_key))
    assert service.adapter_health(tenant, invalid.id).status == "unavailable"


def test_connector_entitlement_store_failure_is_fail_closed():
    connector = connector_factory(
        access_policy=ConnectorAccessPolicy.ENTITLEMENT_REQUIRED,
        required_entitlement="paid.integration",
    )
    service = ConnectorService(entitlements=RaisingEntitlement())
    with pytest.raises(Exception) as exc:
        service.list_connectors(uuid.uuid4())
    assert getattr(exc.value, "status_code", None) == 503
    assert connector.required_entitlement == "paid.integration"


def test_validation_helpers_reject_invalid_shapes_and_redact_nested_secrets():
    tenant = uuid.uuid4()
    with pytest.raises(Exception) as invalid_uuid:
        _uuid("not-a-uuid", "tenant_id")
    assert getattr(invalid_uuid.value, "error_code", None) == "invalid_uuid"

    with pytest.raises(Exception) as not_mapping:
        _safe_mapping(tenant, ["not", "an", "object"], "config")
    assert getattr(not_mapping.value, "error_code", None) == "validation_error"

    with pytest.raises(Exception) as unsafe:
        _safe_mapping(tenant, {"nested": [{"api-key": "clear"}]}, "config")
    assert getattr(unsafe.value, "error_code", None) == "secret_in_config"

    redacted = _redact({"items": [{"access_token": "clear"}, {"name": "public"}]}, frozenset({"access_token"}))
    assert redacted == {"items": [{"access_token": "[REDACTED]"}, {"name": "public"}]}


def test_connector_policy_and_lookup_fail_closed_paths():
    malformed = connector_factory(access_policy="tenant_scoped", required_entitlement="")
    inactive = connector_factory(is_active=False)
    service = ConnectorService()

    with pytest.raises(Exception) as policy_exc:
        service.list_connectors(uuid.uuid4(), {"is_active": True})
    assert getattr(policy_exc.value, "error_code", None) == "CAPABILITY_UNAVAILABLE"

    with pytest.raises(Exception):
        service.get_connector(uuid.uuid4(), inactive.id)

    hidden = connector_factory(
        access_policy=ConnectorAccessPolicy.ENTITLEMENT_REQUIRED,
        required_entitlement="paid.integration",
    )
    with pytest.raises(Exception) as entitlement_exc:
        ConnectorService(entitlements=DenyEntitlement()).get_connector(uuid.uuid4(), hidden.id)
    assert getattr(entitlement_exc.value, "status_code", None) == 404
    assert malformed.access_policy == "tenant_scoped"


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


def test_credentials_revoke_expiry_json_and_invalid_rotation_paths():
    integration = integration_factory()
    service = CredentialService()
    credential = service.create(
        integration.tenant_id,
        integration.created_by,
        integration.id,
        "oauth_token",
        {"access_token": "clear-json-token"},
        timezone.now() - timedelta(minutes=1),
    )
    with pytest.raises(Exception) as exc:
        service.resolve_active(integration.tenant_id, integration.id, "oauth_token")
    credential.refresh_from_db()
    assert getattr(exc.value, "error_code", None) == "credential_expired"
    assert credential.status == CredentialStatus.EXPIRED

    active = service.create(integration.tenant_id, integration.created_by, integration.id, "api_key", "revoke-secret")
    revoked = service.revoke(integration.tenant_id, integration.created_by, active.id, "revoke-once")
    assert revoked.status == CredentialStatus.REVOKED
    with pytest.raises(Exception) as duplicate_exc:
        service.create(integration.tenant_id, integration.created_by, integration.id, "certificate", "")
    assert getattr(duplicate_exc.value, "error_code", None) == "validation_error"
    with pytest.raises(Exception) as unsupported_exc:
        service.create(integration.tenant_id, integration.created_by, integration.id, "unsupported", "x")
    assert getattr(unsupported_exc.value, "error_code", None) == "validation_error"


def test_credential_plaintext_and_resolution_fail_closed_paths(monkeypatch):
    integration = integration_factory()
    service = CredentialService()

    with pytest.raises(Exception) as json_exc:
        service._plaintext({"not-json-serializable"}, 64)
    assert getattr(json_exc.value, "error_code", None) == "validation_error"

    with pytest.raises(Exception) as length_exc:
        service._plaintext("cleartext", 4)
    assert getattr(length_exc.value, "error_code", None) == "validation_error"

    with pytest.raises(Exception) as missing_exc:
        service.resolve_active(integration.tenant_id, integration.id, "api_key")
    assert getattr(missing_exc.value, "error_code", None) == "credential_missing"

    credential_factory(integration)
    monkeypatch.setattr(
        "src.modules.integration_platform.services.EncryptionService.decrypt",
        lambda encrypted: (_ for _ in ()).throw(RuntimeError("kms unavailable")),
    )
    with pytest.raises(Exception) as decrypt_exc:
        service.resolve_active(integration.tenant_id, integration.id, "api_key")
    assert getattr(decrypt_exc.value, "error_code", None) == "credential_decryption_failed"


def test_mapping_preview_is_deterministic_and_reports_per_record_failures():
    integration = integration_factory()
    mapping = mapping_factory(
        integration,
        source_field="name",
        target_field="display_name",
        transform={
            "operations": [
                {"operation": "trim", "options": {}},
                {"operation": "string_case", "options": {"case": "upper"}},
            ]
        },
    )
    result = DataMappingService().preview(
        integration.tenant_id,
        integration.id,
        [mapping.id],
        [{"name": "  alpha "}, {"name": " beta"}],
    )
    assert result.records == ({"display_name": "ALPHA"}, {"display_name": "BETA"})
    assert result.failures == ()


def test_mapping_create_update_validate_delete_and_failure_evidence():
    integration = integration_factory()
    service = DataMappingService()
    mapping = service.create(
        integration.tenant_id,
        integration.created_by,
        integration.id,
        {
            "name": "Account name",
            "source_field": "name",
            "target_field": "display_name",
            "transform": {"operation": "trim", "options": {}},
            "is_required": True,
        },
    )
    updated = service.update(integration.tenant_id, integration.created_by, mapping.id, {"position": 2})
    assert updated.position == 2
    with pytest.raises(Exception) as immutable_exc:
        service.update(integration.tenant_id, integration.created_by, mapping.id, {"integration": integration.id})
    assert getattr(immutable_exc.value, "error_code", None) == "immutable_field"

    invalid = service.validate(
        integration.tenant_id,
        integration.id,
        [
            mapping,
            {
                "source_field": "unknown",
                "target_field": "display_name",
                "transform": {"operation": "not_registered", "options": {}},
            },
        ],
        {"type": "object", "properties": {"name": {"type": "string"}}},
        {"type": "object", "properties": {"display_name": {"type": "string"}}},
    )
    assert invalid["valid"] is False and invalid["error_count" if "error_count" in invalid else "mapping_count"]
    preview = service.preview(integration.tenant_id, integration.id, [mapping.id], [{"other": "missing"}])
    assert preview.records == ()
    assert preview.failures[0].code == "required_value_missing"
    service.soft_delete(integration.tenant_id, integration.created_by, mapping.id)
    with pytest.raises(Exception):
        service.preview(integration.tenant_id, integration.id, [mapping.id], [{"name": "Acme"}])


def test_zero_source_batch_is_a_proven_success_without_sink_counts():
    connector = connector_factory()
    connector_adapter_registry.register(connector.adapter_key, ProvenAdapter(connector.adapter_key))
    integration = integration_factory(connector=connector, status="active")
    service = IntegrationService(quotas=AllowQuota())
    job = service.request_sync(integration.tenant_id, integration.created_by, integration.id, "pull", [], "sync-zero")
    result = service.execute_sync(integration.tenant_id, job)
    assert result.status == "succeeded"
    assert result.evidence["records_read"] == result.evidence["records_written"] == 0


def test_sync_pull_requires_sink_evidence_and_succeeds_when_persisted():
    connector = connector_factory()
    connector_adapter_registry.register(connector.adapter_key, PersistingPullAdapter(connector.adapter_key))
    integration = integration_factory(connector=connector, status="active")
    mapping = mapping_factory(
        integration,
        source_field="name",
        target_field="display_name",
        transform={"operation": "trim", "options": {}},
    )
    service = IntegrationService(quotas=AllowQuota())
    job = service.request_sync(
        integration.tenant_id,
        integration.created_by,
        integration.id,
        "pull",
        [mapping.id],
        "p1",
    )
    result = service.execute_sync(integration.tenant_id, job)
    assert result.status == "succeeded"
    assert result.evidence["records_written"] == 2

    connector_adapter_registry.clear()
    connector_adapter_registry.register(
        connector.adapter_key,
        ProvenAdapter(
            connector.adapter_key,
            batch=RecordBatch(({"name": "x"},), source_exhausted=True, source_count=1),
        ),
    )
    failed_job = service.request_sync(
        integration.tenant_id, integration.created_by, integration.id, "pull", [mapping.id], "p2"
    )
    failed = service.execute_sync(integration.tenant_id, failed_job)
    assert failed.status == "failed"
    assert failed.error_code == "sync_sink_unavailable"


def test_push_without_governed_source_fails_instead_of_fabricating_records():
    connector = connector_factory()
    connector_adapter_registry.register(connector.adapter_key, ProvenAdapter(connector.adapter_key))
    integration = integration_factory(connector=connector, status="active")
    service = IntegrationService(quotas=AllowQuota())
    job = service.request_sync(integration.tenant_id, integration.created_by, integration.id, "push", [], "sync-push")
    result = service.execute_sync(integration.tenant_id, job)
    assert result.status == "failed" and result.error_code == "sync_source_unavailable"


def test_integration_update_delete_and_invalid_request_paths():
    connector = connector_factory(
        schema={
            "type": "object",
            "properties": {"base_url": {"type": "string"}},
            "additionalProperties": False,
        }
    )
    connector_adapter_registry.register(connector.adapter_key, ProvenAdapter(connector.adapter_key))
    service = IntegrationService(quotas=AllowQuota())
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    integration = service.create(
        tenant,
        actor,
        {"connector": connector, "name": "ERP", "config": {"base_url": "https://api.example.test"}},
    )
    updated = service.update(tenant, actor, integration.id, {"name": "ERP updated", "config": {}})
    assert updated.name == "ERP updated"
    with pytest.raises(Exception) as immutable_exc:
        service.update(tenant, actor, integration.id, {"connector_id": connector.id})
    assert getattr(immutable_exc.value, "error_code", None) == "immutable_field"
    with pytest.raises(Exception) as activate_exc:
        service.activate(tenant, actor, integration.id, "activate-before-test")
    assert getattr(activate_exc.value, "error_code", None) == "successful_test_required"
    with pytest.raises(Exception) as duplicate_exc:
        service.request_sync(tenant, actor, integration.id, "pull", [uuid.uuid4(), uuid.uuid4()], "inactive")
    assert getattr(duplicate_exc.value, "error_code", None) == "invalid_state"
    integration.status = "inactive"
    integration.save(update_fields=("status", "updated_at"))
    service.soft_delete(tenant, actor, integration.id)
    integration.refresh_from_db()
    assert integration.is_deleted is True


def test_integration_create_adapter_and_job_fail_closed_paths():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    connector = connector_factory(
        schema={"type": "object", "properties": {"base_url": {"type": "string"}}, "additionalProperties": False}
    )
    connector_adapter_registry.register(connector.adapter_key, ProvenAdapter(connector.adapter_key))
    service = IntegrationService(quotas=AllowQuota())

    with pytest.raises(Exception) as type_exc:
        service.create(tenant, actor, {"connector": connector, "name": "ERP", "integration_type": "file", "config": {}})
    assert getattr(type_exc.value, "error_code", None) == "connector_type_mismatch"

    with pytest.raises(Exception) as schema_exc:
        service.create(tenant, actor, {"connector": connector, "name": "ERP", "config": {"extra": "blocked"}})
    assert getattr(schema_exc.value, "error_code", None) == "schema_validation_failed"

    invalid = connector_factory(schema={"type": "object", "additionalProperties": False})
    connector_adapter_registry.register(invalid.adapter_key, NonMappingValidationAdapter(invalid.adapter_key))
    with pytest.raises(Exception) as adapter_exc:
        service.create(tenant, actor, {"connector": invalid, "name": "Invalid adapter", "config": {}})
    assert getattr(adapter_exc.value, "error_code", None) == "invalid_adapter_result"

    entitled = connector_factory(
        access_policy=ConnectorAccessPolicy.ENTITLEMENT_REQUIRED,
        required_entitlement="paid.integration",
    )
    connector_adapter_registry.register(entitled.adapter_key, ProvenAdapter(entitled.adapter_key))
    with pytest.raises(Exception) as entitlement_exc:
        IntegrationService(entitlements=DenyEntitlement()).create(
            tenant, actor, {"connector": entitled, "name": "Paid", "config": {}}
        )
    assert getattr(entitlement_exc.value, "error_code", None) == "entitlement_required"


def test_integration_workers_reject_stale_invalid_and_failed_adapter_results():
    connector = connector_factory(schema={"type": "object", "additionalProperties": False})
    connector_adapter_registry.register(connector.adapter_key, FailingTestAdapter(connector.adapter_key))
    integration = integration_factory(connector=connector, status="testing")
    service = IntegrationService(quotas=AllowQuota())

    wrong = AsyncJob.objects.create(
        tenant_id=integration.tenant_id,
        command="integration_platform.not-test",
        payload={"integration_id": str(integration.id)},
        idempotency_key="wrong-test-job",
    )
    with pytest.raises(Exception):
        service.execute_test(integration.tenant_id, wrong)

    stale = enqueue(
        integration.tenant_id,
        integration.created_by,
        service.TEST_COMMAND,
        {"integration_id": str(integration.id)},
        "stale-test-job",
    )
    with pytest.raises(Exception) as stale_exc:
        service.execute_test(integration.tenant_id, stale)
    assert getattr(stale_exc.value, "error_code", None) == "stale_job"

    current_integration = integration_factory(connector=connector, status="inactive")
    current = service.request_test(
        current_integration.tenant_id,
        current_integration.created_by,
        current_integration.id,
        "failing-test",
    )
    failed = service.execute_test(current_integration.tenant_id, current)
    assert failed.status == "failed"
    assert failed.error_code == "dependency_failure"

    connector_adapter_registry.clear()
    connector_adapter_registry.register(connector.adapter_key, InvalidPullAdapter(connector.adapter_key))
    sync_integration = integration_factory(connector=connector, status="active")
    job = service.request_sync(
        sync_integration.tenant_id,
        sync_integration.created_by,
        sync_integration.id,
        "pull",
        [],
        "invalid-pull",
    )
    with pytest.raises(Exception) as pull_exc:
        service.execute_sync(sync_integration.tenant_id, job)
    assert getattr(pull_exc.value, "error_code", None) == "invalid_adapter_result"


def test_configuration_save_preview_rollback_and_audit_evidence():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    service = ConfigurationService()
    document = default_configuration()
    document["jobs"]["poll_after_ms"] = 2500

    preview = service.preview(tenant, document)
    assert preview["valid"] is True
    assert "jobs" in preview["changed_sections"]

    saved = service.save(tenant, actor, document, correlation_id="corr-integration-save")
    assert saved["version"] == 1
    assert saved["document"]["jobs"]["poll_after_ms"] == 2500
    assert service.versions(tenant).count() == 1
    assert service.audits(tenant).get().correlation_id == "corr-integration-save"
    assert OutboxEvent.objects.for_tenant(tenant).filter(event_type="configuration.update").exists()

    replacement = default_configuration()
    replacement["jobs"]["poll_after_ms"] = 3000
    service.save(tenant, actor, replacement, correlation_id="corr-integration-replace")
    rolled_back = service.rollback(tenant, actor, 1, correlation_id="corr-integration-rollback")
    assert rolled_back["version"] == 3
    assert rolled_back["document"]["jobs"]["poll_after_ms"] == 2500


def test_configuration_rejects_invalid_document_and_missing_rollback_version():
    service = ConfigurationService()
    with pytest.raises(Exception):
        service.preview(uuid.uuid4(), {"schema_version": 999})
    with pytest.raises(Exception) as exc:
        service.rollback(uuid.uuid4(), uuid.uuid4(), 999, correlation_id="corr-missing")
    assert getattr(exc.value, "status_code", None) == 404


def test_configuration_save_requires_correlation_identifier():
    with pytest.raises(Exception) as exc:
        ConfigurationService().save(uuid.uuid4(), uuid.uuid4(), default_configuration())
    assert getattr(exc.value, "error_code", None) == "correlation_unavailable"


def test_durable_job_state_requires_supported_operation_and_bounds_progress():
    tenant = uuid.uuid4()
    job = AsyncJob.objects.create(
        tenant_id=tenant,
        command="integration_platform.sync",
        payload={},
        idempotency_key="sync-job-state",
        status="succeeded",
        result={"progress_percent": 999, "records_read": 4, "records_written": 3},
    )
    OutboxEvent.objects.create(
        tenant_id=tenant,
        aggregate_type="async_job",
        aggregate_id=job.id,
        event_type="async_job.enqueued",
        payload={},
    )

    state = durable_job_state(job)
    assert state["operation"] == "integration_sync"
    assert state["progress_percent"] == 100
    assert state["evidence"] == {"records_read": 4, "records_written": 3}

    unsupported = AsyncJob.objects.create(
        tenant_id=tenant,
        command="integration_platform.unknown",
        payload={},
        idempotency_key="unknown-job-state",
        status="queued",
    )
    OutboxEvent.objects.create(
        tenant_id=tenant,
        aggregate_type="async_job",
        aggregate_id=unsupported.id,
        event_type="async_job.enqueued",
        payload={},
    )
    with pytest.raises(OperationFailed) as exc:
        durable_job_state(unsupported)
    assert exc.value.error_code == "JOB_STATE_UNAVAILABLE"


def test_webhook_inbound_signature_receive_replay_and_secret_redaction():
    service = WebhookService()
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    created = service.create(
        tenant,
        actor,
        {"name": "Inbound", "direction": WebhookDirection.INBOUND, "events": ["integration.updated"]},
    )
    webhook = service.activate(tenant, actor, created.record.id, "activate-inbound")
    raw = json.dumps({"event": "integration.updated", "api_key": "secret-value", "name": "Acme"}).encode()
    timestamp = str(int(timezone.now().timestamp()))
    nonce = "nonce-" + uuid.uuid4().hex
    canonical = f"{INBOUND_SIGNATURE_VERSION}.{timestamp}.{nonce}.".encode("ascii") + raw
    signature = "sha256=" + hmac.new(created.secret.encode(), canonical, hashlib.sha256).hexdigest()
    headers = {
        INBOUND_TIMESTAMP_HEADER: timestamp,
        INBOUND_NONCE_HEADER: nonce,
        INBOUND_SIGNATURE_HEADER: signature,
    }
    job = service.receive(webhook.public_id, headers, raw)
    assert job.payload["payload"]["api_key"] == "[REDACTED]"
    webhook.refresh_from_db()
    assert webhook.last_received_at is not None
    with pytest.raises(Exception) as replay_exc:
        service.receive(webhook.public_id, headers, raw)
    assert getattr(replay_exc.value, "error_code", None) == "nonce_replayed"
    with pytest.raises(Exception) as signature_exc:
        service.receive(webhook.public_id, {**headers, INBOUND_NONCE_HEADER: "nonce-" + uuid.uuid4().hex}, raw)
    assert getattr(signature_exc.value, "error_code", None) == "invalid_signature"


def test_webhook_update_rotate_enqueue_redrive_and_worker_outcomes():
    service = WebhookService()
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    created = service.create(
        tenant,
        actor,
        {
            "name": "Outbound",
            "direction": WebhookDirection.OUTBOUND,
            "url": "https://provider.example.test/hooks",
            "events": ["integration.updated"],
            "config": {"dependency": "provider"},
            "max_attempts": 2,
        },
    )
    webhook = service.activate(tenant, actor, created.record.id, "activate-outbound")
    updated = service.update(
        tenant,
        actor,
        webhook.id,
        {"name": "Outbound v2", "events": ["integration.updated", "integration.deleted"], "timeout_seconds": 3},
    )
    assert updated.name == "Outbound v2"
    rotated = service.rotate_secret(tenant, actor, webhook.id, "rotate-secret")
    assert rotated.secret != created.secret
    with pytest.raises(Exception) as rotate_exc:
        service.rotate_secret(tenant, actor, webhook.id, "rotate-secret")
    assert getattr(rotate_exc.value, "error_code", None) == "secret_already_rotated"

    delivery = service.enqueue_delivery(
        tenant,
        actor,
        webhook.id,
        "integration.updated",
        {"api_key": "secret-value", "record": "1"},  # pragma: allowlist secret
        "deliver-1",
    )
    assert delivery.payload["api_key"] == "[REDACTED]"
    assert service.enqueue_delivery(tenant, actor, webhook.id, "integration.updated", {}, "deliver-1").id == delivery.id
    job = AsyncJob.objects.get(id=delivery.job_id)
    success = WebhookDeliveryWorker(http_client=ResponseClient(204)).execute(tenant, job)
    delivery.refresh_from_db()
    assert success.status == "succeeded"
    assert delivery.status == DeliveryStatus.DELIVERED

    retry_delivery = service.enqueue_delivery(tenant, actor, webhook.id, "integration.deleted", {}, "deliver-2")
    retry_job = AsyncJob.objects.get(id=retry_delivery.job_id)
    retry = WebhookDeliveryWorker(http_client=ResponseClient(503)).execute(tenant, retry_job)
    retry_delivery.refresh_from_db()
    assert retry.status == "failed"
    assert retry_delivery.status == DeliveryStatus.RETRYING
    assert retry_delivery.next_attempt_at is not None

    dead = delivery_factory(webhook=webhook, max_attempts=1)
    dead_job = enqueue(tenant, actor, WebhookService.DELIVERY_COMMAND, {"delivery_id": str(dead.id)}, "dead-job")
    dead.job_id = dead_job.id
    dead.save(update_fields=("job_id", "updated_at"))
    dead_result = WebhookDeliveryWorker(http_client=RaisingClient()).execute(tenant, dead_job)
    dead.refresh_from_db()
    webhook.refresh_from_db()
    assert dead_result.error_code == "delivery_dead_lettered"
    assert dead.status == DeliveryStatus.DEAD_LETTER
    assert webhook.status == WebhookStatus.ERROR
    redriven = service.redrive_delivery(tenant, actor, dead.id, "redrive-dead")
    assert redriven.status == DeliveryStatus.QUEUED


def test_webhook_delivery_retry_not_due_and_soft_delete_guards():
    webhook = webhook_factory(status=WebhookStatus.ACTIVE)
    delivery = delivery_factory(webhook=webhook)
    delivery = DELIVERY_STATE_MACHINE.apply(delivery, "start", tenant_id=delivery.tenant_id, transition_key="start")
    delivery = DELIVERY_STATE_MACHINE.apply(delivery, "retry", tenant_id=delivery.tenant_id, transition_key="retry")
    delivery.next_attempt_at = timezone.now() + timedelta(minutes=5)
    job = enqueue(
        delivery.tenant_id,
        webhook.created_by,
        WebhookService.DELIVERY_COMMAND,
        {"delivery_id": str(delivery.id)},
        "retry-not-due",
    )
    delivery.job_id = job.id
    delivery.save(update_fields=("next_attempt_at", "job_id", "updated_at"))
    with pytest.raises(Exception) as retry_exc:
        WebhookDeliveryWorker(http_client=ResponseClient(204)).execute(delivery.tenant_id, job)
    assert getattr(retry_exc.value, "error_code", None) == "retry_not_due"

    service = WebhookService()
    with pytest.raises(Exception) as active_delete_exc:
        service.soft_delete(webhook.tenant_id, webhook.created_by, webhook.id)
    assert getattr(active_delete_exc.value, "error_code", None) == "invalid_state"
    webhook = WEBHOOK_STATE_MACHINE.apply(
        webhook,
        "deactivate",
        tenant_id=webhook.tenant_id,
        transition_key="deactivate",
    )
    service.soft_delete(webhook.tenant_id, webhook.created_by, webhook.id)
    webhook.refresh_from_db()
    assert webhook.is_deleted is True
