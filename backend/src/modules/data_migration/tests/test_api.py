"""Governed API v2 route, boundary and service-delegation contracts."""

from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from django.core.exceptions import ObjectDoesNotExist
from django.urls import resolve
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from src.core.access.permissions import RequiresAccess
from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination, OperationFailed
from src.modules.data_migration import api
from src.modules.data_migration.models import (
    DataMigrationConfiguration,
    ExternalConnection,
    MigrationJob,
    MigrationJobVersion,
    MigrationMapping,
    MigrationRun,
    MigrationRunIssue,
    ValidationRule,
)
from src.modules.data_migration.services import MigrationJobService

pytest_plugins = ["src.core.testing.factories"]


@pytest.fixture(autouse=True)
def fast_test_password_hashing(settings) -> None:
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def allow_access_pipeline(monkeypatch) -> None:
    monkeypatch.setattr(RequiresAccess, "has_permission", lambda self, request, view: True)
    monkeypatch.setattr(RequiresAccess, "has_object_permission", lambda self, request, view, obj: True)


@pytest.fixture
def actor_id(tenant_a_user) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{tenant_a_user.pk}")


def _job(tenant_id: uuid.UUID, actor: uuid.UUID, name: str, **overrides: Any) -> MigrationJob:
    values = {
        "tenant_id": tenant_id,
        "name": name,
        "description": f"{name} migration",
        "source_type": "csv",
        "source_artifact_id": uuid.uuid4(),
        "source_config": {"encoding": "utf-8", "batch_size": 50},
        "target_adapter": "core.record",
        "target_entity": "customer",
        "write_mode": "create",
        "lookup_fields": [],
        "created_by": actor,
    }
    values.update(overrides)
    return MigrationJob.objects.create(**values)


def _version(job: MigrationJob, actor: uuid.UUID) -> MigrationJobVersion:
    return MigrationJobVersion.objects.create(
        tenant_id=job.tenant_id,
        job=job,
        version=1,
        snapshot={"tenant_id": str(job.tenant_id), "job_id": str(job.id), "name": job.name},
        change_summary="Created",
        created_by=actor,
        correlation_id="api-test-correlation",
    )


def _run(job: MigrationJob, actor: uuid.UUID, **overrides: Any) -> MigrationRun:
    values = {
        "tenant_id": job.tenant_id,
        "job": job,
        "job_version": _version(job, actor),
        "async_job_id": uuid.uuid4(),
        "mode": "commit",
        "status": "queued",
        "idempotency_key": f"run-{uuid.uuid4()}",
        "source_checksum": "a" * 64,
        "total_records": 10,
        "processed_records": 0,
        "created_by": actor,
        "correlation_id": "run-correlation",
    }
    values.update(overrides)
    return MigrationRun.objects.create(**values)


@pytest.mark.parametrize(
    ("path", "view_name"),
    (
        ("/api/v2/data-migration/jobs/", "data_migration_v2:job-list"),
        ("/api/v2/data-migration/jobs/import/", "data_migration_v2:job-import-definition"),
        (
            "/api/v2/data-migration/jobs/00000000-0000-0000-0000-000000000001/validate/",
            "data_migration_v2:job-validate-definition",
        ),
        (
            "/api/v2/data-migration/jobs/00000000-0000-0000-0000-000000000001/dry-runs/",
            "data_migration_v2:job-request-dry-run",
        ),
        (
            "/api/v2/data-migration/runs/00000000-0000-0000-0000-000000000001/issues/export/",
            "data_migration_v2:run-export-issues",
        ),
        (
            "/api/v2/data-migration/connections/00000000-0000-0000-0000-000000000001/test/",
            "data_migration_v2:connection-test-connection",
        ),
        ("/api/v2/data-migration/configuration/", "data_migration_v2:configuration"),
        ("/api/v2/data-migration/configuration/versions/1/restore/", "data_migration_v2:configuration-restore"),
        ("/api/v2/data-migration/health/live/", "data_migration_v2:health-live"),
        ("/api/v2/data-migration/health/ready/", "data_migration_v2:health-ready"),
    ),
)
def test_required_routes_resolve(path: str, view_name: str) -> None:
    assert resolve(path).view_name == view_name


@pytest.mark.parametrize(
    "viewset",
    (
        api.MigrationJobViewSet,
        api.MigrationMappingViewSet,
        api.ValidationRuleViewSet,
        api.MigrationRunViewSet,
        api.MigrationRollbackViewSet,
        api.ExternalConnectionViewSet,
        api.DataMigrationConfigurationViewSet,
    ),
)
def test_every_json_viewset_uses_governed_profile_and_bounded_pagination(viewset: type) -> None:
    assert issubclass(viewset, GovernedAPIViewMixin)
    assert viewset.pagination_class is GovernedPageNumberPagination


