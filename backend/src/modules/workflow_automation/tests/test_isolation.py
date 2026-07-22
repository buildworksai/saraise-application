"""Tenant isolation at HTTP, relationship, RLS, and worker boundaries."""

from __future__ import annotations

import uuid

import pytest
from django.db import connection
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue, execute
from src.core.tenancy import tenant_context
from src.core.testing.tenant_contract import TenantIsolationContract
from src.modules.security_access_control.models import Role

from ..jobs import execute_instance_handler
from ..models import Workflow, WorkflowInstance, WorkflowStep, WorkflowTask
from ..services import EXECUTE_INSTANCE_COMMAND, WorkflowDefinitionService, WorkflowExecutionService
from .factories import WorkflowInstanceFactory, WorkflowTaskFactory
from .test_services import action_payload

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def allow_access_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    def allow(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="allowed for isolation contract",
            tenant_id=uuid.UUID(str(tenant_id)),
            remaining_quota=100,
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", allow)


class TestWorkflowIsolation(TenantIsolationContract):
    model = Workflow
    list_url = "/api/v2/workflow-automation/workflows/"
    detail_url_template = "/api/v2/workflow-automation/workflows/{pk}/"
    create_payload = action_payload(key="spoof-attempt")
    read_denial_statuses = frozenset({status.HTTP_404_NOT_FOUND})

    @pytest.fixture(autouse=True)
    def isolation_context(self, tenant_a_client, tenant_a, tenant_b, tenant_a_user, tenant_b_user):
        self.client = tenant_a_client
        self.tenant_a_row = WorkflowDefinitionService.create_workflow(
            tenant_a.id, tenant_a_user, action_payload(key="tenant-a-definition")
        )
        self.tenant_b_row = WorkflowDefinitionService.create_workflow(
            tenant_b.id, tenant_b_user, action_payload(key="tenant-b-definition")
        )

    def get_list_items(self, response):
        return response.json()["data"]

    def get_update_payload(self):
        return {
            "name": "Cross-tenant mutation",
            "expected_updated_at": self.tenant_b_row.updated_at.isoformat(),
        }


def test_nested_step_tenant_spoof_is_rejected_on_create_and_update(
    tenant_a_client, tenant_a, tenant_b, tenant_a_user
) -> None:
    payload = action_payload(key="nested-create-spoof")
    payload["steps"][0]["tenant_id"] = str(tenant_b.id)
    response = tenant_a_client.post(
        "/api/v2/workflow-automation/workflows/", payload, format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    workflow = WorkflowDefinitionService.create_workflow(
        tenant_a.id, tenant_a_user, action_payload(key="nested-update-spoof")
    )
    steps = action_payload()["steps"]
    steps[0]["tenant_id"] = str(tenant_b.id)
    response = tenant_a_client.patch(
        f"/api/v2/workflow-automation/workflows/{workflow.id}/",
        {"expected_updated_at": workflow.updated_at.isoformat(), "steps": steps},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert WorkflowStep.objects.for_tenant(tenant_b.id).filter(workflow_id=workflow.id).count() == 0


def test_cross_tenant_definition_actions_and_start_are_404_without_side_effects(
    tenant_a_client, tenant_b, tenant_b_user
) -> None:
    workflow = WorkflowDefinitionService.create_workflow(
        tenant_b.id, tenant_b_user, action_payload(key="tenant-b-actions")
    )
    workflow = WorkflowDefinitionService.publish_workflow(
        tenant_b.id, workflow.id, tenant_b_user, "tenant-b-publish"
    )
    before = (workflow.status, workflow.version, workflow.updated_at)
    for suffix, payload in (
        ("publish", {"transition_key": "foreign-publish"}),
        ("archive", {"transition_key": "foreign-archive"}),
        ("clone", {}),
    ):
        response = tenant_a_client.post(
            f"/api/v2/workflow-automation/workflows/{workflow.id}/{suffix}/",
            payload,
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    workflow.refresh_from_db()
    assert (workflow.status, workflow.version, workflow.updated_at) == before

    jobs_before = AsyncJob.objects.count()
    events_before = OutboxEvent.objects.count()
    response = tenant_a_client.post(
        "/api/v2/workflow-automation/instances/",
        {
            "workflow_id": str(workflow.id),
            "context_data": {},
            "idempotency_key": "foreign-workflow-start",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert AsyncJob.objects.count() == jobs_before
    assert OutboxEvent.objects.count() == events_before
    assert WorkflowInstance.objects.filter(idempotency_key="foreign-workflow-start").count() == 0


def test_cross_tenant_instance_list_detail_and_cancel(
    tenant_a_client, tenant_a, tenant_b, tenant_a_user, tenant_b_user
) -> None:
    instance_a = WorkflowInstanceFactory(tenant_id=tenant_a.id, started_by=tenant_a_user)
    instance_b = WorkflowInstanceFactory(tenant_id=tenant_b.id, started_by=tenant_b_user)
    listing = tenant_a_client.get("/api/v2/workflow-automation/instances/")
    identifiers = {item["id"] for item in listing.json()["data"]}
    assert str(instance_a.id) in identifiers
    assert str(instance_b.id) not in identifiers
    assert tenant_a_client.get(
        f"/api/v2/workflow-automation/instances/{instance_b.id}/"
    ).status_code == status.HTTP_404_NOT_FOUND
    before = (instance_b.state, instance_b.updated_at)
    response = tenant_a_client.post(
        f"/api/v2/workflow-automation/instances/{instance_b.id}/cancel/",
        {"transition_key": "foreign-cancel"},
        format="json",
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    instance_b.refresh_from_db()
    assert (instance_b.state, instance_b.updated_at) == before


def test_cross_tenant_task_list_detail_complete_and_reject(
    tenant_a_client, tenant_a, tenant_b, tenant_a_user, tenant_b_user
) -> None:
    task_a = WorkflowTaskFactory(
        tenant_id=tenant_a.id,
        assignment_kind="user",
        assignee=tenant_a_user,
        assignee_role_id=None,
        assignment_key=f"user:{tenant_a_user.pk}",
    )
    task_b = WorkflowTaskFactory(
        tenant_id=tenant_b.id,
        assignment_kind="user",
        assignee=tenant_b_user,
        assignee_role_id=None,
        assignment_key=f"user:{tenant_b_user.pk}",
    )
    listing = tenant_a_client.get("/api/v2/workflow-automation/tasks/")
    identifiers = {item["id"] for item in listing.json()["data"]}
    assert str(task_a.id) in identifiers
    assert str(task_b.id) not in identifiers
    assert tenant_a_client.get(
        f"/api/v2/workflow-automation/tasks/{task_b.id}/"
    ).status_code == status.HTTP_404_NOT_FOUND
    before = (task_b.status, task_b.meta_data, task_b.updated_at)
    for suffix, payload in (
        ("complete", {"meta_data": {}, "transition_key": "foreign-complete"}),
        (
            "reject",
            {"reason": "Not authorized", "meta_data": {}, "transition_key": "foreign-reject"},
        ),
    ):
        response = tenant_a_client.post(
            f"/api/v2/workflow-automation/tasks/{task_b.id}/{suffix}/", payload, format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    task_b.refresh_from_db()
    assert (task_b.status, task_b.meta_data, task_b.updated_at) == before


def test_role_assignment_cannot_resolve_another_tenant_role(
    tenant_a, tenant_b, tenant_a_user
) -> None:
    foreign_role = Role.objects.create(
        tenant_id=tenant_b.id,
        name="Tenant B approver",
        code="tenant_b_approver",
    )
    payload = action_payload(key="foreign-role")
    payload["workflow_type"] = "approval"
    payload["steps"] = [
        {
            "key": "approve",
            "name": "Approve",
            "step_type": "approval",
            "order": 1,
            "config": {
                "assignment_kind": "role",
                "assignee_id": str(foreign_role.id),
                "rejection_behavior": "fail",
            },
            "is_terminal": True,
            "next_step_keys": [],
            "join_key": "",
        }
    ]
    workflow = WorkflowDefinitionService.create_workflow(tenant_a.id, tenant_a_user, payload)
    workflow = WorkflowDefinitionService.publish_workflow(
        tenant_a.id, workflow.id, tenant_a_user, "foreign-role-publish"
    )
    instance = WorkflowExecutionService.start_workflow(
        tenant_a.id, workflow.id, tenant_a_user, {}, "foreign-role-start"
    )
    execute(instance.async_job_id, tenant_a.id)
    instance.refresh_from_db()
    assert instance.state == "failed"
    assert instance.failure_code == "ASSIGNEE_ROLE_NOT_FOUND"
    assert WorkflowTask.objects.for_tenant(tenant_a.id).filter(instance=instance).count() == 0


def test_worker_tenant_context_cannot_read_foreign_instance(tenant_a, tenant_b, tenant_a_user) -> None:
    foreign = WorkflowInstanceFactory(tenant_id=tenant_b.id)
    job = enqueue(
        tenant_a.id,
        tenant_a_user.pk,
        EXECUTE_INSTANCE_COMMAND,
        {"instance_id": str(foreign.id)},
        "malicious-cross-tenant-worker",
    )
    with pytest.raises(Exception):
        execute_instance_handler(job)
    foreign.refresh_from_db()
    assert foreign.state == "pending"


def test_postgresql_rls_blocks_wrong_database_context(tenant_a, tenant_b) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("RLS is enforced by PostgreSQL")
    foreign = WorkflowInstanceFactory(tenant_id=tenant_b.id)
    with tenant_context(tenant_a.id):
        assert WorkflowInstance._base_manager.filter(id=foreign.id).count() == 0
