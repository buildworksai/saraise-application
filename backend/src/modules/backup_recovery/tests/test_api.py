"""Governed API v2 endpoint and security contracts."""

from __future__ import annotations

import uuid

import pytest
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessDecisionPipeline, AccessReasonCode
from src.core.testing.factories import authenticated_api_client

from ..factories import completed_job_with_archive_factory, job_factory, storage_target_factory
from ..models import BackupJob

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db

PREFIX = "/api/v2/backup-recovery"


@pytest.fixture(autouse=True)
def allow_access(monkeypatch):
    def decide(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(True, AccessReasonCode.ALLOW, "allowed", tenant_id=uuid.UUID(str(tenant_id)))

    monkeypatch.setattr(AccessDecisionPipeline, "decide", decide)


def assert_v2(response, expected_status=200):
    assert response.status_code == expected_status, response.content
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert body["meta"]["correlation_id"]
    return body


def test_session_authentication_and_csrf(tenant_a_user):
    anonymous = authenticated_api_client(tenant_a_user, enforce_csrf_checks=True)
    anonymous.credentials()
    response = anonymous.post(f"{PREFIX}/storage-targets/", {}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_jobs_endpoints_pagination_filters_commands_and_no_public_worker_actions(
    authenticated_tenant_a_client, tenant_a, tmp_path
):
    target = storage_target_factory(tenant_a.id, locator_prefix_ref=str(tmp_path), is_default=True)
    payload = {
        "backup_type": "full",
        "scope_type": "files",
        "scope_ref": str(tmp_path),
        "idempotency_key": "api-job",
        "storage_target_id": str(target.id),
        "description": "API backup",
    }
    created = assert_v2(authenticated_tenant_a_client.post(f"{PREFIX}/jobs/", payload, format="json"), 202)["data"]
    assert created["status"] == "pending" and created["async_job_id"]
    listed = assert_v2(
        authenticated_tenant_a_client.get(f"{PREFIX}/jobs/?status=pending&page_size=100&ordering=-requested_at")
    )["data"]
    assert [row["id"] for row in listed] == [created["job_id"]]
    detail = assert_v2(authenticated_tenant_a_client.get(f"{PREFIX}/jobs/{created['job_id']}/"))["data"]
    assert detail["id"] == created["job_id"] and detail["allowed_commands"]["cancel"]["allowed"]
    updated = assert_v2(
        authenticated_tenant_a_client.patch(
            f"{PREFIX}/jobs/{created['job_id']}/", {"description": "updated"}, format="json"
        )
    )["data"]
    assert updated["description"] == "updated"
    cancelled = assert_v2(
        authenticated_tenant_a_client.post(
            f"{PREFIX}/jobs/{created['job_id']}/cancel/", {"transition_key": "api-cancel"}, format="json"
        )
    )["data"]
    assert cancelled["status"] == "cancelled"
    retried = assert_v2(
        authenticated_tenant_a_client.post(
            f"{PREFIX}/jobs/{created['job_id']}/retry/", {"idempotency_key": "api-retry"}, format="json"
        ),
        202,
    )["data"]
    retried_detail = assert_v2(authenticated_tenant_a_client.get(f"{PREFIX}/jobs/{retried['job_id']}/"))["data"]
    assert retried_detail["retry_of"] == created["job_id"]
    assert (
        authenticated_tenant_a_client.post(
            f"{PREFIX}/jobs/{created['job_id']}/complete/", {}, format="json"
        ).status_code
        == 404
    )
    assert (
        authenticated_tenant_a_client.post(f"{PREFIX}/jobs/{created['job_id']}/fail/", {}, format="json").status_code
        == 404
    )


def test_schedule_policy_and_storage_target_crud_actions(authenticated_tenant_a_client, tenant_a, tmp_path):
    target_payload = {
        "name": "Local",
        "adapter_key": "local-filesystem",
        "locator_prefix_ref": str(tmp_path),
        "configuration_ref": "local",
        "is_default": True,
    }
    target = assert_v2(
        authenticated_tenant_a_client.post(f"{PREFIX}/storage-targets/", target_payload, format="json"), 201
    )["data"]
    assert assert_v2(
        authenticated_tenant_a_client.post(f"{PREFIX}/storage-targets/{target['id']}/probe/", {}, format="json")
    )["data"]["healthy"]
    assert_v2(
        authenticated_tenant_a_client.post(f"{PREFIX}/storage-targets/{target['id']}/deactivate/", {}, format="json")
    )
    assert_v2(
        authenticated_tenant_a_client.post(f"{PREFIX}/storage-targets/{target['id']}/activate/", {}, format="json")
    )
    assert_v2(
        authenticated_tenant_a_client.post(f"{PREFIX}/storage-targets/{target['id']}/set-default/", {}, format="json")
    )

    policy = assert_v2(
        authenticated_tenant_a_client.post(
            f"{PREFIX}/retention-policies/",
            {"name": "Thirty days", "retention_days": 30, "archive_after_days": 7},
            format="json",
        ),
        201,
    )["data"]
    preview = assert_v2(authenticated_tenant_a_client.get(f"{PREFIX}/retention-policies/{policy['id']}/preview/"))[
        "data"
    ]
    assert preview["expires_at"]
    assert_v2(
        authenticated_tenant_a_client.post(f"{PREFIX}/retention-policies/{policy['id']}/deactivate/", {}, format="json")
    )
    assert_v2(
        authenticated_tenant_a_client.post(f"{PREFIX}/retention-policies/{policy['id']}/activate/", {}, format="json")
    )

    schedule_payload = {
        "name": "Daily",
        "scope_type": "tenant",
        "scope_ref": str(tenant_a.id),
        "backup_type": "full",
        "frequency": "daily",
        "schedule_time": "02:00:00",
        "timezone": "UTC",
        "storage_target_id": target["id"],
        "retention_policy_id": policy["id"],
    }
    schedule = assert_v2(
        authenticated_tenant_a_client.post(f"{PREFIX}/schedules/", schedule_payload, format="json"), 201
    )["data"]
    assert_v2(
        authenticated_tenant_a_client.patch(
            f"{PREFIX}/schedules/{schedule['id']}/", {"description": "updated"}, format="json"
        )
    )
    assert_v2(
        authenticated_tenant_a_client.post(
            f"{PREFIX}/schedules/{schedule['id']}/run-now/", {"idempotency_key": "run-now"}, format="json"
        ),
        202,
    )
    assert_v2(authenticated_tenant_a_client.post(f"{PREFIX}/schedules/{schedule['id']}/deactivate/", {}, format="json"))


def test_archive_and_verification_are_read_only_and_isolated(authenticated_tenant_a_client, tenant_a):
    _, archive = completed_job_with_archive_factory(tenant_a.id)
    detail = assert_v2(authenticated_tenant_a_client.get(f"{PREFIX}/archives/{archive.id}/"))["data"]
    assert detail["artifact_locator_ref"] == archive.artifact_locator_ref
    listed = assert_v2(authenticated_tenant_a_client.get(f"{PREFIX}/archives/"))["data"]
    assert listed[0]["artifact_locator_ref"].startswith("***")
    verification = assert_v2(
        authenticated_tenant_a_client.post(
            f"{PREFIX}/archives/{archive.id}/verify/", {"idempotency_key": "api-verify"}, format="json"
        ),
        202,
    )["data"]
    assert (
        assert_v2(authenticated_tenant_a_client.get(f"{PREFIX}/verifications/{verification['id']}/"))["data"]["status"]
        == "pending"
    )
    cancelled = assert_v2(
        authenticated_tenant_a_client.post(
            f"{PREFIX}/verifications/{verification['id']}/cancel/",
            {"transition_key": "api-verify-cancel"},
            format="json",
        )
    )["data"]
    assert cancelled["status"] == "cancelled"
    assert authenticated_tenant_a_client.delete(f"{PREFIX}/archives/{archive.id}/").status_code == 405


def test_spoofed_system_fields_are_rejected(authenticated_tenant_a_client, tenant_a, tmp_path):
    target = storage_target_factory(tenant_a.id, locator_prefix_ref=str(tmp_path), is_default=True)
    payload = {
        "backup_type": "full",
        "scope_type": "files",
        "scope_ref": str(tmp_path),
        "idempotency_key": "spoof",
        "storage_target_id": str(target.id),
        "tenant_id": str(uuid.uuid4()),
        "status": "completed",
        "checksum_digest": "0" * 64,
    }
    response = authenticated_tenant_a_client.post(f"{PREFIX}/jobs/", payload, format="json")
    assert response.status_code == 400
    assert not BackupJob.objects.filter(tenant_id=tenant_a.id, idempotency_key="spoof").exists()


def test_unknown_action_and_permission_denial_fail_closed(authenticated_tenant_a_client, tenant_a, monkeypatch):
    job = job_factory(tenant_a.id)
    assert authenticated_tenant_a_client.post(f"{PREFIX}/jobs/{job.id}/unknown/", {}, format="json").status_code == 404

    def deny(self, tenant_id, identity, required_permission, **kwargs):
        del self, tenant_id, identity, required_permission, kwargs
        return AccessDecision(False, AccessReasonCode.PERMISSION_DENIED, "denied")

    monkeypatch.setattr(AccessDecisionPipeline, "decide", deny)
    response = authenticated_tenant_a_client.get(f"{PREFIX}/jobs/")
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"]
    assert body["meta"]["correlation_id"]
