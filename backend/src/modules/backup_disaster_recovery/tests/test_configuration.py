"""Configuration-first contracts for tenant disaster-recovery policy."""

from __future__ import annotations

import copy
import uuid
from typing import Any

import pytest
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessDecisionPipeline, AccessReasonCode

from ..models import BDRConfiguration, BDRConfigurationVersion
from ..services import (
    BDRDomainError,
    ConfigurationService,
    ResourceNotFound,
    get_configuration,
)

pytest_plugins = ["src.core.testing"]

PREFIX = "/api/v2/backup-disaster-recovery/configurations"


@pytest.fixture(autouse=True)
def allow_access(monkeypatch):
    def decide(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(
            True,
            AccessReasonCode.ALLOW,
            "allowed",
            tenant_id=uuid.UUID(str(tenant_id)),
        )

    monkeypatch.setattr(AccessDecisionPipeline, "decide", decide)


def _document(tenant_id: uuid.UUID) -> dict[str, Any]:
    return copy.deepcopy(get_configuration(tenant_id).document)


@pytest.mark.django_db
def test_missing_configuration_uses_complete_strict_defaults() -> None:
    tenant_id = uuid.uuid4()

    configuration = get_configuration(tenant_id)

    assert configuration._state.adding is True
    assert configuration.tenant_id == tenant_id
    assert configuration.version == 0
    assert set(configuration.document["quota_costs"]) == {
        "default",
        "backup_execution",
        "verification",
        "restore_validation",
        "restore_execution",
        "exercise_execution",
    }
    assert all(value > 0 for value in configuration.document["quota_costs"].values())


@pytest.mark.django_db
def test_malformed_persisted_configuration_fails_closed() -> None:
    tenant_id = uuid.uuid4()
    BDRConfiguration.objects.create(
        tenant_id=tenant_id,
        environment="default",
        document={"quota_costs": {"default": 1}},
        rollout={"enabled": True, "roles": [], "cohorts": []},
    )

    with pytest.raises(BDRDomainError, match="invalid keys"):
        get_configuration(tenant_id)


@pytest.mark.django_db
def test_preview_validates_and_never_mutates() -> None:
    tenant_id = uuid.uuid4()
    document = _document(tenant_id)
    document["reports"]["default_interval_days"] = 14

    preview = ConfigurationService().preview(tenant_id, document)

    assert preview["valid"] is True
    assert {change["path"] for change in preview["changes"]} == {"document.reports.default_interval_days"}
    assert not BDRConfiguration.objects.for_tenant(tenant_id).exists()
    assert not BDRConfigurationVersion.objects.for_tenant(tenant_id).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document["steps"].update({"min_timeout_seconds": 500, "default_timeout_seconds": 300}),
        lambda document: document["reports"].update({"default_bucket": "year"}),
        lambda document: document["providers"].update({"storage_adapter_key": ""}),
        lambda document: document["quota_costs"].update({"restore_execution": 0}),
    ],
)
def test_invalid_configuration_is_unsavable(mutate) -> None:
    tenant_id = uuid.uuid4()
    document = _document(tenant_id)
    mutate(document)

    with pytest.raises(BDRDomainError, match="configuration|limits|allowed|empty|positive"):
        ConfigurationService().update(
            tenant_id,
            uuid.uuid4(),
            uuid.uuid4(),
            document,
        )

    assert not BDRConfiguration.objects.for_tenant(tenant_id).exists()
    assert not BDRConfigurationVersion.objects.for_tenant(tenant_id).exists()


@pytest.mark.django_db
def test_update_versions_and_rollback_preserve_full_audit_ancestry() -> None:
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    service = ConfigurationService()
    first_document = _document(tenant_id)
    first_document["reports"]["default_interval_days"] = 14
    first_correlation = uuid.uuid4()

    first = service.update(tenant_id, actor_id, first_correlation, first_document)
    second_document = copy.deepcopy(first.document)
    second_document["reports"]["default_interval_days"] = 60
    second_correlation = uuid.uuid4()
    second = service.update(tenant_id, actor_id, second_correlation, second_document)
    rollback_correlation = uuid.uuid4()
    rolled_back = service.rollback(
        tenant_id,
        actor_id,
        rollback_correlation,
        version=1,
    )

    assert first.version == 1
    assert second.version == 2
    assert rolled_back.version == 3
    assert rolled_back.document["reports"]["default_interval_days"] == 14
    versions = list(service.versions(tenant_id).order_by("version"))
    assert [row.version for row in versions] == [1, 2, 3]
    assert [row.correlation_id for row in versions] == [
        first_correlation,
        second_correlation,
        rollback_correlation,
    ]
    assert all(row.actor_id == actor_id for row in versions)
    assert versions[0].prior_value == {}
    assert versions[0].new_value["document"] == first_document
    assert versions[1].prior_value["document"] == first_document
    assert versions[1].new_value["document"] == second_document
    assert versions[2].rollback_of_id == versions[0].id
    assert versions[2].prior_value["document"] == second_document
    assert versions[2].new_value["document"] == first_document


