from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from src.core.access.decision import AccessDecision, AccessDecisionPipeline, AccessReasonCode
from src.core.async_jobs.services import execute as execute_async_job
from src.core.testing import TEST_PASSWORD

from ..adapter_registry import register_backup_catalog, register_storage_adapter
from ..models import RecoveryPointStatus, RestoreRun, RestoreRunStatus, ScopeType
from ..ports import BackupArtifactDescriptor, BackupType
from ..ports import ScopeType as PortScopeType
from .factories import (
    recovery_point_factory,
    runbook_factory,
    runbook_step_factory,
    step_execution_factory,
)
from .test_services import Catalog, Storage

pytest_plugins = ["src.core.testing"]

PREFIX = "/api/v2/backup-disaster-recovery"


@pytest.fixture(autouse=True)
def allow_access(monkeypatch):
    def decide(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="test access projection",
            tenant_id=uuid.UUID(str(tenant_id)),
        )

    monkeypatch.setattr(AccessDecisionPipeline, "decide", decide)


@pytest.mark.django_db
def test_anonymous_request_is_401(api_client):
    response = api_client.get(f"{PREFIX}/recovery-points/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.django_db
def test_recovery_point_list_is_enveloped_and_paginated(authenticated_tenant_a_client, tenant_a):
    own = recovery_point_factory(tenant_id=tenant_a.id, scope_ref="own")
    recovery_point_factory(scope_ref="other")
    response = authenticated_tenant_a_client.get(f"{PREFIX}/recovery-points/?page_size=1")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["data"][0]["id"] == str(own.id)
    assert body["meta"]["pagination"]["page_size"] == 1
    assert "correlation_id" in body["meta"]


@pytest.mark.django_db
def test_recovery_point_detail_redacts_provider_references(authenticated_tenant_a_client, tenant_a):
    point = recovery_point_factory(
        tenant_id=tenant_a.id,
        artifact_locator_ref="secret/location",
        encryption_key_ref="secret/key",
    )
    response = authenticated_tenant_a_client.get(f"{PREFIX}/recovery-points/{point.id}/")
    assert response.status_code == status.HTTP_200_OK
    serialized = response.json()["data"]
    assert "artifact_locator_ref" not in serialized
    assert "encryption_key_ref" not in serialized
    assert "adapter_key" not in serialized


@pytest.mark.django_db
def test_cross_tenant_detail_is_exact_404(authenticated_tenant_a_client):
    point = recovery_point_factory()
    before = point.__dict__.copy()
    response = authenticated_tenant_a_client.get(f"{PREFIX}/recovery-points/{point.id}/")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    point.refresh_from_db()
    assert point.artifact_locator_ref == before["artifact_locator_ref"]


@pytest.mark.django_db
def test_legacy_resource_route_and_put_are_not_exposed(authenticated_tenant_a_client, tenant_a):
    assert authenticated_tenant_a_client.get("/api/v1/backup-disaster-recovery/resources/").status_code == 404
    point = recovery_point_factory(tenant_id=tenant_a.id)
    response = authenticated_tenant_a_client.put(
        f"{PREFIX}/recovery-points/{point.id}/", {"status": "available"}, format="json"
    )
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
def test_unknown_filter_is_422(authenticated_tenant_a_client):
    response = authenticated_tenant_a_client.get(f"{PREFIX}/recovery-points/?tenant_id=spoof")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_policy_denial_is_403_with_stable_envelope(authenticated_tenant_a_client, monkeypatch):
    def deny(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision.deny(
            AccessReasonCode.POLICY_DENIED,
            "denied",
            tenant_id=uuid.UUID(str(tenant_id)),
        )

    monkeypatch.setattr(AccessDecisionPipeline, "decide", deny)
    response = authenticated_tenant_a_client.get(f"{PREFIX}/readiness/")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "POLICY_DENIED"


@pytest.mark.django_db
def test_unmapped_framework_action_fails_closed(authenticated_tenant_a_client):
    response = authenticated_tenant_a_client.options(f"{PREFIX}/recovery-points/")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_csrf_is_enforced_for_runbook_create(tenant_a_user):
    client = APIClient(enforce_csrf_checks=True)
    assert client.login(username=tenant_a_user.username, password=TEST_PASSWORD)
    response = client.post(
        f"{PREFIX}/runbooks/",
        {
            "name": "Primary",
            "slug": "primary",
            "scope_type": ScopeType.TENANT,
            "scope_ref": "primary",
            "adapter_key": "local-filesystem",
            "rpo_target_seconds": 3600,
            "rto_target_seconds": 7200,
            "owner_id": str(uuid.uuid4()),
        },
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_runbook_create_detail_and_step_filter(authenticated_tenant_a_client, tenant_a):
    runbook = runbook_factory(tenant_id=tenant_a.id)
    step = runbook_step_factory(runbook)
    detail = authenticated_tenant_a_client.get(f"{PREFIX}/runbooks/{runbook.id}/")
    assert detail.status_code == status.HTTP_200_OK
    assert detail.json()["data"]["steps"][0]["id"] == str(step.id)
    missing_filter = authenticated_tenant_a_client.get(f"{PREFIX}/runbook-steps/")
    assert missing_filter.status_code == status.HTTP_400_BAD_REQUEST
    listed = authenticated_tenant_a_client.get(f"{PREFIX}/runbook-steps/?runbook_id={runbook.id}")
    assert listed.status_code == status.HTTP_200_OK
    assert listed.json()["data"][0]["id"] == str(step.id)


@pytest.mark.django_db
def test_read_only_step_evidence_rejects_writes(authenticated_tenant_a_client):
    response = authenticated_tenant_a_client.post(f"{PREFIX}/step-executions/", {}, format="json")
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
def test_complete_governed_api_workflow(authenticated_tenant_a_client, tenant_a):
    """Exercise every mutable v2 resource through its public HTTP contract."""

    client = authenticated_tenant_a_client
    now = timezone.now()
    backup_job_id = uuid.uuid4()
    descriptor = BackupArtifactDescriptor(
        backup_job_id=backup_job_id,
        backup_archive_id=None,
        adapter_key="local-filesystem",
        artifact_locator_ref="tenant/backup.bin",
        encryption_key_ref=None,
        scope_type=PortScopeType.TENANT,
        scope_ref="primary",
        backup_type=BackupType.FULL,
        data_cutoff_at=now - timedelta(minutes=5),
        captured_at=now,
        expires_at=now + timedelta(days=30),
        size_bytes=4,
        checksum_algorithm="sha256",
        checksum_digest="a" * 64,
        provider_acknowledgement="catalog-ack",
    )
    register_backup_catalog("default", Catalog(descriptor), replace=True)
    register_storage_adapter("local-filesystem", Storage(), replace=True)

    backup = client.post(
        f"{PREFIX}/backup-executions/",
        {
            "backup_type": "full",
            "scope_type": "tenant",
            "scope_ref": "primary",
            "idempotency_key": "api-backup",
        },
        format="json",
    )
    assert backup.status_code == status.HTTP_202_ACCEPTED
    backup_data = backup.json()["data"]
    assert backup_data["backup_job_id"] == str(backup_job_id)
    assert backup_data["requested_at"]
    backup_status = client.get(f"{PREFIX}/backup-executions/{backup_job_id}/")
    assert backup_status.status_code == status.HTTP_200_OK
    assert backup_status.json()["data"]["status"] == "completed"

    point = recovery_point_factory(
        tenant_id=tenant_a.id,
        adapter_key="local-filesystem",
        status=RecoveryPointStatus.AVAILABLE,
        verified_at=now,
        scope_ref="primary",
    )
    verification = client.post(
        f"{PREFIX}/recovery-points/{point.id}/verify/",
        {"idempotency_key": "api-verify"},
        format="json",
    )
    assert verification.status_code == status.HTTP_202_ACCEPTED
    assert verification.json()["data"]["accepted_at"]

    expirable = recovery_point_factory(
        tenant_id=tenant_a.id,
        adapter_key="local-filesystem",
        status=RecoveryPointStatus.AVAILABLE,
        verified_at=now - timedelta(days=2),
        captured_at=now - timedelta(days=2),
        data_cutoff_at=now - timedelta(days=3),
        expires_at=now - timedelta(days=1),
    )
    expired = client.post(
        f"{PREFIX}/recovery-points/{expirable.id}/expire/",
        {"transition_key": "api-expire"},
        format="json",
    )
    assert expired.status_code == status.HTTP_200_OK
    assert expired.json()["data"]["status"] == "expired"
    restore_point = recovery_point_factory(
        tenant_id=tenant_a.id,
        backup_job_id=backup_job_id,
        adapter_key="local-filesystem",
        status=RecoveryPointStatus.AVAILABLE,
        verified_at=now,
        scope_ref="primary",
    )

    with override_settings(BDR_STORAGE_ADAPTER_KEY="local-filesystem"):
        created = client.post(
            f"{PREFIX}/runbooks/",
            {
                "name": "API recovery plan",
                "slug": "api-recovery-plan",
                "description": "Executable tenant recovery",
                "scope_type": "tenant",
                "scope_ref": "primary",
                "rpo_target_seconds": 3600,
                "rto_target_seconds": 7200,
            },
            format="json",
        )
    assert created.status_code == status.HTTP_201_CREATED
    runbook_id = created.json()["data"]["id"]
    updated = client.patch(
        f"{PREFIX}/runbooks/{runbook_id}/",
        {"name": "API recovery plan updated"},
        format="json",
    )
    assert updated.status_code == status.HTTP_200_OK

    first_step = client.post(
        f"{PREFIX}/runbook-steps/",
        {
            "runbook_id": runbook_id,
            "step_key": "validate",
            "position": 1,
            "name": "Validate recovery point",
            "description": "Verify integrity before restoration.",
            "action_type": "validate_recovery_point",
            "parameters": {"require_checksum": True, "require_encryption": True},
            "timeout_seconds": 300,
            "retry_limit": 0,
            "on_failure": "stop",
        },
        format="json",
    )
    second_step = client.post(
        f"{PREFIX}/runbook-steps/",
        {
            "runbook_id": runbook_id,
            "step_key": "verify",
            "position": 2,
            "name": "Verify restored service",
            "description": "Run application verification.",
            "action_type": "verify",
            "parameters": {"checks": ["integrity", "application"]},
            "timeout_seconds": 300,
            "retry_limit": 1,
            "on_failure": "stop",
        },
        format="json",
    )
    assert first_step.status_code == second_step.status_code == status.HTTP_201_CREATED
    first_step_id = first_step.json()["data"]["id"]
    second_step_id = second_step.json()["data"]["id"]
    patched_step = client.patch(
        f"{PREFIX}/runbook-steps/{second_step_id}/",
        {"name": "Verify restored application"},
        format="json",
    )
    assert patched_step.status_code == status.HTTP_200_OK
    reordered = client.post(
        f"{PREFIX}/runbooks/{runbook_id}/reorder-steps/",
        {"step_ids": [second_step_id, first_step_id]},
        format="json",
    )
    assert reordered.status_code == status.HTTP_200_OK
    assert [row["position"] for row in reordered.json()["data"]] == [1, 2]

    published = client.post(
        f"{PREFIX}/runbooks/{runbook_id}/publish/",
        {"transition_key": "api-publish"},
        format="json",
    )
    assert published.status_code == status.HTTP_200_OK
    assert published.json()["data"]["status"] == "published"
    listed_runbooks = client.get(f"{PREFIX}/runbooks/?status=published&search=updated&ordering=name")
    assert listed_runbooks.status_code == status.HTTP_200_OK

    restore = client.post(
        f"{PREFIX}/restore-runs/",
        {
            "recovery_point_id": str(restore_point.id),
            "runbook_id": runbook_id,
            "target_environment": "isolated",
            "target_ref": "api-sandbox",
            "restore_mode": "full",
            "selected_components": [],
            "idempotency_key": "api-restore",
        },
        format="json",
    )
    assert restore.status_code == status.HTTP_202_ACCEPTED, restore.json()
    restore_data = restore.json()["data"]
    restore_id = restore_data["id"]
    validation_job = execute_async_job(restore_data["async_job_id"], tenant_a.id)
    assert validation_job.status == "succeeded"
    validated_restore = RestoreRun.objects.get(id=restore_id)
    assert validated_restore.status == RestoreRunStatus.READY
    assert validated_restore.validation_evidence["artifact_valid"] is True
    assert [entry["command"] for entry in validated_restore.transition_history] == [
        "begin_validation",
        "mark_ready",
    ]
    execute = client.post(
        f"{PREFIX}/restore-runs/{restore_id}/execute/",
        {"idempotency_key": "api-restore-execute"},
        format="json",
    )
    assert execute.status_code == status.HTTP_202_ACCEPTED
    assert execute.json()["data"]["accepted_at"]
    assert client.get(f"{PREFIX}/restore-runs/{restore_id}/").status_code == status.HTTP_200_OK
    assert client.get(f"{PREFIX}/restore-runs/?status=ready").status_code == status.HTTP_200_OK

    cancellable = client.post(
        f"{PREFIX}/restore-runs/",
        {
            "recovery_point_id": str(restore_point.id),
            "target_environment": "isolated",
            "target_ref": "cancel-sandbox",
            "restore_mode": "full",
            "selected_components": [],
            "idempotency_key": "api-restore-cancel",
        },
        format="json",
    )
    cancelled = client.post(
        f"{PREFIX}/restore-runs/{cancellable.json()['data']['id']}/cancel/",
        {"transition_key": "api-cancel"},
        format="json",
    )
    assert cancelled.status_code == status.HTTP_200_OK
    assert cancelled.json()["data"]["status"] == "cancelled"
    production = client.post(
        f"{PREFIX}/restore-runs/",
        {
            "recovery_point_id": str(restore_point.id),
            "target_environment": "production",
            "target_ref": "production",
            "restore_mode": "full",
            "selected_components": [],
            "idempotency_key": "api-production",
            "step_up_token": "opaque-proof",
        },
        format="json",
    )
    assert production.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert production.json()["error"]["code"] == "CAPABILITY_UNAVAILABLE"

    exercise = client.post(
        f"{PREFIX}/exercises/",
        {
            "name": "API exercise",
            "runbook_id": runbook_id,
            "recovery_point_id": str(restore_point.id),
            "exercise_type": "tabletop",
            "environment": "isolated",
            "scheduled_for": (now + timedelta(days=1)).isoformat(),
            "idempotency_key": "api-exercise",
        },
        format="json",
    )
    assert exercise.status_code == status.HTTP_201_CREATED
    exercise_id = exercise.json()["data"]["id"]
    edited_exercise = client.patch(
        f"{PREFIX}/exercises/{exercise_id}/",
        {"name": "API exercise updated"},
        format="json",
    )
    assert edited_exercise.status_code == status.HTTP_200_OK
    started = client.post(
        f"{PREFIX}/exercises/{exercise_id}/start/",
        {"idempotency_key": "api-exercise-start"},
        format="json",
    )
    assert started.status_code == status.HTTP_202_ACCEPTED
    assert started.json()["data"]["accepted_at"]
    assert client.get(f"{PREFIX}/exercises/?status=queued").status_code == status.HTTP_200_OK

    runbook = validated_restore.runbook
    assert runbook is not None
    cancel_exercise = client.post(
        f"{PREFIX}/exercises/",
        {
            "name": "Cancelled exercise",
            "runbook_id": str(runbook.id),
            "exercise_type": "tabletop",
            "environment": "standby",
            "scheduled_for": (now + timedelta(days=2)).isoformat(),
            "idempotency_key": "api-exercise-cancel",
        },
        format="json",
    )
    cancelled_exercise = client.post(
        f"{PREFIX}/exercises/{cancel_exercise.json()['data']['id']}/cancel/",
        {"transition_key": "api-exercise-cancel-transition"},
        format="json",
    )
    assert cancelled_exercise.status_code == status.HTTP_200_OK

    step_row = runbook.steps.get(id=first_step_id)
    execution = step_execution_factory(
        cancel_exercise.json()["data"] and runbook.exercises.get(id=cancel_exercise.json()["data"]["id"]),
        step_row,
    )
    assert client.get(f"{PREFIX}/step-executions/?exercise={execution.exercise_id}").status_code == 200
    assert client.get(f"{PREFIX}/step-executions/{execution.id}/").status_code == 200

    clone = client.post(f"{PREFIX}/runbooks/{runbook_id}/clone/", {"name": "Version two"}, format="json")
    assert clone.status_code == status.HTTP_201_CREATED
    clone_id = clone.json()["data"]["id"]
    clone_detail = client.get(f"{PREFIX}/runbooks/{clone_id}/")
    clone_step_id = clone_detail.json()["data"]["steps"][0]["id"]
    assert client.delete(f"{PREFIX}/runbook-steps/{clone_step_id}/").status_code == 204
    assert client.delete(f"{PREFIX}/runbooks/{clone_id}/").status_code == 204
    retired = client.post(
        f"{PREFIX}/runbooks/{runbook_id}/retire/",
        {"transition_key": "api-retire"},
        format="json",
    )
    assert retired.status_code == status.HTTP_200_OK
    assert client.get(f"{PREFIX}/reports/objectives/?bucket=day").status_code == 200
    readiness = client.get(f"{PREFIX}/readiness/")
    assert readiness.status_code == 200
    assert "provider_state" in readiness.json()["data"]
