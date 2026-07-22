"""Proof for tenant configuration validation, history, rollback, import, and isolation."""

import uuid

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError

from ..models import ProcessMiningConfiguration, ProcessMiningConfigurationAudit
from ..services import ProcessMiningConfigurationService

pytestmark = pytest.mark.django_db


def test_configuration_is_tenant_scoped_and_versioned():
    service = ProcessMiningConfigurationService()
    tenant_a, tenant_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    value_a = service.get_configuration(tenant_a, actor, "req_config_a")
    value_b = service.get_configuration(tenant_b, actor, "req_config_b")
    assert value_a.tenant_id == tenant_a and value_b.tenant_id == tenant_b
    assert ProcessMiningConfiguration.objects.for_tenant(tenant_a).count() == 1
    assert not ProcessMiningConfiguration.objects.for_tenant(tenant_a).filter(pk=value_b.pk).exists()
    assert value_a.versions.count() == 1 and value_a.audits.count() == 1


def test_configuration_preview_update_rollback_and_import():
    service = ProcessMiningConfigurationService()
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    initial = service.get_configuration(tenant, actor, "req_initial")
    changed = dict(initial.document)
    changed["max_batch_events"] = 250
    preview = service.preview(tenant, changed)
    assert preview["changes"]["max_batch_events"] == {"from": 10_000, "to": 250}
    updated = service.update(tenant, actor, "req_update", changed)
    assert updated.version == 2 and updated.document["max_batch_events"] == 250
    rolled_back = service.rollback(tenant, actor, "req_rollback", 1)
    assert rolled_back.version == 3 and rolled_back.document["max_batch_events"] == 10_000
    exported = service.export_document(tenant)
    exported["document"]["max_batch_events"] = 300
    imported = service.import_document(tenant, actor, "req_import", exported)
    assert imported.version == 4 and imported.document["max_batch_events"] == 300
    assert list(service.history(tenant).values_list("version", flat=True)) == [4, 3, 2, 1]


def test_configuration_safe_limits_and_dependencies_are_server_enforced():
    service = ProcessMiningConfigurationService()
    tenant = uuid.uuid4()
    document = service.get_configuration(tenant).document
    invalid = dict(document)
    invalid["retention_days"] = invalid["retention_min_days"] - 1
    with pytest.raises(ValidationError):
        service.update(tenant, uuid.uuid4(), "req_invalid", invalid)
    invalid = dict(document)
    invalid["unknown_policy"] = True
    with pytest.raises(ValidationError):
        service.preview(tenant, invalid)


def test_configuration_audit_is_immutable():
    service = ProcessMiningConfigurationService()
    configuration = service.get_configuration(uuid.uuid4(), uuid.uuid4(), "req_audit")
    audit = configuration.audits.get()
    audit.action = "tampered"
    with pytest.raises(DjangoValidationError, match="immutable"):
        audit.save()
    with pytest.raises(DjangoValidationError, match="cannot be deleted"):
        audit.delete()
    assert ProcessMiningConfigurationAudit.objects.filter(pk=audit.pk, action="initialize").exists()