@pytest.mark.django_db
def test_import_export_are_transactional_and_tenant_isolated() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    service = ConfigurationService()
    document_a = _document(tenant_a)
    document_a["reports"]["default_interval_days"] = 7
    config_a = service.update(tenant_a, uuid.uuid4(), uuid.uuid4(), document_a)
    exported = service.export_document(tenant_a)

    imported = service.import_document(
        tenant_b,
        uuid.uuid4(),
        uuid.uuid4(),
        {**exported, "tenant_id": str(tenant_a)},
    )

    assert imported.tenant_id == tenant_b
    assert imported.document == config_a.document
    assert BDRConfiguration.objects.for_tenant(tenant_a).get().id == config_a.id
    assert BDRConfiguration.objects.for_tenant(tenant_b).get().id == imported.id
    assert imported.id != config_a.id

    invalid = copy.deepcopy(exported)
    invalid["document"]["reports"]["default_bucket"] = "year"
    before_config = BDRConfiguration.objects.for_tenant(tenant_b).get()
    before_versions = list(BDRConfigurationVersion.objects.for_tenant(tenant_b).values_list("id", flat=True))
    with pytest.raises(BDRDomainError):
        service.import_document(tenant_b, uuid.uuid4(), uuid.uuid4(), invalid)
    after_config = BDRConfiguration.objects.for_tenant(tenant_b).get()
    assert after_config.version == before_config.version
    assert after_config.document == before_config.document
    assert list(BDRConfigurationVersion.objects.for_tenant(tenant_b).values_list("id", flat=True)) == before_versions


@pytest.mark.django_db
def test_cross_tenant_version_cannot_be_rolled_back() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    service = ConfigurationService()
    document_b = _document(tenant_b)
    service.update(tenant_b, uuid.uuid4(), uuid.uuid4(), document_b)
    document_b["reports"]["default_interval_days"] = 15
    service.update(tenant_b, uuid.uuid4(), uuid.uuid4(), document_b)

    with pytest.raises(ResourceNotFound):
        service.rollback(tenant_a, uuid.uuid4(), uuid.uuid4(), version=2)

    assert not BDRConfiguration.objects.for_tenant(tenant_a).exists()
    assert BDRConfiguration.objects.for_tenant(tenant_b).get().version == 2


@pytest.mark.django_db
def test_configuration_current_detail_and_unsupported_verbs_are_tenant_isolated(
    authenticated_tenant_a_client, tenant_a, tenant_b
) -> None:
    service = ConfigurationService()
    document_a = _document(tenant_a.id)
    document_a["reports"]["default_interval_days"] = 11
    config_a = service.update(tenant_a.id, uuid.uuid4(), uuid.uuid4(), document_a)
    document_b = _document(tenant_b.id)
    document_b["reports"]["default_interval_days"] = 22
    config_b = service.update(tenant_b.id, uuid.uuid4(), uuid.uuid4(), document_b)

    current = authenticated_tenant_a_client.get(f"{PREFIX}/current/")
    assert current.status_code == status.HTTP_200_OK
    current_payload = current.json()["data"]
    assert current_payload["id"] == str(config_a.id)
    assert current_payload["tenant_id"] == str(tenant_a.id)
    assert current_payload["document"]["reports"]["default_interval_days"] == 11

    before_b = BDRConfiguration.objects.get(pk=config_b.id)
    detail = f"{PREFIX}/{config_b.id}/"
    responses = (
        authenticated_tenant_a_client.get(detail),
        authenticated_tenant_a_client.patch(detail, {"document": document_a}, format="json"),
        authenticated_tenant_a_client.delete(detail),
    )
    assert all(
        response.status_code
        in {status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED}
        for response in responses
    )
    config_b.refresh_from_db()
    assert config_b.version == before_b.version
    assert config_b.document == before_b.document

    collection_responses = (
        authenticated_tenant_a_client.get(f"{PREFIX}/"),
        authenticated_tenant_a_client.post(f"{PREFIX}/", {}, format="json"),
        authenticated_tenant_a_client.delete(f"{PREFIX}/"),
    )
    assert all(
        response.status_code in {status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED}
        for response in collection_responses
    )


