"""Tenant configuration lifecycle and isolation proof."""

import uuid

import pytest
from django.core.exceptions import ValidationError

from ..models import CRMConfiguration, CRMConfigurationAudit, CRMConfigurationVersion
from ..services import AccountService, CRMConfigurationService, CRMServiceError, LeadService

pytestmark = pytest.mark.django_db


def _write(tenant_id, threshold=70, correlation="cfg-test"):
    return CRMConfigurationService.write(
        tenant_id,
        payload={"environment": "production", "document": {"lead": {"qualification_threshold": threshold}}},
        actor_id="configuration-admin",
        correlation_id=correlation,
    )


def test_configuration_is_tenant_isolated_and_defaults_are_complete():
    first = uuid.uuid4()
    second = uuid.uuid4()
    _write(first, 83)

    assert CRMConfigurationService.get(first)["document"]["lead"]["qualification_threshold"] == 83
    assert CRMConfigurationService.get(second)["document"]["lead"]["qualification_threshold"] == 70
    assert CRMConfiguration.objects.filter(tenant_id=second).count() == 0
    assert CRMConfigurationVersion.objects.filter(tenant_id=second).count() == 0
    assert CRMConfigurationAudit.objects.filter(tenant_id=second).count() == 0


def test_configuration_validation_rejects_unsafe_or_unknown_values_before_write():
    tenant = uuid.uuid4()
    with pytest.raises(CRMServiceError, match="Grade thresholds"):
        CRMConfigurationService.write(
            tenant,
            payload={"document": {"lead": {"grade_thresholds": {"A": 60, "B": 80, "C": 40, "D": 0}}}},
            actor_id="admin",
            correlation_id="invalid-bands",
        )
    with pytest.raises(CRMServiceError, match="unsupported fields"):
        CRMConfigurationService.write(
            tenant,
            payload={"document": {"lead": {"unbounded_override": 999999}}},
            actor_id="admin",
            correlation_id="unknown-setting",
        )
    with pytest.raises(CRMServiceError, match="unsupported source"):
        CRMConfigurationService.write(
            tenant,
            payload={
                "document": {
                    "opportunity": {
                        "transitions": {
                            "advance_to_qualification": {
                                "from": ["closed_won"],
                                "to": "qualification",
                            }
                        }
                    }
                }
            },
            actor_id="admin",
            correlation_id="unsafe-transition",
        )
    assert not CRMConfiguration.objects.filter(tenant_id=tenant).exists()


def test_versions_audits_rollback_and_import_export_are_reversible_and_immutable():
    tenant = uuid.uuid4()
    first = _write(tenant, 71, "version-one")
    second = _write(tenant, 88, "version-two")
    assert (first["version"], second["version"]) == (1, 2)

    rolled_back = CRMConfigurationService.rollback(
        tenant,
        environment="production",
        version=1,
        actor_id="rollback-admin",
        correlation_id="rollback-correlation",
    )
    assert rolled_back["version"] == 3
    assert rolled_back["document"]["lead"]["qualification_threshold"] == 71
    versions = CRMConfigurationService.versions(tenant)
    assert versions[0]["change_type"] == "rollback"
    assert versions[0]["rollback_of_version"] == 1

    exported = CRMConfigurationService.export(tenant)
    imported_tenant = uuid.uuid4()
    imported = CRMConfigurationService.import_document(
        imported_tenant,
        exported=exported,
        actor_id="import-admin",
        correlation_id="import-correlation",
    )
    assert imported["document"] == rolled_back["document"]

    version = CRMConfigurationVersion.objects.filter(tenant_id=tenant).first()
    audit = CRMConfigurationAudit.objects.filter(tenant_id=tenant).first()
    version.change_type = "tampered"
    audit.action = "tampered"
    with pytest.raises(ValidationError, match="immutable"):
        version.save()
    with pytest.raises(ValidationError, match="immutable"):
        audit.save()
    with pytest.raises(ValidationError, match="immutable"):
        version.delete()
    with pytest.raises(ValidationError, match="immutable"):
        audit.delete()


def test_configured_tenant_defaults_are_applied_by_services():
    tenant = uuid.uuid4()
    CRMConfigurationService.write(
        tenant,
        payload={
            "document": {
                "lead": {"default_score": 5, "default_grade": "D", "default_status": "contacted"},
                "account": {"default_type": "partner"},
            }
        },
        actor_id="configuration-admin",
        correlation_id="configured-defaults",
    )

    lead = LeadService.create_lead(tenant, data={"last_name": "Configured"}, actor_id="operator")
    account = AccountService.create_account(tenant, data={"name": "Configured Account"}, actor_id="operator")

    assert (lead.score, lead.grade, lead.status) == (5, "D", "contacted")
    assert account.account_type == "partner"


def test_configuration_write_rejects_a_stale_expected_version():
    tenant = uuid.uuid4()
    _write(tenant, 71)

    with pytest.raises(CRMServiceError, match="stale"):
        CRMConfigurationService.write(
            tenant,
            payload={"document": {"lead": {"qualification_threshold": 72}}},
            actor_id="configuration-admin",
            correlation_id="stale-write",
            expected_version=0,
        )
