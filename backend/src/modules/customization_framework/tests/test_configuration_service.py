"""Service-level proof for validated, versioned tenant runtime configuration."""

from __future__ import annotations

import uuid

import pytest

from src.modules.customization_framework.models import (
    ConfigurationAuditRecord,
    RuntimeConfigurationVersion,
)
from src.modules.customization_framework.services import (
    CustomizationConfigurationService,
    CustomizationValidationError,
    default_configuration_document,
    effective_configuration,
)

pytestmark = pytest.mark.django_db


def test_configuration_update_replay_audit_and_cross_tenant_isolation(
    tenant_a: object,
    tenant_b: object,
    actor_id: uuid.UUID,
) -> None:
    service = CustomizationConfigurationService()
    tenant_a_id = tenant_a.id
    tenant_b_id = tenant_b.id
    document = default_configuration_document()
    document["limits"]["ast_nodes"] = 128
    correlation = uuid.uuid4()
    command_key = str(uuid.uuid4())

    created = service.update(
        tenant_a_id,
        actor_id=actor_id,
        correlation_id=correlation,
        idempotency_key=command_key,
        expected_version=0,
        document=document,
    )
    replay = service.update(
        tenant_a_id,
        actor_id=actor_id,
        correlation_id=correlation,
        idempotency_key=command_key,
        expected_version=0,
        document=document,
    )

    assert replay.id == created.id
    assert replay.version == 1
    assert effective_configuration(tenant_a_id)["limits"]["ast_nodes"] == 128
    assert effective_configuration(tenant_b_id)["limits"]["ast_nodes"] == 256
    assert service.get(tenant_b_id) is None
    assert RuntimeConfigurationVersion.objects.for_tenant(tenant_a_id).count() == 1
    audit = ConfigurationAuditRecord.objects.for_tenant(tenant_a_id).get()
    assert audit.correlation_id == correlation
    assert audit.before["limits"]["ast_nodes"] == 256
    assert audit.after["limits"]["ast_nodes"] == 128


def test_configuration_validation_preview_rollback_and_import_guard(
    tenant_a: object,
    actor_id: uuid.UUID,
) -> None:
    service = CustomizationConfigurationService()
    tenant_id = tenant_a.id
    first = default_configuration_document()
    first["list_preferences"]["page_size"] = 20
    created = service.update(
        tenant_id,
        actor_id=actor_id,
        correlation_id=uuid.uuid4(),
        idempotency_key=str(uuid.uuid4()),
        expected_version=0,
        document=first,
    )
    second = default_configuration_document()
    second["list_preferences"]["page_size"] = 40
    preview = service.preview(tenant_id, document=second)
    assert preview["valid"] is True
    assert "list_preferences" in preview["changes"]
    updated = service.update(
        tenant_id,
        actor_id=actor_id,
        correlation_id=uuid.uuid4(),
        idempotency_key=str(uuid.uuid4()),
        expected_version=created.version,
        document=second,
    )
    rolled_back = service.rollback(
        tenant_id,
        actor_id=actor_id,
        correlation_id=uuid.uuid4(),
        idempotency_key=str(uuid.uuid4()),
        expected_version=updated.version,
        target_version=1,
    )
    assert rolled_back.version == 3
    assert rolled_back.document["list_preferences"]["page_size"] == 20

    exported = service.export_document(tenant_id)
    exported["tenant_id"] = str(uuid.uuid4())
    with pytest.raises(CustomizationValidationError):
        service.import_document(
            tenant_id,
            actor_id=actor_id,
            correlation_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            expected_version=rolled_back.version,
            payload=exported,
        )

    invalid = default_configuration_document()
    invalid["list_preferences"]["page_size"] = 101
    with pytest.raises(CustomizationValidationError):
        service.preview(tenant_id, document=invalid)