@pytest.mark.django_db
def test_configuration_patch_preview_versions_rollback_import_export_api(
    authenticated_tenant_a_client, tenant_a, tenant_b
) -> None:
    service = ConfigurationService()
    document_b = _document(tenant_b.id)
    document_b["reports"]["default_interval_days"] = 77
    config_b = service.update(tenant_b.id, uuid.uuid4(), uuid.uuid4(), document_b)
    proposed = _document(tenant_a.id)
    proposed["reports"]["default_interval_days"] = 8

    preview = authenticated_tenant_a_client.post(
        f"{PREFIX}/preview/",
        {"document": proposed},
        format="json",
    )
    assert preview.status_code == status.HTTP_200_OK
    assert preview.json()["data"]["valid"] is True
    assert not BDRConfiguration.objects.for_tenant(tenant_a.id).exists()

    first_correlation = uuid.uuid4()
    saved = authenticated_tenant_a_client.patch(
        f"{PREFIX}/current/",
        {"tenant_id": str(tenant_b.id), "document": proposed},
        format="json",
        HTTP_X_CORRELATION_ID=str(first_correlation),
    )
    assert saved.status_code == status.HTTP_200_OK
    config_a = BDRConfiguration.objects.for_tenant(tenant_a.id).get()
    assert saved.json()["data"]["id"] == str(config_a.id)
    assert config_a.document["reports"]["default_interval_days"] == 8
    config_b.refresh_from_db()
    assert config_b.document["reports"]["default_interval_days"] == 77
    first_version = BDRConfigurationVersion.objects.for_tenant(tenant_a.id).get()
    assert first_version.correlation_id == first_correlation

    proposed_again = copy.deepcopy(proposed)
    proposed_again["reports"]["default_interval_days"] = 9
    second_correlation = uuid.uuid4()
    updated = authenticated_tenant_a_client.patch(
        f"{PREFIX}/current/",
        {"document": proposed_again},
        format="json",
        HTTP_X_CORRELATION_ID=str(second_correlation),
    )
    assert updated.status_code == status.HTTP_200_OK

    versions = authenticated_tenant_a_client.get(f"{PREFIX}/versions/")
    assert versions.status_code == status.HTTP_200_OK
    version_payloads = versions.json()["data"]
    assert [row["version"] for row in version_payloads] == [2, 1]
    assert {row["correlation_id"] for row in version_payloads} == {
        str(first_correlation),
        str(second_correlation),
    }
    assert all(row["new_value"]["document"] != document_b for row in version_payloads)

    export_response = authenticated_tenant_a_client.get(f"{PREFIX}/export-document/")
    assert export_response.status_code == status.HTTP_200_OK
    exported = export_response.json()["data"]
    assert exported["document"] == proposed_again
    assert "tenant_id" not in exported

    rollback_correlation = uuid.uuid4()
    rollback = authenticated_tenant_a_client.post(
        f"{PREFIX}/rollback/",
        {"version": 1},
        format="json",
        HTTP_X_CORRELATION_ID=str(rollback_correlation),
    )
    assert rollback.status_code == status.HTTP_200_OK
    assert rollback.json()["data"]["version"] == 3
    assert rollback.json()["data"]["document"] == proposed
    rollback_version = BDRConfigurationVersion.objects.for_tenant(tenant_a.id).get(version=3)
    assert rollback_version.rollback_of_id == first_version.id
    assert rollback_version.correlation_id == rollback_correlation

    imported_document = copy.deepcopy(proposed)
    imported_document["reports"]["default_interval_days"] = 10
    import_correlation = uuid.uuid4()
    imported = authenticated_tenant_a_client.post(
        f"{PREFIX}/import-document/",
        {
            "tenant_id": str(tenant_b.id),
            "environment": "default",
            "document": imported_document,
            "rollout": {"enabled": True, "roles": ["operator"], "cohorts": []},
        },
        format="json",
        HTTP_X_CORRELATION_ID=str(import_correlation),
    )
    assert imported.status_code == status.HTTP_200_OK
    assert imported.json()["data"]["tenant_id"] == str(tenant_a.id)
    config_b.refresh_from_db()
    assert config_b.document["reports"]["default_interval_days"] == 77
    assert BDRConfigurationVersion.objects.for_tenant(tenant_a.id).get(version=4).correlation_id == import_correlation


@pytest.mark.django_db
def test_configuration_api_cannot_rollback_another_tenants_version(
    authenticated_tenant_a_client, tenant_a, tenant_b
) -> None:
    service = ConfigurationService()
    document_b = _document(tenant_b.id)
    service.update(tenant_b.id, uuid.uuid4(), uuid.uuid4(), document_b)
    document_b["reports"]["default_interval_days"] = 31
    service.update(tenant_b.id, uuid.uuid4(), uuid.uuid4(), document_b)
    before_b = BDRConfiguration.objects.for_tenant(tenant_b.id).get()

    response = authenticated_tenant_a_client.post(f"{PREFIX}/rollback/", {"version": 2}, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert not BDRConfiguration.objects.for_tenant(tenant_a.id).exists()
    after_b = BDRConfiguration.objects.for_tenant(tenant_b.id).get()
    assert after_b.version == before_b.version
    assert after_b.document == before_b.document
