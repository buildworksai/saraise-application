"""Tenant isolation, validation, versioning, and immutable evidence contracts."""

import uuid

import pytest
from django.core.exceptions import ValidationError

from ..configuration import default_configuration
from ..models import (
    ImmutableRecordError,
    IntegrationPlatformConfiguration,
    IntegrationPlatformConfigurationAudit,
)
from ..services import ConfigurationService

pytestmark = pytest.mark.django_db


def test_configuration_is_tenant_scoped_versioned_audited_and_reversible() -> None:
    tenant_a, tenant_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    service = ConfigurationService()
    first = default_configuration()
    first["environment"] = "test"
    saved = service.save(
        tenant_a, actor, first, environment="test", correlation_id="config-create"
    )
    second = default_configuration()
    second["environment"] = "test"
    second["mapping"]["preview_record_limit"] = 17
    updated = service.save(
        tenant_a, actor, second, environment="test", correlation_id="config-update"
    )

    assert saved["version"] == 1
    assert updated["version"] == 2
    assert service.get(tenant_b, "test")["version"] == 0
    assert list(service.versions(tenant_b, "test")) == []
    assert list(service.audits(tenant_b, "test")) == []

    rolled_back = service.rollback(
        tenant_a, actor, 1, environment="test", correlation_id="config-rollback"
    )
    assert rolled_back["version"] == 3
    assert rolled_back["document"] == first
    assert IntegrationPlatformConfiguration.objects.filter(tenant_id=tenant_a).count() == 1
    assert IntegrationPlatformConfigurationAudit.objects.filter(tenant_id=tenant_a).count() == 3


def test_configuration_rejects_unsafe_limits_and_audit_tampering() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    service = ConfigurationService()
    document = default_configuration()
    document["security"]["signature_window_seconds"] = 0
    with pytest.raises(ValidationError):
        service.save(tenant, actor, document, correlation_id="unsafe")

    saved = service.save(
        tenant, actor, default_configuration(), correlation_id="immutable"
    )
    audit = IntegrationPlatformConfigurationAudit.objects.get(
        configuration_id=saved["id"]
    )
    audit.action = "tampered"
    with pytest.raises(ImmutableRecordError):
        audit.save()
    with pytest.raises(ImmutableRecordError):
        audit.delete()
