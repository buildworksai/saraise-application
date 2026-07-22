"""Production-faithful HTTP, worker, relation, and RLS isolation contracts."""

from __future__ import annotations

import uuid
from typing import Any, Mapping

import pytest
from django.db import connection
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessDecisionPipeline, AccessReasonCode
from src.core.tenancy import MissingTenantContext, tenant_context
from src.core.testing.tenant_contract import TenantIsolationContract

from ..factories import (
    completed_job_with_archive_factory,
    job_factory,
    retention_policy_factory,
    schedule_factory,
    storage_target_factory,
    verification_factory,
)
from ..models import BackupJob, BackupRetentionPolicy, BackupSchedule, BackupStorageTarget
from ..tasks import capture_backup

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db

PREFIX = "/api/v2/backup-recovery"


@pytest.fixture(autouse=True)
def allow_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def decide(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(True, AccessReasonCode.ALLOW, "allowed", tenant_id=uuid.UUID(str(tenant_id)))

    monkeypatch.setattr(AccessDecisionPipeline, "decide", decide)


class V2IsolationContract(TenantIsolationContract):
    read_denial_statuses = frozenset({status.HTTP_404_NOT_FOUND})
    create_success_statuses = frozenset({status.HTTP_200_OK, status.HTTP_201_CREATED, status.HTTP_202_ACCEPTED})

    def get_list_items(self, response: Any) -> list[Mapping[str, Any]]:
        return response.json()["data"]


@pytest.fixture
def tenant_resources(tenant_a, tenant_b):
    target_a = storage_target_factory(tenant_a.id, is_default=True)
    target_b = storage_target_factory(tenant_b.id, is_default=True)
    policy_a = retention_policy_factory(tenant_a.id)
    policy_b = retention_policy_factory(tenant_b.id)
    schedule_a = schedule_factory(tenant_a.id, storage_target=target_a, retention_policy=policy_a)
    schedule_b = schedule_factory(tenant_b.id, storage_target=target_b, retention_policy=policy_b)
    job_a = job_factory(tenant_a.id, storage_target=target_a)
    job_b = job_factory(tenant_b.id, storage_target=target_b)
    return target_a, target_b, policy_a, policy_b, schedule_a, schedule_b, job_a, job_b


class TestStorageTargetIsolation(V2IsolationContract):
    model = BackupStorageTarget
    list_url = f"{PREFIX}/storage-targets/"
    detail_url_template = f"{PREFIX}/storage-targets/{{pk}}/"
    update_payload = {"name": "Cross-tenant mutation"}
    create_payload = {
        "name": "Spoofed target",
        "adapter_key": "local-filesystem",
        "locator_prefix_ref": "safe-backups",
        "configuration_ref": "local-default",
    }

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_resources):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row, self.tenant_b_row = tenant_resources[:2]


class TestRetentionPolicyIsolation(V2IsolationContract):
    model = BackupRetentionPolicy
    list_url = f"{PREFIX}/retention-policies/"
    detail_url_template = f"{PREFIX}/retention-policies/{{pk}}/"
    update_payload = {"description": "Cross-tenant mutation"}
    create_payload = {"name": "Spoofed policy", "retention_days": 30, "archive_after_days": 7}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_resources):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row, self.tenant_b_row = tenant_resources[2:4]


class TestScheduleIsolation(V2IsolationContract):
    model = BackupSchedule
    list_url = f"{PREFIX}/schedules/"
    detail_url_template = f"{PREFIX}/schedules/{{pk}}/"
    update_payload = {"description": "Cross-tenant mutation"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_resources):
        self.client = authenticated_tenant_a_client
        target_a, _, policy_a, _, self.tenant_a_row, self.tenant_b_row, _, _ = tenant_resources
        self.create_payload = {
            "name": "Spoofed schedule",
            "scope_type": "tenant",
            "scope_ref": "primary",
            "backup_type": "full",
            "frequency": "daily",
            "schedule_time": "02:00:00",
            "timezone": "UTC",
            "storage_target_id": str(target_a.id),
            "retention_policy_id": str(policy_a.id),
        }


