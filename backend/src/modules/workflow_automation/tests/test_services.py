"""Service-layer contracts for workflow definitions and executions."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import execute
from src.core.testing.factories import TenantUserFactory

from ..models import WorkflowInstance, WorkflowStepExecution, WorkflowTask
from ..services import (
    SaraiseWorkflowExecutionAdapter,
    WorkflowDefinitionService,
    WorkflowExecutionService,
    WorkflowTaskService,
)

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db


def action_payload(*, key: str = "purchase-approval") -> dict[str, object]:
    return {
        "key": key,
        "name": "Purchase approval",
        "description": "A durable purchase approval workflow",
        "workflow_type": "sequential",
        "trigger_type": "manual",
        "trigger_config": {},
        "required_context_schema": {
            "type": "object",
            "properties": {"approved": {"type": "boolean"}},
            "additionalProperties": True,
        },
        "steps": [
            {
                "key": "complete",
                "name": "Complete",
                "step_type": "action",
                "order": 1,
                "config": {
                    "handler": "core.terminal_completion.v1",
                    "schema_version": "1",
                    "input_mapping": {},
                    "configuration": {},
                },
                "is_terminal": True,
                "next_step_keys": [],
                "join_key": "",
            }
        ],
    }


def approval_payload(user_id: object) -> dict[str, object]:
    payload = action_payload(key="human-approval")
    payload["workflow_type"] = "approval"
    payload["steps"] = [
        {
            "key": "approve",
            "name": "Manager approval",
            "step_type": "approval",
            "order": 1,
            "config": {
                "assignment_kind": "user",
                "assignee_id": str(user_id),
                "due_in_seconds": 3600,
                "rejection_behavior": "fail",
                "completion_rule": "any",
            },
            "is_terminal": True,
            "next_step_keys": [],
            "join_key": "",
        }
    ]
    return payload


def publish(tenant_id, actor, payload=None):
    workflow = WorkflowDefinitionService.create_workflow(tenant_id, actor, payload or action_payload())
    return WorkflowDefinitionService.publish_workflow(tenant_id, workflow.id, actor, "publish-v1")


def run_job(instance):
    assert instance.async_job_id is not None
    return execute(instance.async_job_id, instance.tenant_id)


def test_definition_create_update_publish_clone_archive_delete(tenant_a, tenant_a_user) -> None:
    workflow = WorkflowDefinitionService.create_workflow(tenant_a.id, tenant_a_user, action_payload())
    assert workflow.tenant_id == tenant_a.id
    assert workflow.steps.count() == 1
    assert OutboxEvent.objects.for_tenant(tenant_a.id).filter(event_type="workflow.definition.created").exists()

    updated = WorkflowDefinitionService.update_workflow(
        tenant_a.id,
        workflow.id,
        tenant_a_user,
        {"name": "Updated approval", "expected_updated_at": workflow.updated_at},
    )
    assert updated.name == "Updated approval"

    published = WorkflowDefinitionService.publish_workflow(
        tenant_a.id, workflow.id, tenant_a_user, "publish-once"
    )
    replay = WorkflowDefinitionService.publish_workflow(
        tenant_a.id, workflow.id, tenant_a_user, "publish-once"
    )
    assert replay.status == published.status == "published"
    clone = WorkflowDefinitionService.clone_version(tenant_a.id, workflow.id, tenant_a_user)
    assert (clone.status, clone.version, clone.key) == ("draft", 2, workflow.key)
    archived = WorkflowDefinitionService.archive_workflow(
        tenant_a.id, workflow.id, tenant_a_user, "archive-v1"
    )
    assert archived.status == "archived"
    WorkflowDefinitionService.delete_draft(tenant_a.id, clone.id, tenant_a_user)
    assert WorkflowDefinitionService.list_workflows(tenant_a.id).filter(id=clone.id).count() == 0


def test_definition_validation_not_found_and_optimistic_conflict(tenant_a, tenant_a_user) -> None:
    invalid = action_payload()
    invalid["name"] = " "
    result = WorkflowDefinitionService.validate_definition(tenant_a.id, invalid)
    assert result.valid is False
    assert any(issue.code == "NAME_REQUIRED" for issue in result.issues)
    with pytest.raises(NotFound):
        WorkflowDefinitionService.get_workflow(tenant_a.id, uuid.uuid4())

    workflow = WorkflowDefinitionService.create_workflow(tenant_a.id, tenant_a_user, action_payload())
    with pytest.raises(Exception, match="changed after it was loaded"):
        WorkflowDefinitionService.update_workflow(
            tenant_a.id,
            workflow.id,
            tenant_a_user,
            {"name": "Stale", "expected_updated_at": workflow.updated_at - timedelta(seconds=1)},
        )


def test_start_is_idempotent_and_durable_job_records_evidence(tenant_a, tenant_a_user) -> None:
    workflow = publish(tenant_a.id, tenant_a_user)
    first = WorkflowExecutionService.start_workflow(
        tenant_a.id, workflow.id, tenant_a_user, {"approved": True}, "start-42"
    )
    replay = WorkflowExecutionService.start_workflow(
        tenant_a.id, workflow.id, tenant_a_user, {"approved": True}, "start-42"
    )
    assert first.id == replay.id
    assert first.state == "pending"
    assert AsyncJob.objects.for_tenant(tenant_a.id).filter(id=first.async_job_id).count() == 1

    completed_job = run_job(first)
    first.refresh_from_db()
    assert completed_job.status == "succeeded"
    assert first.state == "completed"
    execution = WorkflowStepExecution.objects.for_tenant(tenant_a.id).get(instance=first)
    assert execution.state == "succeeded"
    assert execution.handler_key == "core.terminal_completion.v1"
    assert execution.output_evidence["terminal_marker"]
    assert execute(completed_job.id, tenant_a.id).attempts == completed_job.attempts


def test_start_rejects_draft_bad_context_and_cross_tenant(tenant_a, tenant_b, tenant_a_user) -> None:
    draft = WorkflowDefinitionService.create_workflow(tenant_a.id, tenant_a_user, action_payload())
    with pytest.raises(Exception, match="published"):
        WorkflowExecutionService.start_workflow(tenant_a.id, draft.id, tenant_a_user, {}, "draft")
    with pytest.raises(NotFound):
        WorkflowExecutionService.start_workflow(tenant_b.id, draft.id, tenant_a_user, {}, "foreign")

    published = WorkflowDefinitionService.publish_workflow(
        tenant_a.id, draft.id, tenant_a_user, "publish-context"
    )
    # The published definition above allows an optional value; direct schema validation
    # is covered here without mutating its immutable definition.
    with pytest.raises(ValidationError):
        WorkflowExecutionService.start_workflow(
            tenant_a.id, published.id, tenant_a_user, {"approved": "yes"}, "bad-context"
        )


def test_approval_completion_rejection_and_timeout(tenant_a, tenant_a_user) -> None:
    approver = TenantUserFactory(organization=tenant_a, username="workflow-approver")
    workflow = publish(tenant_a.id, tenant_a_user, approval_payload(approver.pk))

    approved = WorkflowExecutionService.start_workflow(
        tenant_a.id, workflow.id, tenant_a_user, {}, "approval-complete"
    )
    run_job(approved)
    approved.refresh_from_db()
    task = WorkflowTask.objects.for_tenant(tenant_a.id).get(instance=approved)
    assert approved.state == "waiting"
    decided = WorkflowTaskService.complete_task(
        tenant_a.id, task.id, approver, {"comment": "Approved"}, "decision-complete"
    )
    assert decided.status == "completed"
    approved.refresh_from_db()
    assert approved.state == "completed"
    assert WorkflowTaskService.complete_task(
        tenant_a.id, task.id, approver, {"comment": "Approved"}, "decision-complete"
    ).status == "completed"

    rejected = WorkflowExecutionService.start_workflow(
        tenant_a.id, workflow.id, tenant_a_user, {}, "approval-reject"
    )
    run_job(rejected)
    rejected_task = WorkflowTask.objects.for_tenant(tenant_a.id).get(instance=rejected)
    WorkflowTaskService.reject_task(
        tenant_a.id, rejected_task.id, approver, "Outside policy", {}, "decision-reject"
    )
    rejected.refresh_from_db()
    assert rejected.state == "failed"
    assert rejected.failure_code == "TASK_REJECTED"

    timed = WorkflowExecutionService.start_workflow(
        tenant_a.id, workflow.id, tenant_a_user, {}, "approval-timeout"
    )
    run_job(timed)
    timed_task = WorkflowTask.objects.for_tenant(tenant_a.id).get(instance=timed)
    WorkflowTask.objects.for_tenant(tenant_a.id).filter(id=timed_task.id).update(
        due_date=timezone.now() - timedelta(seconds=1)
    )
    assert WorkflowTaskService.expire_due_tasks(tenant_a.id, timezone.now()) == 1
    timed.refresh_from_db()
    assert timed.state == "failed"


def test_decision_executes_true_and_false_branches(tenant_a, tenant_a_user) -> None:
    payload = action_payload(key="decision-path")
    payload["workflow_type"] = "conditional"
    terminal = lambda key, order: {
        "key": key,
        "name": key.title(),
        "step_type": "action",
        "order": order,
        "config": {
            "handler": "core.terminal_completion.v1",
            "schema_version": "1",
            "input_mapping": {},
            "configuration": {},
        },
        "is_terminal": True,
        "next_step_keys": [],
        "join_key": "",
    }
    payload["steps"] = [
        {
            "key": "choose",
            "name": "Choose",
            "step_type": "decision",
            "order": 1,
            "config": {
                "condition": {"handler": "core.truthy.v1", "value_path": "approved"},
                "true_step_key": "accepted",
                "false_step_key": "declined",
                "schema_version": "1",
            },
            "is_terminal": False,
            "next_step_keys": ["accepted", "declined"],
            "join_key": "",
        },
        terminal("accepted", 2),
        terminal("declined", 3),
    ]
    workflow = publish(tenant_a.id, tenant_a_user, payload)
    for choice, target in ((True, "accepted"), (False, "declined")):
        instance = WorkflowExecutionService.start_workflow(
            tenant_a.id, workflow.id, tenant_a_user, {"approved": choice}, f"branch-{choice}"
        )
        run_job(instance)
        instance.refresh_from_db()
        assert instance.state == "completed"
        assert target in instance.result_data["steps"]


def test_adapter_invocation_and_cancellation(tenant_a, tenant_a_user) -> None:
    from src.modules.automation_orchestration.workflow_adapter import WorkflowInvocation

    workflow = publish(tenant_a.id, tenant_a_user, approval_payload(tenant_a_user.pk))
    request = WorkflowInvocation(
        tenant_id=tenant_a.id,
        workflow_id=workflow.id,
        actor_id=tenant_a_user.pk,
        correlation_id=str(uuid.uuid4()),
        input={},
        idempotency_token="adapter-start",
    )
    adapter = SaraiseWorkflowExecutionAdapter()
    result = adapter.invoke(request)
    assert result.status == "accepted"
    assert adapter.cancel(tenant_a.id, result.instance_id, "adapter-cancel") is True
    assert WorkflowInstance.objects.for_tenant(tenant_a.id).get(id=result.instance_id).state == "cancelled"