@pytest.mark.parametrize(
    ("viewset", "method", "service_name"),
    (
        (api.MigrationJobViewSet, "create", "MigrationJobService.create"),
        (api.MigrationJobViewSet, "partial_update", "MigrationJobService.update"),
        (api.MigrationJobViewSet, "destroy", "MigrationJobService.soft_delete"),
        (api.MigrationMappingViewSet, "partial_update", "MigrationMappingService.update"),
        (api.ValidationRuleViewSet, "partial_update", "ValidationRuleService.update"),
        (api.MigrationRunViewSet, "cancel", "MigrationExecutionService.cancel"),
        (api.MigrationRunViewSet, "rollback", "RollbackService.request"),
        (api.ExternalConnectionViewSet, "create", "ExternalConnectionService.register"),
        (api.DataMigrationConfigurationViewSet, "update_configuration", "DataMigrationConfigurationService.update"),
    ),
)
def test_mutations_delegate_to_services(viewset: type, method: str, service_name: str) -> None:
    source = inspect.getsource(getattr(viewset, method))
    assert service_name in source
    assert ".save(" not in source
    assert ".objects.create(" not in source


def test_idempotency_key_is_mandatory_and_validated() -> None:
    missing = APIRequestFactory().post("/api/v2/data-migration/jobs/id/runs/")
    with pytest.raises(ValidationError):
        api._idempotency_key(missing)
    valid = APIRequestFactory().post("/", HTTP_IDEMPOTENCY_KEY="tenant:run:001")
    assert api._idempotency_key(valid) == "tenant:run:001"
    oversized = APIRequestFactory().post("/", HTTP_IDEMPOTENCY_KEY="x" * 256)
    with pytest.raises(ValidationError):
        api._idempotency_key(oversized)


def test_request_identity_helpers_fail_closed_and_normalize_actor_ids() -> None:
    tenant_id = uuid.uuid4()
    request = APIRequestFactory().get("/")
    request.user = SimpleNamespace(
        id=uuid.UUID(int=7), pk=uuid.UUID(int=7), profile=SimpleNamespace(tenant_id=tenant_id)
    )
    assert api._tenant(request) == tenant_id
    assert request.tenant_id == tenant_id
    assert api._actor(request) == uuid.UUID(int=7)

    request.user.pk = "external-user-42"
    assert api._actor(request) == uuid.uuid5(uuid.NAMESPACE_URL, "saraise:user:external-user-42")

    request.user.pk = None
    with pytest.raises(api.PermissionDenied):
        api._actor(request)

    request.user.profile.tenant_id = "not-a-tenant"
    with pytest.raises(api.PermissionDenied):
        api._tenant(request)


def test_result_data_unwraps_public_payload_shapes() -> None:
    dataclass_result = api._result_data(type("ValueResult", (), {"value": {"ok": True}})())
    data_result = api._result_data(type("DataResult", (), {"data": {"count": 1}})())
    raw_result = api._result_data({"raw": True})

    assert dataclass_result == {"ok": True}
    assert data_result == {"count": 1}
    assert raw_result == {"raw": True}


def test_csv_formula_injection_is_neutralized() -> None:
    for unsafe in ("=cmd()", "+1", "-1", "@SUM(A1)", "\tformula", "\rformula"):
        assert api._csv_cell(unsafe).startswith("'")
    assert api._csv_cell("ordinary") == "ordinary"


