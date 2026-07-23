from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError

from src.core.access.decision import AccessDecision, AccessReasonCode
from ..models import WorkflowAutomationConfigurationRevision
from ..services import WorkflowConfigurationService, default_configuration_document

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def allow_declared_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def allow(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="declared configuration permission granted",
            tenant_id=tenant_id,
            remaining_quota=100,
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", allow)


def test_configuration_is_tenant_isolated_versioned_and_audited(
    tenant_a,
    tenant_b,
    tenant_a_user,
) -> None:
    first = WorkflowConfigurationService.get_configuration(tenant_a.id)
    other = WorkflowConfigurationService.get_configuration(tenant_b.id)
    assert first.tenant_id == tenant_a.id
    assert other.tenant_id == tenant_b.id
    assert first.id != other.id

    document = default_configuration_document()
    document["limits"]["catalog_default_limit"] = 30
    updated = WorkflowConfigurationService.update_configuration(
        tenant_a.id,
        tenant_a_user,
        document,
        expected_version=1,
        change_reason="raise-governed-page-size",
    )
    assert updated.version == 2
    assert WorkflowConfigurationService.get_configuration(tenant_b.id).version == 1
    revision = WorkflowAutomationConfigurationRevision.objects.for_tenant(tenant_a.id).get(version=2)
    assert revision.previous_document["limits"]["catalog_default_limit"] == 25
    assert revision.document["limits"]["catalog_default_limit"] == 30
    assert revision.correlation_id
    with pytest.raises(DjangoValidationError):
        WorkflowAutomationConfigurationRevision.objects.for_tenant(tenant_a.id).filter(id=revision.id).update(
            change_reason="tampered"
        )


def test_configuration_rejects_unsafe_limits_and_rolls_back(
    tenant_a,
    tenant_a_user,
) -> None:
    WorkflowConfigurationService.get_configuration(tenant_a.id)
    invalid = default_configuration_document()
    invalid["limits"]["catalog_default_limit"] = 101
    invalid["limits"]["catalog_max_limit"] = 100
    with pytest.raises(ValidationError):
        WorkflowConfigurationService.update_configuration(
            tenant_a.id,
            tenant_a_user,
            invalid,
            expected_version=1,
            change_reason="unsafe",
        )

    changed = default_configuration_document()
    changed["operational"]["execution_poll_interval_ms"] = 20000
    WorkflowConfigurationService.update_configuration(
        tenant_a.id,
        tenant_a_user,
        changed,
        expected_version=1,
        change_reason="poll-policy",
    )
    restored = WorkflowConfigurationService.rollback(
        tenant_a.id,
        tenant_a_user,
        1,
        expected_version=2,
    )
    assert restored.version == 3
    assert restored.document["operational"]["execution_poll_interval_ms"] == 15000


def test_configuration_api_preview_history_export_and_cross_tenant_isolation(
    tenant_a_client,
    tenant_a,
    tenant_b,
) -> None:
    WorkflowConfigurationService.get_configuration(tenant_b.id)
    response = tenant_a_client.get("/api/v2/workflow-automation/configuration/")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["tenant_id"] == str(tenant_a.id)
    assert payload["tenant_id"] != str(tenant_b.id)

    preview = tenant_a_client.post(
        "/api/v2/workflow-automation/configuration/preview/",
        {"environment": "production", "document": payload["document"]},
        format="json",
    )
    assert preview.status_code == 200
    assert preview.json()["data"]["valid"] is True

    history = tenant_a_client.get("/api/v2/workflow-automation/configuration/history/")
    assert history.status_code == 200
    assert all(item["correlation_id"] for item in history.json()["data"])

    exported = tenant_a_client.get("/api/v2/workflow-automation/configuration/export/")
    assert exported.status_code == 200
    assert exported.json()["data"]["schema"] == "saraise.workflow-automation.configuration/v1"
    assert "attachment;" in exported["Content-Disposition"]
