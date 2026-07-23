"""Tenant configuration validation, versioning and isolation proofs."""

from __future__ import annotations

import uuid

import pytest

from src.core.access.entitlements import Quota
from src.modules.dms.managers import ImmutableVersionError
from src.modules.dms.models import DmsConfiguration, DmsConfigurationAudit, DmsConfigurationVersion
from src.modules.dms.services import (
    DEFAULT_DMS_CONFIGURATION,
    DmsConfigurationService,
    DmsPermissionDenied,
    DmsValidationError,
)

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db


def test_configuration_is_tenant_scoped_versioned_audited_and_reversible() -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    actor_a, actor_b = uuid.uuid4(), uuid.uuid4()

    initial_a = DmsConfigurationService.current(tenant_a, actor_a)
    initial_b = DmsConfigurationService.current(tenant_b, actor_b)
    assert initial_a.values == DEFAULT_DMS_CONFIGURATION
    assert initial_b.values == DEFAULT_DMS_CONFIGURATION
    assert DmsConfiguration.objects.filter(tenant_id=tenant_a).get() == initial_a
    assert not DmsConfiguration.objects.filter(tenant_id=tenant_a, id=initial_b.id).exists()

    changed = dict(initial_a.values)
    changed["max_document_tags"] = 75
    preview = DmsConfigurationService.preview(tenant_a, actor_a, changed)
    assert preview["valid"] is True
    assert preview["changes"] == [{"field": "max_document_tags", "before": 50, "after": 75}]

    updated = DmsConfigurationService.update(tenant_a, actor_a, changed)
    assert updated.version == 2
    assert DmsConfigurationService.runtime_values(tenant_a)["max_document_tags"] == 75
    assert list(DmsConfigurationService.history(tenant_a, actor_a).values_list("version", flat=True)) == [2, 1]
    audit = list(DmsConfigurationService.audit(tenant_a, actor_a))
    assert [row.action for row in audit] == ["updated", "created"]
    assert all(row.correlation_id for row in audit)
    assert all(row.tenant_id == tenant_a for row in audit)
    assert not DmsConfigurationVersion.objects.filter(tenant_id=tenant_a, configuration=initial_b).exists()
    assert not DmsConfigurationAudit.objects.filter(tenant_id=tenant_a, configuration=initial_b).exists()
    projected_quota = Quota.objects.get(tenant_id=tenant_a, resource="dms.api_reads")
    assert projected_quota.limit == changed["api_read_quota"]
    assert projected_quota.remaining == changed["api_read_quota"]
    assert projected_quota.metadata["configuration_version"] == 2

    rolled_back = DmsConfigurationService.rollback(tenant_a, actor_a, 1)
    assert rolled_back.version == 3
    assert rolled_back.values["max_document_tags"] == 50
    assert DmsConfigurationService.current(tenant_b, actor_b).version == 1


def test_configuration_import_export_validation_and_immutable_evidence() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    current = DmsConfigurationService.current(tenant_id, actor_id)
    document = DmsConfigurationService.export_document(tenant_id, actor_id)
    values = dict(document["values"])
    values["default_share_access_count"] = 11
    document["values"] = values
    imported = DmsConfigurationService.import_document(tenant_id, actor_id, document)
    assert imported.version == 2
    assert imported.values["default_share_access_count"] == 11
    wrong_module = dict(document)
    wrong_module["module"] = "another-module"
    with pytest.raises(DmsValidationError):
        DmsConfigurationService.import_document(tenant_id, actor_id, wrong_module)

    invalid = dict(imported.values)
    invalid["max_folder_depth"] = 65
    with pytest.raises(DmsValidationError):
        DmsConfigurationService.update(tenant_id, actor_id, invalid)
    current.refresh_from_db()
    assert current.version == 2

    version = DmsConfigurationVersion.objects.filter(tenant_id=tenant_id).first()
    audit = DmsConfigurationAudit.objects.filter(tenant_id=tenant_id).first()
    assert version is not None and audit is not None
    with pytest.raises(ImmutableVersionError):
        DmsConfigurationVersion.objects.filter(id=version.id).update(values={})
    with pytest.raises(ImmutableVersionError):
        audit.delete()


def test_feature_rollout_uses_server_owned_tenant_roles(tenant_a_user) -> None:
    tenant_a_user.profile.refresh_from_db()
    tenant_id = tenant_a_user.profile.tenant_id
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{tenant_a_user.id}")
    configuration = DmsConfigurationService.current(tenant_id, actor_id)
    values = dict(configuration.values)
    values["rollout"] = {
        "enabled": True,
        "roles": ["tenant_admin"],
        "cohorts": [],
    }
    DmsConfigurationService.update(tenant_id, actor_id, values)

    DmsConfigurationService.require_feature(tenant_id, actor_id, "uploads")
    with pytest.raises(DmsPermissionDenied):
        DmsConfigurationService.require_feature(tenant_id, uuid.uuid4(), "uploads")
