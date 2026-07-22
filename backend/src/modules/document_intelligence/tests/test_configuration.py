"""Governed configuration validation, evidence, rollback, and tenant isolation."""

from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction

from src.modules.document_intelligence.models import ConfigurationAudit, ConfigurationVersion
from src.modules.document_intelligence.services import (
    ConfigurationService,
    DocumentIntelligenceError,
    default_configuration_document,
)


@pytest.mark.django_db
def test_missing_configuration_is_atomically_materialized_with_audit() -> None:
    tenant_id = uuid.uuid4()

    effective = ConfigurationService().get_effective(tenant_id, "development")

    assert effective == default_configuration_document()
    assert ConfigurationVersion.objects.for_tenant(tenant_id).count() == 1
    audit = ConfigurationAudit.objects.for_tenant(tenant_id).get()
    assert audit.operation == ConfigurationAudit.Operation.INITIALIZE
    assert audit.correlation_id


@pytest.mark.django_db
def test_configuration_is_versioned_audited_and_tenant_isolated() -> None:
    tenant_a, tenant_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    service = ConfigurationService()
    document = default_configuration_document()
    created = service.save(
        tenant_a,
        actor,
        document,
        environment="development",
        change_reason="Initialize governed defaults",
        correlation_id="configuration-test-create",
    )

    assert created.version == 1
    assert service.get_effective(tenant_a, "development") == document
    assert ConfigurationVersion.objects.for_tenant(tenant_a).count() == 1
    audit = ConfigurationAudit.objects.for_tenant(tenant_a).get()
    assert audit.operation == ConfigurationAudit.Operation.INITIALIZE
    assert audit.previous_document is None
    assert audit.new_document == document
    assert audit.correlation_id == "configuration-test-create"
    assert not ConfigurationVersion.objects.for_tenant(tenant_b).exists()
    assert not ConfigurationAudit.objects.for_tenant(tenant_b).exists()
    assert service.get_effective(tenant_b, "development") == default_configuration_document()
    assert ConfigurationVersion.objects.for_tenant(tenant_b).count() == 1
    assert ConfigurationVersion.objects.for_tenant(tenant_b).get().tenant_id == tenant_b


@pytest.mark.django_db
def test_invalid_configuration_is_unsavable_and_creates_no_evidence() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    document = default_configuration_document()
    document["extraction"]["max_active"] = 0

    with pytest.raises(DocumentIntelligenceError) as caught:
        ConfigurationService().save(
            tenant,
            actor,
            document,
            environment="development",
            change_reason="Unsafe change",
        )

    assert caught.value.error_code == "invalid_configuration"
    assert not ConfigurationVersion.objects.for_tenant(tenant).exists()
    assert not ConfigurationAudit.objects.for_tenant(tenant).exists()


@pytest.mark.django_db
def test_update_rollback_import_export_and_simulation_are_real() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    service = ConfigurationService()
    original = default_configuration_document()
    service.save(
        tenant,
        actor,
        original,
        environment="development",
        change_reason="Initialize",
        correlation_id="config-v1",
    )
    changed = default_configuration_document()
    changed["extraction"]["max_active"] = 9
    updated = service.save(
        tenant,
        actor,
        changed,
        environment="development",
        change_reason="Raise bounded concurrency",
        correlation_id="config-v2",
    )
    assert updated.version == 2
    simulation = service.simulate(tenant, original, environment="development")
    assert simulation["valid"] is True
    assert simulation["changes"] == [{"path": "extraction.max_active", "before": 9, "after": 5}]
    assert ConfigurationVersion.objects.for_tenant(tenant).count() == 2

    rolled_back = service.rollback(
        tenant,
        actor,
        1,
        environment="development",
        change_reason="Restore version one",
        correlation_id="config-v3",
    )
    assert rolled_back.version == 3
    assert rolled_back.document == original
    assert ConfigurationAudit.objects.for_tenant(tenant).get(version=3).operation == "rollback"

    exported = service.export_document(tenant, "development")
    imported_tenant = uuid.uuid4()
    imported = service.import_document(
        imported_tenant,
        actor,
        exported,
        change_reason="Promote reviewed configuration",
        correlation_id="config-import",
    )
    assert imported.document == original
    assert imported.tenant_id == imported_tenant
    assert ConfigurationAudit.objects.for_tenant(imported_tenant).get().operation == "initialize"


@pytest.mark.django_db
def test_configuration_evidence_rejects_bulk_and_raw_mutation() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    ConfigurationService().save(
        tenant,
        actor,
        default_configuration_document(),
        environment="development",
        change_reason="Initialize",
    )
    version = ConfigurationVersion.objects.for_tenant(tenant).get()
    with pytest.raises(ValidationError):
        ConfigurationVersion.objects.for_tenant(tenant).update(change_reason="tampered")
    with pytest.raises(ValidationError):
        ConfigurationAudit.objects.for_tenant(tenant).delete()
    if connection.vendor != "postgresql":
        return
    with pytest.raises(DatabaseError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE document_intelligence_configuration_versions SET change_reason = %s WHERE id = %s",
                ["tampered", str(version.id)],
            )
