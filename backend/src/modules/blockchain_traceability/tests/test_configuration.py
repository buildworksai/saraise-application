"""Configuration-first service, model, API, and tenant-isolation proof."""

from __future__ import annotations

from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.modules.blockchain_traceability.models import (
    BlockchainTraceabilityConfiguration,
    BlockchainTraceabilityConfigurationAudit,
    BlockchainTraceabilityConfigurationVersion,
    ImmutableEvidenceError,
)
from src.modules.blockchain_traceability.services import (
    DEFAULT_CONFIGURATION,
    BlockchainTraceabilityConfigurationService,
    BlockchainTraceabilityError,
)

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db

BASE_URL = "/api/v2/blockchain-traceability/configuration/"


def _success_data(response):
    """Read the repository-wide governed API v2 success envelope."""

    return response.json()["data"]


@pytest.fixture(autouse=True)
def allow_declared_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise real session and CSRF handling without remote policy I/O."""

    def allow(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="test policy allows the declared configuration capability",
            tenant_id=UUID(str(tenant_id)),
            remaining_quota=100,
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", allow)


def _document(**section_overrides) -> dict[str, object]:
    document = deepcopy(DEFAULT_CONFIGURATION)
    for section, values in section_overrides.items():
        document[section].update(values)
    return document


def test_current_creates_one_default_with_matching_initial_version_and_audit(tenant_a) -> None:
    service = BlockchainTraceabilityConfigurationService()

    current = service.current(tenant_a.id)
    replay = service.current(tenant_a.id)

    assert replay.pk == current.pk
    assert current.version == 1
    assert current.document == DEFAULT_CONFIGURATION
    assert current.created_by == "system:configuration-default"
    version = BlockchainTraceabilityConfigurationVersion.objects.get(
        tenant_id=tenant_a.id,
        environment="default",
        version=1,
    )
    audit = BlockchainTraceabilityConfigurationAudit.objects.get(
        tenant_id=tenant_a.id,
        environment="default",
        to_version=1,
    )
    assert version.document == current.document
    assert version.change_type == "initialize"
    assert audit.action == "initialize"
    assert audit.from_version is None
    assert audit.before == {}
    assert audit.after == current.document
    assert version.correlation_id == audit.correlation_id
    assert version.correlation_id
    assert BlockchainTraceabilityConfiguration.objects.filter(tenant_id=tenant_a.id).count() == 1
    assert BlockchainTraceabilityConfigurationVersion.objects.filter(tenant_id=tenant_a.id).count() == 1
    assert BlockchainTraceabilityConfigurationAudit.objects.filter(tenant_id=tenant_a.id).count() == 1


@pytest.mark.parametrize(
    ("section", "field", "unsafe_value"),
    [
        ("validation", "max_json_bytes", 1_048_577),
        ("validation", "max_json_depth", 51),
        ("validation", "max_json_keys", 10_001),
        ("network_policy", "max_confirmation_depth", 65_536),
        ("list_policy", "max_page_size", 501),
        ("resilience", "timeout_seconds", 120.1),
        ("credential_policy", "token_entropy_bytes", 31),
    ],
)
def test_service_rejects_values_above_or_below_platform_safe_limits(
    tenant_a,
    section: str,
    field: str,
    unsafe_value: object,
) -> None:
    service = BlockchainTraceabilityConfigurationService()
    current = service.current(tenant_a.id)
    invalid = deepcopy(current.document)
    invalid[section][field] = unsafe_value

    with pytest.raises(BlockchainTraceabilityError) as raised:
        service.update(tenant_a.id, "operator:a", invalid)

    assert raised.value.error_code == "invalid_configuration"
    current.refresh_from_db()
    assert current.version == 1
    assert BlockchainTraceabilityConfigurationVersion.objects.filter(tenant_id=tenant_a.id).count() == 1
    assert BlockchainTraceabilityConfigurationAudit.objects.filter(tenant_id=tenant_a.id).count() == 1


def test_update_records_correlated_append_only_version_and_audit(monkeypatch, tenant_a) -> None:
    service = BlockchainTraceabilityConfigurationService()
    current = service.current(tenant_a.id)
    before = deepcopy(current.document)
    correlation_id = str(uuid4())
    monkeypatch.setattr("src.modules.blockchain_traceability.services.get_correlation_id", lambda: correlation_id)

    updated = service.update(
        tenant_a.id,
        "operator:a",
        _document(list_policy={"default_page_size": 40}),
    )

    assert updated.version == 2
    version = BlockchainTraceabilityConfigurationVersion.objects.get(tenant_id=tenant_a.id, version=2)
    audit = BlockchainTraceabilityConfigurationAudit.objects.get(tenant_id=tenant_a.id, to_version=2)
    assert version.correlation_id == correlation_id
    assert audit.correlation_id == correlation_id
    assert version.created_by == "operator:a"
    assert audit.changed_by == "operator:a"
    assert audit.from_version == 1
    assert audit.before == before
    assert audit.after == updated.document

    version.document = {}
    with pytest.raises(ImmutableEvidenceError, match="cannot be updated"):
        version.save()
    with pytest.raises(ImmutableEvidenceError, match="cannot be updated"):
        BlockchainTraceabilityConfigurationVersion.objects.filter(pk=version.pk).update(change_type="tampered")
    with pytest.raises(ImmutableEvidenceError, match="cannot be deleted"):
        audit.delete()
    with pytest.raises(ImmutableEvidenceError, match="cannot be deleted"):
        BlockchainTraceabilityConfigurationAudit.objects.filter(pk=audit.pk).delete()


def test_rollback_creates_a_new_revision_without_rewriting_history(tenant_a) -> None:
    service = BlockchainTraceabilityConfigurationService()
    initial = deepcopy(service.current(tenant_a.id).document)
    service.update(tenant_a.id, "operator:a", _document(list_policy={"default_page_size": 40}))
    service.update(tenant_a.id, "operator:a", _document(list_policy={"default_page_size": 60}))

    rolled_back = service.rollback(tenant_a.id, "reviewer:a", version=1)

    assert rolled_back.version == 4
    assert rolled_back.document == initial
    assert list(service.history(tenant_a.id).values_list("version", flat=True)) == [4, 3, 2, 1]
    rollback_audit = BlockchainTraceabilityConfigurationAudit.objects.get(tenant_id=tenant_a.id, to_version=4)
    assert rollback_audit.action == "rollback"
    assert rollback_audit.from_version == 3
    assert rollback_audit.changed_by == "reviewer:a"
    assert rollback_audit.after == initial


def test_export_is_detached_and_import_is_validated_versioned_and_audited(tenant_a) -> None:
    service = BlockchainTraceabilityConfigurationService()
    service.current(tenant_a.id)
    exported = service.export_document(tenant_a.id)
    exported["document"]["list_policy"]["default_page_size"] = 35

    assert service.current(tenant_a.id).document["list_policy"]["default_page_size"] == 25
    imported = service.import_document(tenant_a.id, "promoter:a", exported, environment="staging")

    assert imported.environment == "staging"
    assert imported.version == 2
    assert imported.document["list_policy"]["default_page_size"] == 35
    imported_audit = BlockchainTraceabilityConfigurationAudit.objects.get(
        tenant_id=tenant_a.id,
        environment="staging",
        to_version=2,
    )
    assert imported_audit.action == "import"
    assert imported_audit.changed_by == "promoter:a"
    round_trip = service.export_document(tenant_a.id, environment="staging")
    assert round_trip == {
        "schema": "saraise.blockchain_traceability.configuration/v1",
        "environment": "staging",
        "version": 2,
        "document": imported.document,
    }

    malformed = deepcopy(round_trip)
    malformed["unexpected"] = True
    with pytest.raises(BlockchainTraceabilityError) as raised:
        service.import_document(tenant_a.id, "promoter:a", malformed, environment="staging")
    assert raised.value.error_code == "invalid_configuration_import"
    imported.refresh_from_db()
    assert imported.version == 2


def test_configuration_api_delegates_server_validation_and_propagates_correlation(
    authenticated_tenant_a_client,
    tenant_a,
) -> None:
    initial_response = authenticated_tenant_a_client.get(BASE_URL)
    assert initial_response.status_code == status.HTTP_200_OK
    initial = _success_data(initial_response)
    assert initial["tenant_id"] == str(tenant_a.id)
    assert initial["version"] == 1

    invalid = deepcopy(initial["document"])
    invalid["validation"]["max_json_bytes"] = 1_048_577
    rejected = authenticated_tenant_a_client.put(
        f"{BASE_URL}current/",
        {"environment": "default", "document": invalid},
        format="json",
    )
    assert rejected.status_code == status.HTTP_400_BAD_REQUEST
    assert rejected.json()["error"]["code"] == "invalid_configuration"
    assert BlockchainTraceabilityConfiguration.objects.get(tenant_id=tenant_a.id).version == 1

    correlation_id = str(uuid4())
    valid = deepcopy(initial["document"])
    valid["list_policy"]["default_page_size"] = 45
    accepted = authenticated_tenant_a_client.put(
        f"{BASE_URL}current/",
        {"environment": "default", "document": valid},
        format="json",
        HTTP_X_CORRELATION_ID=correlation_id,
    )
    assert accepted.status_code == status.HTTP_200_OK
    assert _success_data(accepted)["version"] == 2
    assert (
        BlockchainTraceabilityConfigurationVersion.objects.get(
            tenant_id=tenant_a.id,
            version=2,
        ).correlation_id
        == correlation_id
    )
    assert (
        BlockchainTraceabilityConfigurationAudit.objects.get(
            tenant_id=tenant_a.id,
            to_version=2,
        ).correlation_id
        == correlation_id
    )


def test_configuration_api_preview_history_rollback_and_import_export(
    authenticated_tenant_a_client,
    tenant_a,
) -> None:
    current = _success_data(authenticated_tenant_a_client.get(BASE_URL))
    candidate = deepcopy(current["document"])
    candidate["list_policy"]["default_page_size"] = 30

    preview = authenticated_tenant_a_client.post(
        f"{BASE_URL}preview/",
        {"environment": "default", "document": candidate},
        format="json",
    )
    assert preview.status_code == status.HTTP_200_OK
    assert _success_data(preview)["valid"] is True
    assert _success_data(preview)["changes"] == [{"path": "list_policy.default_page_size", "before": 25, "after": 30}]
    assert BlockchainTraceabilityConfiguration.objects.get(tenant_id=tenant_a.id).version == 1

    exported = authenticated_tenant_a_client.get(f"{BASE_URL}export-document/")
    assert exported.status_code == status.HTTP_200_OK
    import_payload = _success_data(exported)
    import_payload["environment"] = "staging"
    import_payload["document"]["list_policy"]["default_page_size"] = 30
    imported = authenticated_tenant_a_client.post(
        f"{BASE_URL}import-document/",
        import_payload,
        format="json",
    )
    assert imported.status_code == status.HTTP_200_OK
    assert _success_data(imported)["environment"] == "staging"
    assert _success_data(imported)["version"] == 2

    history = authenticated_tenant_a_client.get(f"{BASE_URL}history/?environment=staging")
    assert history.status_code == status.HTTP_200_OK
    assert [row["change_type"] for row in _success_data(history)] == ["import", "initialize"]
    rollback = authenticated_tenant_a_client.post(
        f"{BASE_URL}rollback/",
        {"environment": "staging", "version": 1},
        format="json",
    )
    assert rollback.status_code == status.HTTP_200_OK
    assert _success_data(rollback)["version"] == 3
    assert _success_data(rollback)["document"] == current["document"]
    assert (
        BlockchainTraceabilityConfigurationAudit.objects.get(
            tenant_id=tenant_a.id,
            environment="staging",
            to_version=3,
        ).action
        == "rollback"
    )


def test_configuration_config_version_and_audit_are_cross_tenant_isolated(
    authenticated_tenant_a_client,
    tenant_a,
    tenant_b,
) -> None:
    service = BlockchainTraceabilityConfigurationService()
    config_a = service.current(tenant_a.id)
    service.current(tenant_b.id)
    service.update(tenant_b.id, "operator:b", _document(list_policy={"default_page_size": 35}))
    config_b = service.update(
        tenant_b.id,
        "operator:b",
        _document(list_policy={"default_page_size": 55}),
    )

    assert config_a.tenant_id != config_b.tenant_id
    assert config_b.version == 3
    assert set(service.history(tenant_a.id).values_list("tenant_id", flat=True)) == {tenant_a.id}
    assert set(service.history(tenant_b.id).values_list("tenant_id", flat=True)) == {tenant_b.id}
    assert not BlockchainTraceabilityConfiguration.objects.filter(
        tenant_id=tenant_a.id,
        id=config_b.id,
    ).exists()
    assert not BlockchainTraceabilityConfigurationVersion.objects.filter(
        tenant_id=tenant_a.id,
        id__in=service.history(tenant_b.id).values("id"),
    ).exists()
    tenant_b_audit_ids = BlockchainTraceabilityConfigurationAudit.objects.filter(tenant_id=tenant_b.id).values("id")
    assert not BlockchainTraceabilityConfigurationAudit.objects.filter(
        tenant_id=tenant_a.id,
        id__in=tenant_b_audit_ids,
    ).exists()

    current_response = authenticated_tenant_a_client.get(BASE_URL)
    assert current_response.status_code == status.HTTP_200_OK
    assert _success_data(current_response)["id"] == str(config_a.id)
    assert _success_data(current_response)["document"]["list_policy"]["default_page_size"] == 25
    history_response = authenticated_tenant_a_client.get(f"{BASE_URL}history/")
    assert history_response.status_code == status.HTTP_200_OK
    assert [row["version"] for row in _success_data(history_response)] == [1]

    cross_tenant_rollback = authenticated_tenant_a_client.post(
        f"{BASE_URL}rollback/",
        {"environment": "default", "version": 3},
        format="json",
    )
    assert cross_tenant_rollback.status_code == status.HTTP_404_NOT_FOUND
    config_b.refresh_from_db()
    assert config_b.version == 3
    assert config_b.document["list_policy"]["default_page_size"] == 55
