"""Tenant configuration, audit, rollback, and API contract tests."""

from __future__ import annotations

from copy import deepcopy
import uuid

import pytest
from django.core.exceptions import ValidationError

from src.core.access.decision import AccessDecision, AccessDecisionPipeline, AccessReasonCode
from src.modules.master_data_management.models import MasterDataConfigurationVersion
from src.modules.master_data_management.services import ConfigurationService, MDMDomainError

from .factories import actor_id

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db

BASE = "/api/v2/master-data-management/configurations"


@pytest.fixture(autouse=True)
def allow_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def decide(
        self: AccessDecisionPipeline,
        tenant_id: object,
        identity: object,
        required_permission: str,
        **kwargs: object,
    ) -> AccessDecision:
        del self, identity, required_permission, kwargs
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="configuration test access",
            tenant_id=uuid.UUID(str(tenant_id)),
        )

    monkeypatch.setattr(AccessDecisionPipeline, "decide", decide)


def write_configuration(
    tenant_id: uuid.UUID,
    *,
    key: str,
    document: dict[str, object] | None = None,
):
    return ConfigurationService.write(
        tenant_id,
        actor_id(),
        document=document or ConfigurationService.defaults(),
        idempotency_key=key,
        reason="Configuration test mutation.",
    )


def test_configuration_write_is_versioned_audited_and_idempotent() -> None:
    tenant = uuid.uuid4()
    current = write_configuration(tenant, key="config-v1")
    replay = write_configuration(tenant, key="config-v1")

    assert replay.id == current.id
    assert replay.version == 1
    audit = MasterDataConfigurationVersion.objects.for_tenant(tenant).get()
    assert audit.actor_id == actor_id()
    assert audit.correlation_id
    assert audit.prior_value == {}
    assert audit.new_value == current.document


def test_configuration_rejects_invalid_safe_limits_before_persistence() -> None:
    tenant = uuid.uuid4()
    invalid = ConfigurationService.defaults()
    invalid["limits"]["entity_name_max"] = 256  # type: ignore[index]

    with pytest.raises(MDMDomainError) as caught:
        write_configuration(tenant, key="invalid-limit", document=invalid)

    assert caught.value.error_code == "INVALID_CONFIGURATION"
    assert not MasterDataConfigurationVersion.objects.for_tenant(tenant).exists()


def test_configuration_preview_and_rollback_create_real_versions() -> None:
    tenant = uuid.uuid4()
    first = write_configuration(tenant, key="config-first")
    changed = deepcopy(first.document)
    changed["dashboard"]["trend_window_days"] = 45  # type: ignore[index]
    preview = ConfigurationService.preview(tenant, changed)
    assert preview["valid"] is True
    assert any(
        item["path"] == "dashboard.trend_window_days"
        for item in preview["changes"]  # type: ignore[union-attr]
    )

    second = ConfigurationService.write(
        tenant,
        actor_id(),
        document=changed,
        expected_version=1,
        idempotency_key="config-second",
        reason="Change trend window.",
    )
    restored = ConfigurationService.rollback(
        tenant,
        actor_id(),
        version=1,
        idempotency_key="config-rollback",
        reason="Restore the prior version.",
    )

    assert second.version == 2
    assert restored.version == 3
    assert restored.document == first.document
    assert list(
        MasterDataConfigurationVersion.objects.for_tenant(tenant)
        .order_by("version")
        .values_list("change_type", flat=True)
    ) == ["update", "update", "rollback"]


def test_configuration_audit_is_immutable() -> None:
    tenant = uuid.uuid4()
    write_configuration(tenant, key="immutable-config")
    audit = MasterDataConfigurationVersion.objects.for_tenant(tenant).get()

    audit.reason = "tampered"
    with pytest.raises(ValidationError, match="append-only"):
        audit.save()
    with pytest.raises(ValidationError, match="append-only"):
        MasterDataConfigurationVersion.objects.for_tenant(tenant).update(reason="tampered")


def test_configuration_api_materializes_real_defaults_and_supports_portability(
    authenticated_tenant_a_client: object,
    tenant_a: object,
) -> None:
    response = authenticated_tenant_a_client.get(f"{BASE}/")  # type: ignore[attr-defined]
    assert response.status_code == 200
    current = response.json()["data"]
    assert current["id"]
    assert current["version"] == 1
    assert current["tenant_id"] == str(tenant_a.id)  # type: ignore[attr-defined]

    preview = authenticated_tenant_a_client.post(  # type: ignore[attr-defined]
        f"{BASE}/preview/",
        {"document": current["document"]},
        format="json",
    )
    assert preview.status_code == 200
    assert preview.json()["data"]["valid"] is True

    exported = authenticated_tenant_a_client.get(f"{BASE}/export/")  # type: ignore[attr-defined]
    assert exported.status_code == 200
    assert exported.json()["data"]["configuration_version"] == 1
    history = authenticated_tenant_a_client.get(f"{BASE}/history/")  # type: ignore[attr-defined]
    assert history.status_code == 200
    assert len(history.json()["data"]) == 1


def test_configuration_api_prevents_cross_tenant_reads(
    authenticated_tenant_a_client: object,
    tenant_a: object,
    tenant_b: object,
) -> None:
    foreign = write_configuration(tenant_b.id, key="foreign-config")  # type: ignore[attr-defined]
    response = authenticated_tenant_a_client.get(f"{BASE}/{foreign.id}/")  # type: ignore[attr-defined]
    assert response.status_code == 404

    own = authenticated_tenant_a_client.get(f"{BASE}/")  # type: ignore[attr-defined]
    assert own.status_code == 200
    assert own.json()["data"]["tenant_id"] == str(tenant_a.id)  # type: ignore[attr-defined]
    assert own.json()["data"]["id"] != str(foreign.id)