class TestJobIsolation(V2IsolationContract):
    model = BackupJob
    list_url = f"{PREFIX}/jobs/"
    detail_url_template = f"{PREFIX}/jobs/{{pk}}/"
    update_payload = {"description": "Cross-tenant mutation"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_resources):
        self.client = authenticated_tenant_a_client
        target_a, _, policy_a, _, _, _, self.tenant_a_row, self.tenant_b_row = tenant_resources
        self.create_payload = {
            "backup_type": "full",
            "scope_type": "tenant",
            "scope_ref": "primary",
            "idempotency_key": f"isolation:{uuid.uuid4()}",
            "storage_target_id": str(target_a.id),
            "retention_policy_id": str(policy_a.id),
        }


@pytest.mark.parametrize(
    ("resource_index", "action"),
    [
        (4, "activate"),
        (4, "deactivate"),
        (4, "run-now"),
        (2, "activate"),
        (2, "deactivate"),
        (0, "activate"),
        (0, "deactivate"),
        (0, "set-default"),
        (0, "probe"),
        (6, "cancel"),
        (6, "retry"),
    ],
)
def test_custom_actions_hide_cross_tenant_ids(authenticated_tenant_a_client, tenant_resources, resource_index, action):
    row = tenant_resources[resource_index + 1]
    resource = {0: "storage-targets", 2: "retention-policies", 4: "schedules", 6: "jobs"}[resource_index]
    response = authenticated_tenant_a_client.post(
        f"{PREFIX}/{resource}/{row.id}/{action}/",
        {"idempotency_key": str(uuid.uuid4()), "transition_key": str(uuid.uuid4())},
        format="json",
    )
    assert response.status_code == 404


def test_archive_and_verification_list_detail_action_isolation(authenticated_tenant_a_client, tenant_a, tenant_b):
    _, own_archive = completed_job_with_archive_factory(tenant_a.id)
    _, other_archive = completed_job_with_archive_factory(tenant_b.id)
    own_verification = verification_factory(tenant_a.id, archive=own_archive)
    other_verification = verification_factory(tenant_b.id, archive=other_archive)
    archive_rows = authenticated_tenant_a_client.get(f"{PREFIX}/archives/").json()["data"]
    verification_rows = authenticated_tenant_a_client.get(f"{PREFIX}/verifications/").json()["data"]
    assert str(own_archive.id) in {row["id"] for row in archive_rows}
    assert str(other_archive.id) not in {row["id"] for row in archive_rows}
    assert str(own_verification.id) in {row["id"] for row in verification_rows}
    assert str(other_verification.id) not in {row["id"] for row in verification_rows}
    assert authenticated_tenant_a_client.get(f"{PREFIX}/archives/{other_archive.id}/").status_code == 404
    assert (
        authenticated_tenant_a_client.post(
            f"{PREFIX}/archives/{other_archive.id}/verify/", {"idempotency_key": "x"}, format="json"
        ).status_code
        == 404
    )
    assert authenticated_tenant_a_client.get(f"{PREFIX}/verifications/{other_verification.id}/").status_code == 404
    assert (
        authenticated_tenant_a_client.post(
            f"{PREFIX}/verifications/{other_verification.id}/cancel/", {"transition_key": "x"}, format="json"
        ).status_code
        == 404
    )


def test_cross_tenant_relations_fail_closed(tenant_a, tenant_b):
    foreign_target = storage_target_factory(tenant_b.id)
    own_policy = retention_policy_factory(tenant_a.id)
    with pytest.raises(Exception):
        schedule_factory(tenant_a.id, storage_target=foreign_target, retention_policy=own_policy)


def test_worker_requires_keyword_tenant_context(tenant_a):
    with pytest.raises(MissingTenantContext):
        capture_backup(job_id=uuid.uuid4())
    with pytest.raises((TypeError, ValueError)):
        capture_backup(tenant_id="malformed", job_id=uuid.uuid4())


@pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL RLS contract")
def test_postgresql_rls_blocks_unscoped_access(tenant_a, tenant_b):
    own = storage_target_factory(tenant_a.id)
    other = storage_target_factory(tenant_b.id)
    with tenant_context(tenant_a.id):
        assert BackupStorageTarget.objects.filter(pk=own.id).exists()
        assert not BackupStorageTarget.objects.filter(pk=other.id).exists()
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM backup_recovery_storage_targets WHERE id = %s", [other.id])
            assert cursor.fetchone()[0] == 0
