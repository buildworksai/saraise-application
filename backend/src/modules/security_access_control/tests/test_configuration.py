"""Tenant configuration lifecycle, replay safety, and isolation proof."""

from __future__ import annotations

import uuid

import pytest
from rest_framework.permissions import IsAuthenticated

from src.core.async_jobs.models import OutboxEvent
from src.modules.security_access_control.api import GovernedSecurityViewSet
from src.modules.security_access_control.models import (
    ImmutableConfigurationError,
    MutationReplay,
    SecurityAuditLog,
    SecurityConfiguration,
    SecurityConfigurationVersion,
)
from src.modules.security_access_control.services import (
    ConfigurationService,
    SecurityNotFound,
    SecurityValidationError,
    default_security_configuration,
)

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db
BASE = "/api/v2/security-access-control/configuration"


@pytest.fixture
def actor_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def correlation_id() -> str:
    return f"corr-{uuid.uuid4()}"


@pytest.fixture(autouse=True)
def authorize_configuration_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GovernedSecurityViewSet, "get_permissions", lambda self: [IsAuthenticated()])


def _data(response):
    assert response.status_code < 400, response.content
    return response.json()["data"]


def test_configuration_versions_are_tenant_scoped_immutable_and_rollback_any_version(
    tenant_a, tenant_b, actor_id, correlation_id
) -> None:
    current = ConfigurationService.current(
        tenant_a.id, actor_id=actor_id, correlation_id=correlation_id, environment="test"
    )
    assert current.tenant_id == tenant_a.id and current.version == 1
    changed = default_security_configuration()
    changed["limits"]["audit_default_window_days"] = 14
    updated = ConfigurationService.replace(
        tenant_a.id,
        document=changed,
        environment="test",
        rollout=current.rollout,
        actor_id=actor_id,
        correlation_id="corr-update",
        reason="Reduce the default evidence window",
    )
    assert updated.version == 2
    assert SecurityConfiguration.objects.for_tenant(tenant_b.id).count() == 0
    assert SecurityConfigurationVersion.objects.for_tenant(tenant_b.id).count() == 0
    with pytest.raises(SecurityNotFound):
        ConfigurationService.rollback(
            tenant_b.id, 1, actor_id=actor_id, correlation_id="corr-foreign", reason="Foreign rollback"
        )
    rolled_back = ConfigurationService.rollback(
        tenant_a.id, 1, actor_id=actor_id, correlation_id="corr-rollback", reason="Restore baseline"
    )
    assert rolled_back.version == 3
    assert rolled_back.document["limits"]["audit_default_window_days"] == 30
    evidence = SecurityConfigurationVersion.objects.for_tenant(tenant_a.id).get(version=2)
    assert evidence.previous_document["limits"]["audit_default_window_days"] == 30
    assert evidence.current_document["limits"]["audit_default_window_days"] == 14
    assert evidence.correlation_id == "corr-update"
    audit = SecurityAuditLog.objects.for_tenant(tenant_a.id).get(correlation_id="corr-update")
    outbox = OutboxEvent.objects.get(pk=audit.outbox_event_id)
    assert outbox.payload["correlation_id"] == "corr-update"
    assert audit.details == {"operation": "update", "version": 2}
    evidence.reason = "tamper"
    with pytest.raises(ImmutableConfigurationError):
        evidence.save()


def test_configuration_rejects_unsafe_limits_and_baseline(tenant_a, actor_id, correlation_id) -> None:
    current = ConfigurationService.current(tenant_a.id, actor_id=actor_id, correlation_id=correlation_id)
    invalid = default_security_configuration()
    invalid["limits"]["audit_default_window_days"] = 91
    invalid["limits"]["audit_max_window_days"] = 90
    with pytest.raises(SecurityValidationError):
        ConfigurationService.preview(current, document=invalid)
    fail_open = default_security_configuration()
    fail_open["baseline_profile"]["download_allowed"] = True
    with pytest.raises(SecurityValidationError):
        ConfigurationService.preview(current, document=fail_open)


def test_configuration_api_preview_update_replay_export_versions_and_rollback(
    authenticated_tenant_a_client,
) -> None:
    current = _data(authenticated_tenant_a_client.get(f"{BASE}/"))
    document = current["document"]
    document["ui"]["loading_skeleton_rows"] = 8
    preview = _data(
        authenticated_tenant_a_client.post(
            f"{BASE}/preview/", {"document": document}, format="json"
        )
    )
    assert preview["valid"] is True and any(item["path"] == "ui.loading_skeleton_rows" for item in preview["diff"])
    body = {
        "environment": "development",
        "document": document,
        "rollout": current["rollout"],
        "reason": "Tune loading feedback",
    }
    first = authenticated_tenant_a_client.put(
        f"{BASE}/", body, format="json", HTTP_IDEMPOTENCY_KEY="config-update-1"
    )
    second = authenticated_tenant_a_client.put(
        f"{BASE}/", body, format="json", HTTP_IDEMPOTENCY_KEY="config-update-1"
    )
    assert _data(first)["version"] == 2
    assert _data(second)["version"] == 2
    assert MutationReplay.objects.count() == 1
    exported = _data(authenticated_tenant_a_client.get(f"{BASE}/export/"))
    assert exported["schema_version"] == "1.0" and exported["document"] == document
    versions = _data(authenticated_tenant_a_client.get(f"{BASE}/versions/"))
    assert [item["version"] for item in versions] == [2, 1]
    rollback = authenticated_tenant_a_client.post(
        f"{BASE}/versions/1/rollback/",
        {"reason": "Return to baseline"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="config-rollback-1",
    )
    assert _data(rollback)["version"] == 3
    missing_key = authenticated_tenant_a_client.put(f"{BASE}/", body, format="json")
    assert missing_key.status_code == 400


def test_idempotency_key_cannot_be_reused_for_different_configuration_request(
    authenticated_tenant_a_client,
) -> None:
    current = _data(authenticated_tenant_a_client.get(f"{BASE}/"))
    body = {
        "environment": current["environment"],
        "document": current["document"],
        "rollout": current["rollout"],
        "reason": "First request",
    }
    assert authenticated_tenant_a_client.put(
        f"{BASE}/", body, format="json", HTTP_IDEMPOTENCY_KEY="same-key"
    ).status_code == 200
    body["reason"] = "Different request"
    conflict = authenticated_tenant_a_client.put(
        f"{BASE}/", body, format="json", HTTP_IDEMPOTENCY_KEY="same-key"
    )
    assert conflict.status_code == 409
