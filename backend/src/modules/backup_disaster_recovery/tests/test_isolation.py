from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessDecisionPipeline, AccessReasonCode
from src.core.testing.tenant_contract import TenantIsolationContract

from ..models import (
    DRExercise,
    DRRunbook,
    DRStepExecution,
    RecoveryPoint,
    RecoveryPointStatus,
    RestoreRun,
    RunbookStep,
    ScopeType,
)
from ..state_machines import RUNBOOK_MACHINE
from .factories import (
    exercise_factory,
    recovery_point_factory,
    restore_run_factory,
    runbook_factory,
    runbook_step_factory,
    step_execution_factory,
)

pytest_plugins = ["src.core.testing"]

PREFIX = "/api/v2/backup-disaster-recovery"


@pytest.fixture(autouse=True)
def allow_access(monkeypatch):
    def decide(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(True, AccessReasonCode.ALLOW, "allowed", tenant_id=uuid.UUID(str(tenant_id)))

    monkeypatch.setattr(AccessDecisionPipeline, "decide", decide)


class V2IsolationContract(TenantIsolationContract):
    read_denial_statuses = frozenset(
        {status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED}
    )
    write_denial_statuses = frozenset(
        {
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        }
    )

    def get_list_items(self, response):
        return response.json()["data"]


@pytest.mark.django_db
class TestDRRunbookIsolation(V2IsolationContract):
    model = DRRunbook
    list_url = f"{PREFIX}/runbooks/"
    detail_url_template = f"{PREFIX}/runbooks/{{pk}}/"
    update_payload = {"name": "Cross-tenant mutation"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = runbook_factory(tenant_id=tenant_a.id, slug="tenant-a")
        self.tenant_b_row = runbook_factory(tenant_id=tenant_b.id, slug="tenant-b")
        self.create_payload = {
            "name": "Spoof attempt",
            "slug": f"spoof-{uuid.uuid4().hex[:8]}",
            "description": "must bind to authenticated tenant",
            "scope_type": ScopeType.TENANT,
            "scope_ref": "primary",
            "adapter_key": "local-filesystem",
            "rpo_target_seconds": 3600,
            "rto_target_seconds": 7200,
            "owner_id": str(uuid.uuid4()),
        }


@pytest.mark.django_db
class TestRunbookStepIsolation(V2IsolationContract):
    model = RunbookStep
    detail_url_template = f"{PREFIX}/runbook-steps/{{pk}}/"
    update_payload = {"name": "Cross-tenant mutation"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        runbook_a = runbook_factory(tenant_id=tenant_a.id, slug="steps-a")
        runbook_b = runbook_factory(tenant_id=tenant_b.id, slug="steps-b")
        self.tenant_a_row = runbook_step_factory(runbook_a, step_key="validate-a")
        self.tenant_b_row = runbook_step_factory(runbook_b, step_key="validate-b")
        self.list_url = f"{PREFIX}/runbook-steps/?runbook_id={runbook_a.id}"
        self.create_payload = {
            "runbook_id": str(runbook_a.id),
            "step_key": f"step-{uuid.uuid4().hex[:8]}",
            "position": 2,
            "name": "Validate artifact",
            "action_type": "validate_recovery_point",
            "parameters": {"require_checksum": True, "require_encryption": True},
            "timeout_seconds": 300,
            "retry_limit": 0,
            "on_failure": "stop",
        }


@pytest.mark.django_db
class TestRecoveryPointIsolation(V2IsolationContract):
    model = RecoveryPoint
    list_url = f"{PREFIX}/recovery-points/"
    detail_url_template = f"{PREFIX}/recovery-points/{{pk}}/"
    create_payload = {}
    update_payload = {"status": "expired"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = recovery_point_factory(tenant_id=tenant_a.id, scope_ref="recovery-a")
        self.tenant_b_row = recovery_point_factory(tenant_id=tenant_b.id, scope_ref="recovery-b")


@pytest.mark.django_db
class TestRestoreRunIsolation(V2IsolationContract):
    model = RestoreRun
    list_url = f"{PREFIX}/restore-runs/"
    detail_url_template = f"{PREFIX}/restore-runs/{{pk}}/"
    create_success_statuses = frozenset({status.HTTP_202_ACCEPTED})
    update_payload = {"target_ref": "cross-tenant-mutation"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        point_a = recovery_point_factory(
            tenant_id=tenant_a.id,
            scope_ref="restore-a",
            status=RecoveryPointStatus.AVAILABLE,
            verified_at=timezone.now(),
        )
        point_b = recovery_point_factory(
            tenant_id=tenant_b.id,
            scope_ref="restore-b",
            status=RecoveryPointStatus.AVAILABLE,
            verified_at=timezone.now(),
        )
        self.tenant_a_row = restore_run_factory(point_a, target_ref="tenant-a-target")
        self.tenant_b_row = restore_run_factory(point_b, target_ref="tenant-b-target")
        self.create_payload = {
            "recovery_point_id": str(point_a.id),
            "target_environment": "isolated",
            "target_ref": f"spoof-{uuid.uuid4()}",
            "restore_mode": "full",
            "selected_components": [],
            "idempotency_key": f"isolation-{uuid.uuid4()}",
        }


@pytest.mark.django_db
class TestDRExerciseIsolation(V2IsolationContract):
    model = DRExercise
    list_url = f"{PREFIX}/exercises/"
    detail_url_template = f"{PREFIX}/exercises/{{pk}}/"
    update_payload = {"name": "Cross-tenant mutation"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        runbook_a = runbook_factory(tenant_id=tenant_a.id, slug="exercise-a")
        runbook_step_factory(runbook_a, step_key="exercise-step-a")
        RUNBOOK_MACHINE.apply(runbook_a, "publish", transition_key="publish-exercise-a")
        runbook_b = runbook_factory(tenant_id=tenant_b.id, slug="exercise-b")
        runbook_step_factory(runbook_b, step_key="exercise-step-b")
        RUNBOOK_MACHINE.apply(runbook_b, "publish", transition_key="publish-exercise-b")
        self.tenant_a_row = exercise_factory(runbook_a, name="Tenant A exercise")
        self.tenant_b_row = exercise_factory(runbook_b, name="Tenant B exercise")
        self.create_payload = {
            "name": "Spoof attempt",
            "runbook_id": str(runbook_a.id),
            "exercise_type": "tabletop",
            "environment": "isolated",
            "scheduled_for": (timezone.now() + timedelta(days=1)).isoformat(),
            "idempotency_key": f"isolation-{uuid.uuid4()}",
        }


@pytest.mark.django_db
class TestDRStepExecutionIsolation(V2IsolationContract):
    model = DRStepExecution
    detail_url_template = f"{PREFIX}/step-executions/{{pk}}/"
    create_payload = {}
    update_payload = {"status": "passed"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        runbook_a = runbook_factory(tenant_id=tenant_a.id, slug="execution-a")
        step_a = runbook_step_factory(runbook_a, step_key="execution-step-a")
        RUNBOOK_MACHINE.apply(runbook_a, "publish", transition_key="publish-execution-a")
        exercise_a = exercise_factory(runbook_a, name="Tenant A execution exercise")
        runbook_b = runbook_factory(tenant_id=tenant_b.id, slug="execution-b")
        step_b = runbook_step_factory(runbook_b, step_key="execution-step-b")
        RUNBOOK_MACHINE.apply(runbook_b, "publish", transition_key="publish-execution-b")
        exercise_b = exercise_factory(runbook_b, name="Tenant B execution exercise")
        self.tenant_a_row = step_execution_factory(exercise_a, step_a)
        self.tenant_b_row = step_execution_factory(exercise_b, step_b)
        self.list_url = f"{PREFIX}/step-executions/?exercise={exercise_a.id}"


@pytest.mark.django_db
def test_recovery_point_list_and_detail_isolation(authenticated_tenant_a_client, tenant_a, tenant_b):
    own = recovery_point_factory(tenant_id=tenant_a.id, scope_ref="own")
    other = recovery_point_factory(tenant_id=tenant_b.id, scope_ref="other")
    body = authenticated_tenant_a_client.get(f"{PREFIX}/recovery-points/").json()
    identities = {row["id"] for row in body["data"]}
    assert str(own.id) in identities
    assert str(other.id) not in identities
    assert authenticated_tenant_a_client.get(f"{PREFIX}/recovery-points/{other.id}/").status_code == 404


@pytest.mark.django_db
def test_spoofed_tenant_filter_is_rejected_without_mutation(authenticated_tenant_a_client, tenant_b):
    other = recovery_point_factory(tenant_id=tenant_b.id)
    before = DRRunbook.objects.count()
    response = authenticated_tenant_a_client.get(f"{PREFIX}/recovery-points/?tenant_id={tenant_b.id}")
    assert response.status_code == 400
    assert DRRunbook.objects.count() == before
    other.refresh_from_db()
