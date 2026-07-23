"""Proof of tenant-isolated, reversible, and auditable HR configuration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast
from uuid import uuid4

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from ..api import HumanResourcesConfigurationViewSet
from ..models import (
    HumanResourcesConfiguration,
    HumanResourcesConfigurationAudit,
    HumanResourcesConfigurationVersion,
)
from ..services import (
    HRConflictError,
    HRValidationError,
    HumanResourcesConfigurationService,
)

pytestmark = pytest.mark.django_db


def _document(**limit_changes: object) -> dict[str, object]:
    document = HumanResourcesConfigurationService.default_document()
    limits = cast(dict[str, object], document["limits"])
    limits.update(limit_changes)
    return document


def _response_data(response: Any) -> Any:
    payload = response.json()
    assert set(payload) == {"data", "meta"}
    assert payload["meta"]["correlation_id"]
    return payload["data"]


def test_configuration_bootstrap_is_tenant_partitioned_and_audited(tenant_a: Any, tenant_b: Any) -> None:
    configuration_a = HumanResourcesConfigurationService.ensure_configuration(tenant_a.id)
    configuration_b = HumanResourcesConfigurationService.ensure_configuration(tenant_b.id)

    assert configuration_a.tenant_id == tenant_a.id
    assert configuration_b.tenant_id == tenant_b.id
    assert configuration_a.id != configuration_b.id
    assert HumanResourcesConfiguration.objects.for_tenant(tenant_a.id).count() == 1
    assert HumanResourcesConfiguration.objects.for_tenant(tenant_b.id).count() == 1

    version_a = HumanResourcesConfigurationVersion.objects.for_tenant(tenant_a.id).get()
    audit_a = HumanResourcesConfigurationAudit.objects.for_tenant(tenant_a.id).get()
    assert version_a.configuration_id == configuration_a.id
    assert version_a.version == 1
    assert version_a.document == configuration_a.document
    assert version_a.correlation_id
    assert audit_a.configuration_id == configuration_a.id
    assert audit_a.action == "bootstrap"
    assert audit_a.before_document is None
    assert audit_a.after_document == configuration_a.document
    assert audit_a.actor_id == "system:configuration-bootstrap"
    assert audit_a.correlation_id == version_a.correlation_id

    assert (
        not HumanResourcesConfigurationVersion.objects.for_tenant(tenant_a.id)
        .filter(configuration_id=configuration_b.id)
        .exists()
    )
    assert (
        not HumanResourcesConfigurationAudit.objects.for_tenant(tenant_a.id)
        .filter(configuration_id=configuration_b.id)
        .exists()
    )


def test_configuration_validation_enforces_schema_dependencies_allow_lists_and_safe_bounds() -> None:
    invalid_documents: list[dict[str, object]] = []

    below_safe_actor_limit = _document(actor_identifier_max_length=31)
    invalid_documents.append(below_safe_actor_limit)

    invalid_depth_dependency = _document(reporting_tree_default_depth=21, reporting_tree_max_depth=20)
    invalid_documents.append(invalid_depth_dependency)

    unsupported_default = HumanResourcesConfigurationService.default_document()
    cast(dict[str, object], unsupported_default["defaults"])["employment_type"] = "seasonal"
    invalid_documents.append(unsupported_default)

    duplicate_allow_list = HumanResourcesConfigurationService.default_document()
    cast(dict[str, object], duplicate_allow_list["allowed_values"])["employment_types"] = [
        "full_time",
        "full_time",
    ]
    invalid_documents.append(duplicate_allow_list)

    invalid_rollout = HumanResourcesConfigurationService.default_document()
    cast(dict[str, object], invalid_rollout["feature_rollout"])["percentage"] = 101
    invalid_documents.append(invalid_rollout)

    unknown_field = HumanResourcesConfigurationService.default_document()
    unknown_field["unmanaged"] = {}
    invalid_documents.append(unknown_field)

    missing_section = HumanResourcesConfigurationService.default_document()
    del missing_section["operations"]
    invalid_documents.append(missing_section)

    for document in invalid_documents:
        with pytest.raises(HRValidationError):
            HumanResourcesConfigurationService.validate_document(document)


def test_configuration_safe_bounds_are_database_enforced(tenant_a: Any) -> None:
    configuration = HumanResourcesConfigurationService.ensure_configuration(tenant_a.id)

    with pytest.raises(IntegrityError), transaction.atomic():
        HumanResourcesConfiguration.objects.filter(pk=configuration.pk).update(actor_identifier_max_length=31)

    configuration.refresh_from_db()
    assert configuration.actor_identifier_max_length == 255


def test_configuration_versions_and_audits_are_immutable(tenant_a: Any) -> None:
    HumanResourcesConfigurationService.ensure_configuration(tenant_a.id)
    snapshot = HumanResourcesConfigurationVersion.objects.for_tenant(tenant_a.id).get()
    audit = HumanResourcesConfigurationAudit.objects.for_tenant(tenant_a.id).get()

    snapshot.change_reason = "tampered"
    with pytest.raises(DjangoValidationError, match="immutable"):
        snapshot.save()
    with pytest.raises(DjangoValidationError, match="immutable"):
        snapshot.delete()

    audit.change_reason = "tampered"
    with pytest.raises(DjangoValidationError, match="immutable"):
        audit.save()
    with pytest.raises(DjangoValidationError, match="immutable"):
        audit.delete()

    snapshot.refresh_from_db()
    audit.refresh_from_db()
    assert snapshot.change_reason == "Defensible module defaults"
    assert audit.change_reason == "Defensible module defaults"


def test_preview_update_replay_conflict_and_rollback_preserve_history(tenant_a: Any) -> None:
    configuration = HumanResourcesConfigurationService.ensure_configuration(tenant_a.id)
    initial_document = deepcopy(configuration.document)
    version_two_document = _document(list_page_size=30)

    preview = HumanResourcesConfigurationService.preview(tenant_a.id, version_two_document)
    assert preview["valid"] is True
    assert preview["normalized_document"] == version_two_document
    assert preview["changes"] == [
        {
            "path": "limits.list_page_size",
            "before": 25,
            "after": 30,
        }
    ]
    configuration.refresh_from_db()
    assert configuration.version == 1
    assert configuration.document == initial_document

    updated = HumanResourcesConfigurationService.update(
        tenant_a.id,
        document=version_two_document,
        environment="default",
        actor_id="configuration-admin",
        correlation_id="correlation-update",
        change_reason="Increase governed list size",
        idempotency_key="configuration-update-1",
    )
    replay = HumanResourcesConfigurationService.update(
        tenant_a.id,
        document=version_two_document,
        environment="default",
        actor_id="configuration-admin",
        correlation_id="different-replay-correlation",
        change_reason="Increase governed list size",
        idempotency_key="configuration-update-1",
    )
    assert replay.id == updated.id
    assert replay.version == 2
    assert HumanResourcesConfigurationVersion.objects.for_tenant(tenant_a.id).count() == 2
    assert HumanResourcesConfigurationAudit.objects.for_tenant(tenant_a.id).count() == 2

    with pytest.raises(HRConflictError) as conflict:
        HumanResourcesConfigurationService.update(
            tenant_a.id,
            document=_document(list_page_size=31),
            environment="default",
            actor_id="configuration-admin",
            correlation_id="correlation-conflict",
            change_reason="Conflicting command",
            idempotency_key="configuration-update-1",
        )
    assert conflict.value.error_code == "HR_IDEMPOTENCY_CONFLICT"

    version_three_document = _document(list_page_size=40)
    HumanResourcesConfigurationService.update(
        tenant_a.id,
        document=version_three_document,
        environment="default",
        actor_id="configuration-admin",
        correlation_id="correlation-update-2",
        change_reason="Second governed change",
        idempotency_key="configuration-update-2",
    )
    rolled_back = HumanResourcesConfigurationService.rollback(
        tenant_a.id,
        environment="default",
        version=2,
        actor_id="configuration-admin",
        correlation_id="correlation-rollback",
        change_reason="Restore approved configuration",
        idempotency_key="configuration-rollback-1",
    )

    assert rolled_back.version == 4
    assert rolled_back.document == version_two_document
    rollback_snapshot = HumanResourcesConfigurationVersion.objects.for_tenant(tenant_a.id).get(version=4)
    rollback_audit = HumanResourcesConfigurationAudit.objects.for_tenant(tenant_a.id).get(version=4)
    assert rollback_snapshot.rolled_back_from_version == 2
    assert rollback_snapshot.correlation_id == "correlation-rollback"
    assert rollback_audit.action == "rollback"
    assert rollback_audit.before_document == version_three_document
    assert rollback_audit.after_document == version_two_document
    assert rollback_audit.correlation_id == "correlation-rollback"


def test_configuration_api_preview_import_export_history_rollback_and_tenant_isolation(
    tenant_a: Any,
    tenant_b: Any,
    tenant_a_client: Any,
    allow_hr_access: Any,
) -> None:
    allow_hr_access(tenant_a.id)
    foreign_document = _document(list_page_size=99)
    HumanResourcesConfigurationService.update(
        tenant_b.id,
        document=foreign_document,
        environment="default",
        actor_id="foreign-admin",
        correlation_id="foreign-correlation",
        change_reason="Foreign tenant configuration",
        idempotency_key="foreign-update-1",
    )

    current = tenant_a_client.get("/api/v2/human-resources/configuration/")
    assert current.status_code == status.HTTP_200_OK
    current_data = _response_data(current)
    assert current_data["version"] == 1
    assert current_data["document"]["limits"]["list_page_size"] == 25

    version_two_document = _document(list_page_size=30)
    preview = tenant_a_client.post(
        "/api/v2/human-resources/configuration/preview/",
        {"environment": "default", "document": version_two_document},
        format="json",
    )
    assert preview.status_code == status.HTTP_200_OK
    assert _response_data(preview)["changes"] == [{"path": "limits.list_page_size", "before": 25, "after": 30}]

    update = tenant_a_client.patch(
        "/api/v2/human-resources/configuration/",
        {
            "environment": "default",
            "document": version_two_document,
            "change_reason": "Approve page-size change",
            "idempotency_key": "api-configuration-update-1",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-configuration-update-1",
        HTTP_X_CORRELATION_ID=str(uuid4()),
    )
    assert update.status_code == status.HTTP_200_OK
    assert _response_data(update)["version"] == 2

    exported = tenant_a_client.get("/api/v2/human-resources/configuration/export/")
    assert exported.status_code == status.HTTP_200_OK
    exported_data = _response_data(exported)
    assert exported_data == {
        "schema": "saraise.human_resources.configuration",
        "environment": "default",
        "version": 2,
        "document": version_two_document,
    }

    imported_document = _document(list_page_size=35)
    imported = tenant_a_client.post(
        "/api/v2/human-resources/configuration/import/",
        {
            "environment": "default",
            "document": imported_document,
            "change_reason": "Import reviewed configuration",
            "idempotency_key": "api-configuration-import-1",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-configuration-import-1",
    )
    assert imported.status_code == status.HTTP_200_OK
    assert _response_data(imported)["version"] == 3

    history = tenant_a_client.get("/api/v2/human-resources/configuration/history/")
    assert history.status_code == status.HTTP_200_OK
    history_data = _response_data(history)
    assert [row["version"] for row in history_data] == [3, 2, 1]
    assert all(row["correlation_id"] != "foreign-correlation" for row in history_data)

    audit = tenant_a_client.get("/api/v2/human-resources/configuration/audit/")
    assert audit.status_code == status.HTTP_200_OK
    audit_data = _response_data(audit)
    assert [row["action"] for row in audit_data] == ["import", "update", "bootstrap"]
    assert all(row["correlation_id"] != "foreign-correlation" for row in audit_data)

    rollback = tenant_a_client.post(
        "/api/v2/human-resources/configuration/rollback/",
        {
            "environment": "default",
            "version": 2,
            "change_reason": "Restore approved API version",
            "idempotency_key": "api-configuration-rollback-1",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-configuration-rollback-1",
    )
    assert rollback.status_code == status.HTTP_200_OK
    rollback_data = _response_data(rollback)
    assert rollback_data["version"] == 4
    assert rollback_data["document"] == version_two_document

    foreign = HumanResourcesConfiguration.objects.for_tenant(tenant_b.id).get(environment="default")
    assert foreign.version == 2
    assert foreign.document == foreign_document


def test_configuration_get_queryset_without_tenant_context_is_empty() -> None:
    request = Request(APIRequestFactory().get("/api/v2/human-resources/configuration/"))
    request.user = AnonymousUser()
    view = HumanResourcesConfigurationViewSet()
    view.request = request

    assert not view.get_queryset().exists()
