"""Black-box tenant isolation contracts for every mutable public entity."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from rest_framework.exceptions import NotFound
from rest_framework import status

from src.core.access.permissions import RequiresAccess
from src.core.testing import TenantIsolationContract
from src.modules.data_migration.models import (
    ExternalConnection,
    MigrationJob,
    MigrationJobVersion,
    MigrationMapping,
    MigrationRun,
    ValidationRule,
)
from src.modules.data_migration.services import MigrationJobService, MigrationServiceError

pytest_plugins = ["src.core.testing.factories"]


@pytest.fixture(autouse=True)
def fast_test_password_hashing(settings) -> None:
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def _items(response: Any) -> list[dict[str, Any]]:
    payload = response.data
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload["data"]
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    raise AssertionError(f"Unexpected collection payload: {payload!r}")


@pytest.fixture(autouse=True)
def allow_access_pipeline(monkeypatch) -> None:
    """Keep isolation focused after the shared access pipeline's own tests."""

    monkeypatch.setattr(RequiresAccess, "has_permission", lambda self, request, view: True)
    monkeypatch.setattr(RequiresAccess, "has_object_permission", lambda self, request, view, obj: True)
    monkeypatch.setattr("src.modules.dms.services.VersionService.get_version", lambda self, tenant, actor, version: object())


@pytest.fixture
def actor_id(tenant_a_user) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{tenant_a_user.pk}")


def _job(tenant_id: uuid.UUID, actor: uuid.UUID, name: str) -> MigrationJob:
    return MigrationJobService.create(
        tenant_id,
        actor,
        {
            "name": name,
            "source_type": "csv",
            "source_artifact_id": uuid.uuid4(),
            "source_config": {"encoding": "utf-8", "batch_size": 50},
            "target_adapter": "core.record",
            "target_entity": "record",
            "write_mode": "create",
            "lookup_fields": [],
        },
    )


class GovernedEnvelopeIsolationContract(TenantIsolationContract):
    read_denial_statuses = frozenset({status.HTTP_404_NOT_FOUND})

    def get_list_items(self, response):
        return _items(response)


@pytest.mark.django_db
class TestMigrationJobIsolation(GovernedEnvelopeIsolationContract):
    model = MigrationJob
    list_url = "/api/v2/data-migration/jobs/"
    detail_url_template = "/api/v2/data-migration/jobs/{pk}/"
    create_payload = {
        "name": "Spoof attempt",
        "source_type": "csv",
        "source_artifact_id": "00000000-0000-0000-0000-000000000123",
        "source_config": {"encoding": "utf-8", "batch_size": 25},
        "target_adapter": "core.record",
        "target_entity": "record",
        "write_mode": "create",
        "lookup_fields": [],
    }
    update_payload = {"description": "cross-tenant edit", "expected_version": 1}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, tenant_a, tenant_b, actor_id):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = _job(tenant_a.id, actor_id, "Tenant A job")
        self.tenant_b_row = _job(tenant_b.id, actor_id, "Tenant B job")


@pytest.mark.django_db
class TestMigrationMappingIsolation(GovernedEnvelopeIsolationContract):
    model = MigrationMapping
    detail_url_template = "/api/v2/data-migration/mappings/{pk}/"
    create_payload = {
        "source_field": "source_new",
        "target_field": "target_new",
        "position": 1,
        "transform_type": "identity",
        "transform_config": {},
        "is_required": False,
    }
    update_payload = {"source_field": "cross_tenant"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, tenant_a, tenant_b, actor_id):
        self.client = authenticated_tenant_a_client
        self.job_a = _job(tenant_a.id, actor_id, "Tenant A mappings")
        job_b = _job(tenant_b.id, actor_id, "Tenant B mappings")
        self.tenant_a_row = MigrationMapping.objects.create(
            tenant_id=tenant_a.id, job=self.job_a, source_field="name", target_field="full_name",
            position=0, transform_type="identity", transform_config={}, created_by=actor_id,
        )
        self.tenant_b_row = MigrationMapping.objects.create(
            tenant_id=tenant_b.id, job=job_b, source_field="name", target_field="full_name",
            position=0, transform_type="identity", transform_config={}, created_by=actor_id,
        )

    def get_list_url(self) -> str:
        return f"/api/v2/data-migration/jobs/{self.job_a.id}/mappings/"