@pytest.mark.django_db
def test_job_list_filters_search_orders_and_excludes_deleted_or_foreign_tenants(
    authenticated_tenant_a_client, tenant_a, tenant_b, actor_id
) -> None:
    target = _job(tenant_a.id, actor_id, "Customers Import")
    _job(tenant_a.id, actor_id, "Deleted Customers", is_deleted=True)
    _job(tenant_b.id, actor_id, "Tenant B Customers")

    response = authenticated_tenant_a_client.get(
        "/api/v2/data-migration/jobs/"
        "?status=draft&source_type=csv&target_adapter=core.record&target_entity=customer"
        "&search=Customers&ordering=name"
    )

    assert response.status_code == status.HTTP_200_OK
    assert [row["id"] for row in response.json()["data"]] == [str(target.id)]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "query",
    (
        "?ordering=tenant_id",
        f"?search={'x' * 201}",
        "?unsupported=true",
    ),
)
def test_job_list_invalid_filters_use_validation_envelope(authenticated_tenant_a_client, query) -> None:
    response = authenticated_tenant_a_client.get(f"/api/v2/data-migration/jobs/{query}")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_job_preview_validates_limit_and_does_not_call_service(
    authenticated_tenant_a_client, tenant_a, actor_id
) -> None:
    job = _job(tenant_a.id, actor_id, "Preview")

    response = authenticated_tenant_a_client.get(f"/api/v2/data-migration/jobs/{job.id}/preview/?limit=101")
    non_integer = authenticated_tenant_a_client.get(f"/api/v2/data-migration/jobs/{job.id}/preview/?limit=not-int")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert non_integer.status_code == status.HTTP_400_BAD_REQUEST
    assert non_integer.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_job_mapping_and_rule_collection_actions_validate_and_list(
    authenticated_tenant_a_client, tenant_a, actor_id
) -> None:
    job = _job(tenant_a.id, actor_id, "Definition Surface")
    mapping_response = authenticated_tenant_a_client.post(
        f"/api/v2/data-migration/jobs/{job.id}/mappings/",
        {
            "source_field": "name",
            "target_field": "full_name",
            "position": 0,
            "transform_type": "identity",
            "transform_config": {},
        },
        format="json",
    )
    rule_response = authenticated_tenant_a_client.post(
        f"/api/v2/data-migration/jobs/{job.id}/validation-rules/",
        {
            "field_name": "full_name",
            "rule_type": "required",
            "rule_config": {},
            "error_message": "Name required",
            "severity": "error",
            "position": 0,
        },
        format="json",
    )
    unsupported_provider = authenticated_tenant_a_client.post(
        f"/api/v2/data-migration/jobs/{job.id}/mappings/suggest/",
        {"provider": "extension"},
        format="json",
    )
    mappings = authenticated_tenant_a_client.get(f"/api/v2/data-migration/jobs/{job.id}/mappings/")
    rules = authenticated_tenant_a_client.get(f"/api/v2/data-migration/jobs/{job.id}/validation-rules/")

    assert mapping_response.status_code == status.HTTP_201_CREATED
    assert rule_response.status_code == status.HTTP_201_CREATED
    assert unsupported_provider.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert unsupported_provider.json()["error"]["code"] == "CAPABILITY_UNAVAILABLE"
    assert [row["id"] for row in mappings.json()["data"]] == [mapping_response.json()["data"]["id"]]
    assert [row["id"] for row in rules.json()["data"]] == [rule_response.json()["data"]["id"]]


@pytest.mark.django_db
def test_mapping_and_validation_rule_detail_endpoints_update_and_delete(
    authenticated_tenant_a_client, tenant_a, actor_id
) -> None:
    job = _job(tenant_a.id, actor_id, "Detail Surface")
    mapping = MigrationMapping.objects.create(
        tenant_id=tenant_a.id,
        job=job,
        source_field="name",
        target_field="full_name",
        position=0,
        transform_type="identity",
        transform_config={},
        created_by=actor_id,
    )
    rule = ValidationRule.objects.create(
        tenant_id=tenant_a.id,
        job=job,
        field_name="full_name",
        rule_type="required",
        rule_config={},
        error_message="Name required",
        severity="error",
        position=0,
        created_by=actor_id,
    )

    mapping_detail = authenticated_tenant_a_client.get(f"/api/v2/data-migration/mappings/{mapping.id}/")
    mapping_update = authenticated_tenant_a_client.patch(
        f"/api/v2/data-migration/mappings/{mapping.id}/",
        {"target_field": "display_name"},
        format="json",
    )
    rule_detail = authenticated_tenant_a_client.get(f"/api/v2/data-migration/validation-rules/{rule.id}/")
    rule_update = authenticated_tenant_a_client.patch(
        f"/api/v2/data-migration/validation-rules/{rule.id}/",
        {"severity": "warning"},
        format="json",
    )
    mapping_delete = authenticated_tenant_a_client.delete(f"/api/v2/data-migration/mappings/{mapping.id}/")
    rule_delete = authenticated_tenant_a_client.delete(f"/api/v2/data-migration/validation-rules/{rule.id}/")

    assert mapping_detail.status_code == status.HTTP_200_OK
    assert mapping_update.status_code == status.HTTP_200_OK
    assert mapping_update.json()["data"]["target_field"] == "display_name"
    assert rule_detail.status_code == status.HTTP_200_OK
    assert rule_update.status_code == status.HTTP_200_OK
    assert rule_update.json()["data"]["severity"] == "warning"
    assert mapping_delete.status_code == status.HTTP_204_NO_CONTENT
    assert rule_delete.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.django_db
