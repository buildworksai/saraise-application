"""Domain-model constraints and lifecycle integrity."""

import uuid

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from src.core.tenancy import TenantScopedModel

from ..models import (
    Connector,
    CredentialStatus,
    DataMapping,
    DeliveryStatus,
    ImmutableDeliveryError,
    Integration,
    IntegrationCredential,
    Webhook,
    WebhookDelivery,
)
from ..state_machines import CREDENTIAL_STATE_MACHINE, DELIVERY_STATE_MACHINE, INTEGRATION_STATE_MACHINE
from .factories import connector_factory, credential_factory, delivery_factory, integration_factory, mapping_factory, webhook_factory

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def encryption_key(settings):
    settings.SARAISE_ENCRYPTION_KEY = Fernet.generate_key().decode()


def test_tenancy_and_native_uuid_contracts():
    assert not issubclass(Connector, TenantScopedModel)
    for model in (Integration, IntegrationCredential, Webhook, WebhookDelivery, DataMapping):
        assert issubclass(model, TenantScopedModel)
        assert model._meta.get_field("tenant_id").get_internal_type() == "UUIDField"
        assert model._meta.get_field("id").get_internal_type() == "UUIDField"


def test_connector_validates_schemas_and_capabilities():
    connector = Connector(
        key="invalid",
        name="Invalid",
        connector_type="api",
        adapter_key="tests.invalid",
        version="1.0.0",
        schema={"type": "not-a-json-schema-type"},
        credential_schema={"type": "object"},
        capabilities=["unknown"],
    )
    with pytest.raises(ValidationError):
        connector.full_clean()


def test_same_tenant_foreign_keys_are_enforced_by_clean():
    integration = integration_factory()
    credential = credential_factory(integration, tenant_id=uuid.uuid4())
    with pytest.raises(ValidationError):
        credential.full_clean()
    mapping = mapping_factory(integration, tenant_id=uuid.uuid4())
    with pytest.raises(ValidationError):
        mapping.full_clean()
    delivery = delivery_factory(webhook_factory(), tenant_id=uuid.uuid4())
    with pytest.raises(ValidationError):
        delivery.full_clean()


def test_partial_live_name_uniqueness_and_soft_delete():
    first = integration_factory(name="Shared")
    with pytest.raises(IntegrityError), transaction.atomic():
        integration_factory(connector=first.connector, tenant_id=first.tenant_id, name="Shared")
    first.is_deleted = True
    first.save(update_fields=("is_deleted", "updated_at"))
    integration_factory(connector=first.connector, tenant_id=first.tenant_id, name="Shared")


def test_only_one_active_credential_per_type():
    credential = credential_factory()
    with pytest.raises(IntegrityError), transaction.atomic():
        credential_factory(credential.integration, credential_type=credential.credential_type)


def test_state_machines_are_legal_idempotent_and_guard_direct_assignment():
    integration = integration_factory()
    transitioned = INTEGRATION_STATE_MACHINE.apply(
        integration,
        "request_test",
        tenant_id=integration.tenant_id,
        transition_key="test-1",
    )
    assert transitioned.status == "testing"
    repeated = INTEGRATION_STATE_MACHINE.apply(
        transitioned,
        "request_test",
        tenant_id=integration.tenant_id,
        transition_key="test-1",
    )
    assert len(repeated.transition_history) == 1
    repeated.status = "inactive"
    with pytest.raises(ValidationError):
        repeated.save()


def test_terminal_credential_and_delivery_evidence_are_immutable():
    credential = credential_factory()
    revoked = CREDENTIAL_STATE_MACHINE.apply(
        credential,
        "revoke",
        tenant_id=credential.tenant_id,
        transition_key="revoke-1",
    )
    assert revoked.status == CredentialStatus.REVOKED
    delivery = delivery_factory()
    delivery = DELIVERY_STATE_MACHINE.apply(delivery, "start", tenant_id=delivery.tenant_id, transition_key="start")
    delivery = DELIVERY_STATE_MACHINE.apply(delivery, "succeed", tenant_id=delivery.tenant_id, transition_key="success")
    assert delivery.status == DeliveryStatus.DELIVERED
    delivery.payload = {"changed": True}
    with pytest.raises(ImmutableDeliveryError):
        delivery.save()
    with pytest.raises(ImmutableDeliveryError):
        delivery.delete()