@pytest.mark.django_db
class TestValidationRuleIsolation(GovernedEnvelopeIsolationContract):
    model = ValidationRule
    detail_url_template = "/api/v2/data-migration/validation-rules/{pk}/"
    create_payload = {
        "field_name": "external_id",
        "rule_type": "required",
        "rule_config": {},
        "error_message": "Required",
        "severity": "error",
        "position": 1,
        "is_active": True,
    }
    update_payload = {"error_message": "cross-tenant edit"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, tenant_a, tenant_b, actor_id):
        self.client = authenticated_tenant_a_client
        self.job_a = _job(tenant_a.id, actor_id, "Tenant A rules")
        job_b = _job(tenant_b.id, actor_id, "Tenant B rules")
        self.tenant_a_row = ValidationRule.objects.create(
            tenant_id=tenant_a.id, job=self.job_a, field_name="name", rule_type="required",
            rule_config={}, error_message="Required", severity="error", position=0, created_by=actor_id,
        )
        self.tenant_b_row = ValidationRule.objects.create(
            tenant_id=tenant_b.id, job=job_b, field_name="name", rule_type="required",
            rule_config={}, error_message="Required", severity="error", position=0, created_by=actor_id,
        )

    def get_list_url(self) -> str:
        return f"/api/v2/data-migration/jobs/{self.job_a.id}/validation-rules/"


@pytest.mark.django_db
class TestExternalConnectionIsolation(GovernedEnvelopeIsolationContract):
    model = ExternalConnection
    list_url = "/api/v2/data-migration/connections/"
    detail_url_template = "/api/v2/data-migration/connections/{pk}/"
    create_payload = {
        "name": "Spoofed connection", "kind": "http", "base_url": "https://api.example.test",
        "credential_ref": "vault://migration/spoof", "tls_mode": "verify-full", "public_options": {},
    }
    update_payload = {"name": "cross-tenant edit"}
    read_denial_statuses = frozenset({status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED})

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, tenant_a, tenant_b, actor_id):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = ExternalConnection.objects.create(
            tenant_id=tenant_a.id, name="Tenant A API", kind="http", base_url="https://a.example.test",
            credential_ref="vault://a", tls_mode="verify-full", public_options={}, created_by=actor_id,
        )
        self.tenant_b_row = ExternalConnection.objects.create(
            tenant_id=tenant_b.id, name="Tenant B API", kind="http", base_url="https://b.example.test",
            credential_ref="vault://b", tls_mode="verify-full", public_options={}, created_by=actor_id,
        )


@pytest.mark.django_db
def test_cross_tenant_actions_are_exact_404(
    authenticated_tenant_a_client, tenant_a, tenant_b, actor_id
) -> None:
    job_b = _job(tenant_b.id, actor_id, "Tenant B actions")
    version_b = MigrationJobVersion.objects.get(job=job_b, version=1)
    run_b = MigrationRun.objects.create(
        tenant_id=tenant_b.id, job=job_b, job_version=version_b, async_job_id=uuid.uuid4(),
        mode="commit", status="queued", idempotency_key="tenant-b-run", source_checksum="a" * 64,
        created_by=actor_id, correlation_id="corr-b",
    )
    client = authenticated_tenant_a_client
    calls = (
        ("post", f"/api/v2/data-migration/jobs/{job_b.id}/validate/", {}),
        ("get", f"/api/v2/data-migration/jobs/{job_b.id}/preview/", None),
        ("post", f"/api/v2/data-migration/jobs/{job_b.id}/inspect/", {}),
        ("post", f"/api/v2/data-migration/jobs/{job_b.id}/versions/1/restore/", {"expected_version": 1}),
        ("post", f"/api/v2/data-migration/jobs/{job_b.id}/runs/", {}),
        ("post", f"/api/v2/data-migration/runs/{run_b.id}/cancel/", {"transition_key": "cancel-a"}),
        ("get", f"/api/v2/data-migration/runs/{run_b.id}/issues/export/", None),
        ("post", f"/api/v2/data-migration/runs/{run_b.id}/rollback/", {}),
    )
    for method, url, data in calls:
        response = getattr(client, method)(url, data=data, format="json", HTTP_IDEMPOTENCY_KEY="isolation-key")
        assert response.status_code == status.HTTP_404_NOT_FOUND, (method, url, response.status_code, response.data)


@pytest.mark.django_db
def test_external_connection_reference_cannot_cross_tenants(tenant_a, tenant_b, actor_id) -> None:
    connection_b = ExternalConnection.objects.create(
        tenant_id=tenant_b.id, name="Tenant B database", kind="postgresql", host="db.example.test",
        port=5432, database="source", username="readonly", credential_ref="vault://b/db",
        tls_mode="verify-full", public_options={}, created_by=actor_id,
    )
    command = {
        "name": "Cross-tenant source", "source_type": "database", "source_artifact_id": None,
        "source_config": {"connection_id": str(connection_b.id), "table": "customers", "columns": ["id"], "filters": {}},
        "target_adapter": "core.record", "target_entity": "record", "write_mode": "create", "lookup_fields": [],
    }
    with pytest.raises((NotFound, MigrationServiceError)):
        MigrationJobService.create(tenant_a.id, actor_id, command)
    assert not MigrationJob.objects.filter(tenant_id=tenant_a.id, name="Cross-tenant source").exists()