def test_job_runs_require_idempotency_and_delegate_commit_request(
    monkeypatch, authenticated_tenant_a_client, tenant_a, actor_id
) -> None:
    job = _job(tenant_a.id, actor_id, "Commit")
    run = _run(job, actor_id, idempotency_key="commit-run")
    calls: list[tuple] = []

    def request_run(*args):
        calls.append(args)
        return run

    missing = authenticated_tenant_a_client.post(f"/api/v2/data-migration/jobs/{job.id}/runs/", {}, format="json")
    monkeypatch.setattr("src.modules.data_migration.api.MigrationExecutionService.request_run", request_run)
    response = authenticated_tenant_a_client.post(
        f"/api/v2/data-migration/jobs/{job.id}/runs/",
        {"source_checksum": "b" * 64},
        format="json",
        HTTP_IDEMPOTENCY_KEY="commit-run",
    )

    assert missing.status_code == status.HTTP_400_BAD_REQUEST
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert calls == [(tenant_a.id, str(job.id), actor_id, "commit", "commit-run")]


@pytest.mark.django_db
def test_job_inspect_import_preview_versions_and_restore_actions(
    authenticated_tenant_a_client, tenant_a, actor_id
) -> None:
    job = _job(tenant_a.id, actor_id, "Versioned")
    version = _version(job, actor_id)
    document = MigrationJobService.export_definition(tenant_a.id, job.id)
    inspect_missing_key = authenticated_tenant_a_client.post(
        f"/api/v2/data-migration/jobs/{job.id}/inspect/",
        {},
        format="json",
    )
    import_preview = authenticated_tenant_a_client.post(
        "/api/v2/data-migration/jobs/import/",
        {"preview_only": True, "document": document},
        format="json",
    )
    versions = authenticated_tenant_a_client.get(f"/api/v2/data-migration/jobs/{job.id}/versions/")
    restored = authenticated_tenant_a_client.post(
        f"/api/v2/data-migration/jobs/{job.id}/versions/{version.version}/restore/",
        {"expected_version": job.configuration_version},
        format="json",
    )

    assert inspect_missing_key.status_code == status.HTTP_400_BAD_REQUEST
    assert import_preview.status_code == status.HTTP_200_OK
    assert import_preview.json()["data"]["checksum_valid"] is True
    assert versions.status_code == status.HTTP_200_OK
    assert [row["version"] for row in versions.json()["data"]] == [version.version]
    assert restored.status_code == status.HTTP_200_OK
    assert restored.json()["data"]["configuration_version"] == job.configuration_version + 1


@pytest.mark.django_db
def test_run_filters_issues_and_csv_export_are_tenant_scoped(authenticated_tenant_a_client, tenant_a, actor_id) -> None:
    job = _job(tenant_a.id, actor_id, "Run Issues")
    run = _run(
        job,
        actor_id,
        mode="commit",
        status="failed",
        total_records=3,
        processed_records=3,
        failed_records=1,
    )
    MigrationRunIssue.objects.create(
        tenant_id=tenant_a.id,
        run=run,
        row_number=2,
        field_name="amount",
        stage="validation",
        severity="error",
        code="BAD_AMOUNT",
        message="=formula must be escaped",
        redacted_sample={"amount": "'=formula"},
    )

    list_response = authenticated_tenant_a_client.get(
        f"/api/v2/data-migration/jobs/{job.id}/runs/?mode=commit&status=failed&created_before="
        f"{(timezone.now() + timezone.timedelta(days=1)).date().isoformat()}&ordering=status"
    )
    issues_response = authenticated_tenant_a_client.get(
        f"/api/v2/data-migration/runs/{run.id}/issues/?severity=error&stage=validation&row_number=2"
    )
    csv_response = authenticated_tenant_a_client.get(f"/api/v2/data-migration/runs/{run.id}/issues/export/")

    assert list_response.status_code == status.HTTP_200_OK
    assert [row["id"] for row in list_response.json()["data"]] == [str(run.id)]
    assert issues_response.status_code == status.HTTP_200_OK
    assert issues_response.json()["data"][0]["code"] == "BAD_AMOUNT"
    assert csv_response.status_code == status.HTTP_200_OK
    exported = b"".join(csv_response.streaming_content).decode()
    assert "'=formula must be escaped" in exported
    assert "X-Content-Type-Options" in csv_response.headers


@pytest.mark.django_db
def test_tenant_admin_cannot_select_connection_tenant_filter(authenticated_tenant_a_client) -> None:
    response = authenticated_tenant_a_client.get(f"/api/v2/data-migration/connections/?tenant_id={uuid.uuid4()}")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_connection_bad_tenant_filter_is_rejected_for_platform_operator(
    authenticated_tenant_a_client, monkeypatch
) -> None:
    monkeypatch.setattr("src.modules.data_migration.api.is_platform_operator", lambda user: True)

    response = authenticated_tenant_a_client.get("/api/v2/data-migration/connections/?tenant_id=not-a-uuid")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_connection_reference_list_hides_inactive_connections(
    authenticated_tenant_a_client, tenant_a, actor_id
) -> None:
    active = ExternalConnection.objects.create(
        tenant_id=tenant_a.id,
        name="Active API",
        kind="http",
        base_url="https://active.example.test",
        credential_ref="vault://active",
        tls_mode="verify-full",
        public_options={},
        created_by=actor_id,
    )
    ExternalConnection.objects.create(
        tenant_id=tenant_a.id,
        name="Inactive API",
        kind="http",
        base_url="https://inactive.example.test",
        credential_ref="vault://inactive",
        tls_mode="verify-full",
        public_options={},
        is_active=False,
        created_by=actor_id,
    )

    response = authenticated_tenant_a_client.get("/api/v2/data-migration/connections/")

    assert response.status_code == status.HTTP_200_OK
    assert [row["id"] for row in response.json()["data"]] == [str(active.id)]
    assert "credential_ref" not in response.json()["data"][0]


@pytest.mark.django_db
def test_configuration_endpoints_preview_update_export_import_versions_and_restore(
    authenticated_tenant_a_client, tenant_a
) -> None:
    config = DataMigrationConfiguration.objects.create(tenant_id=tenant_a.id, created_by=uuid.UUID(int=0))

    preview = authenticated_tenant_a_client.post(
        "/api/v2/data-migration/configuration/preview/",
        {"batch_size": 125, "enabled": False},
        format="json",
    )
    update = authenticated_tenant_a_client.patch(
        "/api/v2/data-migration/configuration/",
        {"expected_version": config.version, "batch_size": 125, "enabled": False},
        format="json",
        HTTP_X_CORRELATION_ID="api-config-update",
    )
    exported = authenticated_tenant_a_client.get("/api/v2/data-migration/configuration/export/")
    document = exported.json()
    imported = authenticated_tenant_a_client.post(
        "/api/v2/data-migration/configuration/import/",
        {"expected_version": 2, "document": document["data"]},
        format="json",
    )
    versions = authenticated_tenant_a_client.get("/api/v2/data-migration/configuration/versions/")
    restored = authenticated_tenant_a_client.post(
        "/api/v2/data-migration/configuration/versions/2/restore/",
        {"expected_version": 3},
        format="json",
    )

    assert preview.status_code == status.HTTP_200_OK
    assert {"batch_size", "enabled"} == {change["field"] for change in preview.json()["data"]["changes"]}
    assert update.status_code == status.HTTP_200_OK
    assert update.json()["data"]["batch_size"] == 125
    assert exported.status_code == status.HTTP_200_OK
    assert document["data"]["configuration"]["batch_size"] == 125
    assert imported.status_code == status.HTTP_200_OK
    assert imported.json()["data"]["version"] == 3
    assert versions.status_code == status.HTTP_200_OK
    assert [row["version"] for row in versions.json()["data"]] == [3, 2]
    assert restored.status_code == status.HTTP_200_OK
    assert restored.json()["data"]["version"] == 4


def test_translate_error_maps_domain_failures_to_stable_api_exceptions() -> None:
    missing = api._translate_error(ObjectDoesNotExist())
    conflict = api._translate_error(type("Conflict", (Exception,), {"code": "VERSION_CONFLICT"})("stale"))
    unavailable = api._translate_error(type("Unavailable", (Exception,), {"code": "CAPABILITY_UNAVAILABLE"})("down"))
    validation = api._translate_error(ValueError("bad source"))

    assert type(missing).__name__ == "NotFound"
    assert isinstance(conflict, OperationFailed)
    assert conflict.status_code == status.HTTP_409_CONFLICT
    assert isinstance(unavailable, OperationFailed)
    assert unavailable.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert isinstance(validation, ValidationError)
