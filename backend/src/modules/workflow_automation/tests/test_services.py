"""Service-layer contracts for workflow definitions and executions."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from src.core.api import OperationFailed
from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import execute
from src.core.state_machine import StateMachineError
from src.core.testing.factories import TenantUserFactory

from ..models import Workflow, WorkflowInstance, WorkflowStep, WorkflowStepExecution, WorkflowTask
from ..services import (
    SaraiseWorkflowExecutionAdapter,
    WorkflowConfigurationService,
    WorkflowDefinitionService,
    WorkflowEngine,
    WorkflowExecutionService,
    WorkflowTaskService,
    _action_configuration,
    _actor_id,
    _apply_machine,
    _context_schema_errors,
    _descriptor_health,
    _handler_from_registry,
    _handler_key_for_step,
    _mapped_input,
    _notification_input,
    _safe_failure_message,
    _transition_key,
    _validate_tenant_json,
    default_configuration_document,
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

    published = WorkflowDefinitionService.publish_workflow(tenant_a.id, workflow.id, tenant_a_user, "publish-once")
    replay = WorkflowDefinitionService.publish_workflow(tenant_a.id, workflow.id, tenant_a_user, "publish-once")
    assert replay.status == published.status == "published"
    clone = WorkflowDefinitionService.clone_version(tenant_a.id, workflow.id, tenant_a_user)
    assert (clone.status, clone.version, clone.key) == ("draft", 2, workflow.key)
    archived = WorkflowDefinitionService.archive_workflow(tenant_a.id, workflow.id, tenant_a_user, "archive-v1")
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


def test_configuration_preview_update_history_and_rollback_are_versioned(tenant_a, tenant_a_user) -> None:
    service = WorkflowConfigurationService()
    current = service.get_configuration(tenant_a.id)
    document = default_configuration_document()
    document["limits"] = {**document["limits"], "catalog_default_limit": 10}

    preview = service.preview(tenant_a.id, document)
    assert preview == {
        "valid": True,
        "current_version": current.version,
        "changed_sections": ["limits"],
        "restart_required": False,
    }

    updated = service.update_configuration(
        tenant_a.id,
        tenant_a_user,
        document,
        expected_version=current.version,
        change_reason="tighten catalog default",
    )
    assert updated.version == current.version + 1
    assert service.value(tenant_a.id, "limits.catalog_default_limit") == 10
    assert service.history(tenant_a.id).filter(version=updated.version).exists()

    with pytest.raises(OperationFailed) as exc:
        service.update_configuration(
            tenant_a.id,
            tenant_a_user,
            document,
            expected_version=current.version,
            change_reason="stale save",
        )
    assert exc.value.error_code == "CONFIGURATION_VERSION_CONFLICT"

    rolled_back = service.rollback(
        tenant_a.id,
        tenant_a_user,
        1,
        expected_version=updated.version,
    )
    assert rolled_back.version == updated.version + 1
    assert rolled_back.document["limits"]["catalog_default_limit"] == 25


@pytest.mark.parametrize(
    ("section", "patch", "expected_key"),
    [
        ("limits", {"catalog_default_limit": 200, "catalog_max_limit": 100}, "limits.catalog_default_limit"),
        ("defaults", {"execution_priority": 99}, "defaults.execution_priority"),
        ("allowed_values", {"workflow_types": ["approval", "parallel"]}, "allowed_values.workflow_types"),
        (
            "feature_flags",
            {"parallel_workflows": {"enabled": True, "roles": [], "cohorts": []}},
            "feature_flags.parallel_workflows.enabled",
        ),
        ("ui", {"reject_reason_max_length": 2001}, "ui.reject_reason_max_length"),
    ],
)
def test_configuration_validation_rejects_unsafe_policy_combinations(section, patch, expected_key) -> None:
    document = default_configuration_document()
    document[section] = {**document[section], **patch}

    with pytest.raises(ValidationError) as exc:
        WorkflowConfigurationService.validate_document(document)
    assert expected_key in exc.value.detail


@pytest.mark.parametrize(
    ("mutate", "expected_key"),
    [
        (lambda document: document.pop("limits"), "document"),
        (lambda document: document.update({"limits": []}), "document"),
        (
            lambda document: document["limits"].update({"execution_priority_min": 8, "execution_priority_max": 3}),
            "limits.execution_priority_min",
        ),
        (
            lambda document: document["defaults"].update({"workflow_type": "parallel"}),
            "defaults.workflow_type",
        ),
        (
            lambda document: document["defaults"].update({"approval_due_seconds": 999999999}),
            "defaults.approval_due_seconds",
        ),
        (
            lambda document: document["defaults"].update({"workflow_version": 0}),
            "defaults.workflow_version",
        ),
        (
            lambda document: document["defaults"].update({"cancellation_reason": ""}),
            "defaults.cancellation_reason",
        ),
        (
            lambda document: document["step_handlers"].update({"action": "unsafe_code"}),
            "step_handlers",
        ),
        (
            lambda document: document["lifecycle"]["instance"].update({"running": ["deleted"]}),
            "lifecycle.instance.running",
        ),
        (
            lambda document: document["action_quota_costs"].update({"core.context_projection.v1": 101}),
            "action_quota_costs",
        ),
        (
            lambda document: document["operational"].update({"outbox_stale_seconds": 1}),
            "operational.outbox_stale_seconds",
        ),
        (
            lambda document: document["ui"].update({"sidebar_orders": {"workflows": 1}}),
            "ui.sidebar_orders",
        ),
        (
            lambda document: document["feature_flags"]["event_triggers"].update({"roles": ["ops", "ops"]}),
            "feature_flags.event_triggers.roles",
        ),
        (
            lambda document: document["feature_flags"]["timeout_notifications"].update({"enabled": True}),
            "feature_flags.timeout_notifications.enabled",
        ),
    ],
)
def test_configuration_validation_rejects_structural_drift_and_unsafe_dependencies(mutate, expected_key) -> None:
    document = default_configuration_document()
    mutate(document)

    with pytest.raises(ValidationError) as exc:
        WorkflowConfigurationService.validate_document(document)
    assert expected_key in exc.value.detail


def test_configuration_environment_and_value_paths_fail_closed(tenant_a) -> None:
    service = WorkflowConfigurationService()

    with pytest.raises(ValidationError) as exc:
        service.get_configuration(tenant_a.id, environment="qa")
    assert "environment" in exc.value.detail

    with pytest.raises(OperationFailed) as exc_info:
        service.value(tenant_a.id, "limits.missing")
    assert exc_info.value.error_code == "WORKFLOW_CONFIGURATION_INVALID"


def test_execution_helper_contracts_fail_closed_for_invalid_mapping_and_schema() -> None:
    assert _mapped_input({"name": "customer.name"}, {"customer": {"name": "Ada"}}) == {"name": "Ada"}

    with pytest.raises(OperationFailed) as missing_path:
        _mapped_input({"name": "customer.missing"}, {"customer": {}})
    assert missing_path.value.error_code == "CONTEXT_PATH_MISSING"

    with pytest.raises(OperationFailed) as invalid_mapping:
        _mapped_input({"name": ""}, {"customer": {"name": "Ada"}})
    assert invalid_mapping.value.error_code == "INPUT_MAPPING_INVALID"

    errors = _context_schema_errors(
        {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "score": {"type": "number"},
                "meta": [],
            },
            "additionalProperties": False,
        },
        {"age": True, "score": False, "extra": "blocked", "meta": "ignored"},
    )
    assert {
        "context.name is required",
        "context.age must be an integer",
        "context.score must be a number",
        "context.extra is not allowed",
        "required_context_schema.properties.meta must be an object",
    }.issubset(set(errors))

    assert _action_configuration("action", {"handler": "core.context_projection.v1", "input_mapping": {"x": "y"}}) == {
        "input_mapping": {"x": "y"}
    }
    assert _action_configuration("notification", {"channel": "email", "template_key": "approval"}) == {
        "template_key": "approval"
    }
    assert _action_configuration("notification", {"channel": "in_app"}) == {"notification_type": "workflow"}


def test_notification_input_renders_templates_and_fails_closed(settings, tenant_a, tenant_a_user) -> None:
    workflow = Workflow.objects.for_tenant(tenant_a.id).create(
        tenant_id=tenant_a.id,
        key="notify-helper",
        version=1,
        name="Notification helper",
        workflow_type="sequential",
        trigger_type="manual",
        trigger_config={},
        status="draft",
        required_context_schema={},
        created_by=tenant_a_user,
    )
    email_step = WorkflowStep.objects.for_tenant(tenant_a.id).create(
        tenant_id=tenant_a.id,
        workflow=workflow,
        key="email",
        name="Email",
        step_type="notification",
        order=1,
        config={
            "channel": "email",
            "recipient_mapping": {"recipient_email": "customer.email"},
            "template_key": "approval",
        },
        is_terminal=False,
    )
    in_app_step = WorkflowStep.objects.for_tenant(tenant_a.id).create(
        tenant_id=tenant_a.id,
        workflow=workflow,
        key="in-app",
        name="In app",
        step_type="notification",
        order=2,
        config={
            "channel": "in_app",
            "recipient_mapping": {"recipient_id": "recipient.id"},
            "template_key": "task-created",
        },
        is_terminal=True,
    )
    instance = WorkflowInstance.objects.for_tenant(tenant_a.id).create(
        tenant_id=tenant_a.id,
        workflow=workflow,
        workflow_version=1,
        current_step=email_step,
        state="running",
        context_data={"customer": {"email": "ada@example.com"}, "recipient": {"id": tenant_a_user.pk}, "name": "Ada"},
        result_data={},
        priority=5,
        idempotency_key="notify-helper",
        correlation_id="corr-notify",
        started_by=tenant_a_user,
    )

    email_input = _notification_input(instance, email_step)
    assert email_input["recipient_email"] == "ada@example.com"
    assert email_input["template_context"]["name"] == "Ada"

    settings.WORKFLOW_NOTIFICATION_TEMPLATES = {
        "task-created": {"title": "Task for {name}", "message": "Review {name}"}
    }
    assert _notification_input(instance, in_app_step) == {
        "recipient_id": str(tenant_a_user.pk),
        "title": "Task for Ada",
        "message": "Review Ada",
    }

    instance.context_data = {"customer": {"email": ""}, "recipient": {"id": tenant_a_user.pk}, "name": "Ada"}
    with pytest.raises(OperationFailed) as missing_email:
        _notification_input(instance, email_step)
    assert missing_email.value.error_code == "NOTIFICATION_RECIPIENT_MISSING"

    settings.WORKFLOW_NOTIFICATION_TEMPLATES = {}
    instance.context_data = {"recipient": {"id": tenant_a_user.pk}, "name": "Ada"}
    with pytest.raises(OperationFailed) as missing_template:
        _notification_input(instance, in_app_step)
    assert missing_template.value.error_code == "CAPABILITY_UNAVAILABLE"

    settings.WORKFLOW_NOTIFICATION_TEMPLATES = {"task-created": {"title": "Task for {missing}", "message": "Review"}}
    with pytest.raises(OperationFailed) as render_error:
        _notification_input(instance, in_app_step)
    assert render_error.value.error_code == "NOTIFICATION_TEMPLATE_FAILED"


def test_public_projection_exposes_only_declared_context_and_step_outputs(tenant_a, tenant_a_user) -> None:
    workflow = Workflow.objects.for_tenant(tenant_a.id).create(
        tenant_id=tenant_a.id,
        key="projection-helper",
        version=1,
        name="Projection helper",
        workflow_type="sequential",
        trigger_type="manual",
        trigger_config={},
        status="draft",
        required_context_schema={
            "type": "object",
            "properties": {
                "public": {"type": "string", "x-public": True},
                "private": {"type": "string"},
            },
        },
        created_by=tenant_a_user,
    )
    step = WorkflowStep.objects.for_tenant(tenant_a.id).create(
        tenant_id=tenant_a.id,
        workflow=workflow,
        key="project",
        name="Project",
        step_type="action",
        order=1,
        config={"public_output_keys": ["visible", "missing", 42]},
        is_terminal=True,
    )
    instance = WorkflowInstance.objects.for_tenant(tenant_a.id).create(
        tenant_id=tenant_a.id,
        workflow=workflow,
        workflow_version=1,
        current_step=None,
        state="completed",
        context_data={"public": "shown", "private": "hidden"},
        result_data={
            "steps": {
                step.key: {
                    "status": "succeeded",
                    "output": {"visible": "ok", "secret": "hidden"},  # pragma: allowlist secret
                },
                "unknown": {"status": "succeeded", "output": {"visible": "blocked"}},
                "bad": "ignored",
            }
        },
        priority=5,
        idempotency_key="projection-helper",
        correlation_id="corr-projection",
        started_by=tenant_a_user,
        completed_at=timezone.now(),
    )

    public_context, public_result = WorkflowExecutionService.public_projection(instance)

    assert public_context == {"public": "shown"}
    assert public_result == {"steps": {"project": {"status": "succeeded", "output": {"visible": "ok"}}}}


def test_descriptor_health_normalizes_exceptions_objects_and_mappings() -> None:
    class RaisingHandler:
        def health(self):
            raise RuntimeError("down")

    class BoolHandler:
        def __init__(self, healthy):
            self._healthy = healthy

        def health(self):
            return type("Health", (), {"healthy": self._healthy})()

    class MappingHandler:
        def health(self):
            return {"status": "ok"}

    assert _descriptor_health(RaisingHandler()) == (False, "degraded")
    assert _descriptor_health(BoolHandler(True)) == (True, "healthy")
    assert _descriptor_health(BoolHandler(False)) == (False, "degraded")
    assert _descriptor_health(MappingHandler()) == (True, "ok")


def test_definition_validation_reports_graph_and_handler_failures(tenant_a) -> None:
    invalid = action_payload(key="invalid-graph")
    invalid["steps"] = [
        {
            "key": "choose",
            "name": "Choose",
            "step_type": "decision",
            "order": 1,
            "config": {
                "condition": {"handler": "missing.condition.v1"},
                "true_step_key": "missing",
                "false_step_key": "choose",
                "schema_version": "1",
            },
            "is_terminal": False,
            "next_step_keys": ["missing"],
            "join_key": "",
        },
        {
            "key": "orphan",
            "name": "Orphan",
            "step_type": "action",
            "order": 2,
            "config": {
                "handler": "missing.action.v1",
                "schema_version": "1",
                "input_mapping": {},
                "configuration": {},
            },
            "is_terminal": True,
            "next_step_keys": [],
            "join_key": "",
        },
    ]

    result = WorkflowDefinitionService.validate_definition(tenant_a.id, invalid)
    assert result.valid is False
    assert {
        "CONDITION_UNAVAILABLE",
        "HANDLER_UNAVAILABLE",
        "STEP_REFERENCE_UNKNOWN",
    }.issubset({issue.code for issue in result.issues})


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

    published = WorkflowDefinitionService.publish_workflow(tenant_a.id, draft.id, tenant_a_user, "publish-context")
    # The published definition above allows an optional value; direct schema validation
    # is covered here without mutating its immutable definition.
    with pytest.raises(ValidationError):
        WorkflowExecutionService.start_workflow(
            tenant_a.id, published.id, tenant_a_user, {"approved": "yes"}, "bad-context"
        )


def test_approval_completion_rejection_and_timeout(tenant_a, tenant_a_user) -> None:
    approver = TenantUserFactory(organization=tenant_a, username="workflow-approver")
    workflow = publish(tenant_a.id, tenant_a_user, approval_payload(approver.pk))

    approved = WorkflowExecutionService.start_workflow(tenant_a.id, workflow.id, tenant_a_user, {}, "approval-complete")
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
    assert (
        WorkflowTaskService.complete_task(
            tenant_a.id, task.id, approver, {"comment": "Approved"}, "decision-complete"
        ).status
        == "completed"
    )

    rejected = WorkflowExecutionService.start_workflow(tenant_a.id, workflow.id, tenant_a_user, {}, "approval-reject")
    run_job(rejected)
    rejected_task = WorkflowTask.objects.for_tenant(tenant_a.id).get(instance=rejected)
    WorkflowTaskService.reject_task(tenant_a.id, rejected_task.id, approver, "Outside policy", {}, "decision-reject")
    rejected.refresh_from_db()
    assert rejected.state == "failed"
    assert rejected.failure_code == "TASK_REJECTED"

    timed = WorkflowExecutionService.start_workflow(tenant_a.id, workflow.id, tenant_a_user, {}, "approval-timeout")
    run_job(timed)
    timed_task = WorkflowTask.objects.for_tenant(tenant_a.id).get(instance=timed)
    WorkflowTask.objects.for_tenant(tenant_a.id).filter(id=timed_task.id).update(
        due_date=timezone.now() - timedelta(seconds=1)
    )
    assert WorkflowTaskService.expire_due_tasks(tenant_a.id, timezone.now()) == 1
    timed.refresh_from_db()
    assert timed.state == "failed"


def test_rejected_approval_can_route_to_configured_recovery_step(tenant_a, tenant_a_user) -> None:
    approver = TenantUserFactory(organization=tenant_a, username="workflow-goto-approver")
    payload = approval_payload(approver.pk)
    payload["key"] = "approval-goto"
    payload["steps"][0]["config"] = {
        **payload["steps"][0]["config"],
        "rejection_behavior": "goto",
        "reject_step_key": "fallback",
    }
    payload["steps"][0]["is_terminal"] = False
    payload["steps"][0]["next_step_keys"] = ["fallback"]
    payload["steps"].append(
        {
            "key": "fallback",
            "name": "Fallback",
            "step_type": "action",
            "order": 2,
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
    )
    workflow = publish(tenant_a.id, tenant_a_user, payload)
    instance = WorkflowExecutionService.start_workflow(tenant_a.id, workflow.id, tenant_a_user, {}, "approval-goto")
    run_job(instance)
    task = WorkflowTask.objects.for_tenant(tenant_a.id).get(instance=instance)

    WorkflowTaskService.reject_task(tenant_a.id, task.id, approver, "needs fallback", {}, "reject-goto")

    instance.refresh_from_db()
    assert instance.state == "running"
    assert instance.current_step.key == "fallback"
    assert AsyncJob.objects.for_tenant(tenant_a.id).filter(id=instance.async_job_id).exists()
    run_job(instance)
    instance.refresh_from_db()
    assert instance.state == "completed"


def test_cancel_open_tasks_records_reason_and_skips_non_pending_tasks(tenant_a, tenant_a_user) -> None:
    approver = TenantUserFactory(organization=tenant_a, username="workflow-cancel-open")
    workflow = publish(tenant_a.id, tenant_a_user, approval_payload(approver.pk))
    instance = WorkflowExecutionService.start_workflow(tenant_a.id, workflow.id, tenant_a_user, {}, "cancel-open")
    run_job(instance)
    task = WorkflowTask.objects.for_tenant(tenant_a.id).get(instance=instance)

    cancelled = WorkflowTaskService.cancel_open_tasks(tenant_a.id, instance.id, tenant_a_user, "operator cancelled")
    second_pass = WorkflowTaskService.cancel_open_tasks(tenant_a.id, instance.id, tenant_a_user, "ignored")

    task.refresh_from_db()
    assert cancelled == 1
    assert second_pass == 0
    assert task.status == "cancelled"
    assert task.meta_data["cancellation_reason"] == "operator cancelled"


def test_decision_executes_true_and_false_branches(tenant_a, tenant_a_user) -> None:
    payload = action_payload(key="decision-path")
    payload["workflow_type"] = "conditional"

    def terminal(key, order):
        return {
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


def test_adapter_handles_unavailable_actor_and_handler_registration(monkeypatch, tenant_a) -> None:
    from src.modules.automation_orchestration.workflow_adapter import WorkflowInvocation

    adapter = SaraiseWorkflowExecutionAdapter()
    unavailable = adapter.invoke(
        WorkflowInvocation(
            tenant_id=tenant_a.id,
            workflow_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            correlation_id=str(uuid.uuid4()),
            input={},
            idempotency_token="missing-actor",
        )
    )
    assert unavailable.status == "unavailable"
    assert unavailable.error_code == "ACTOR_UNAVAILABLE"

    monkeypatch.setattr("src.core.async_jobs.services.get_handler", lambda command: object())
    assert adapter.available() is True

    def missing_handler(command):
        del command
        raise LookupError("not registered")

    monkeypatch.setattr("src.core.async_jobs.services.get_handler", missing_handler)
    assert adapter.available() is False


def test_compatibility_engine_requires_actor_and_known_actions() -> None:
    engine = WorkflowEngine()
    with pytest.raises(PermissionDenied):
        engine.transition_task(uuid.uuid4(), uuid.uuid4(), "complete", {})
    with pytest.raises(ValidationError):
        engine.transition_task(uuid.uuid4(), uuid.uuid4(), "delegate", {}, actor=object())


def test_task_decisions_fail_closed_for_wrong_assignee_and_terminal_replay(tenant_a, tenant_a_user) -> None:
    approver = TenantUserFactory(organization=tenant_a, username="workflow-terminal-approver")
    other_user = TenantUserFactory(organization=tenant_a, username="workflow-terminal-other")
    workflow = publish(tenant_a.id, tenant_a_user, approval_payload(approver.pk))
    instance = WorkflowExecutionService.start_workflow(tenant_a.id, workflow.id, tenant_a_user, {}, "task-guard")
    run_job(instance)
    task = WorkflowTask.objects.for_tenant(tenant_a.id).get(instance=instance)

    with pytest.raises(PermissionDenied):
        WorkflowTaskService.complete_task(tenant_a.id, task.id, other_user, {}, "wrong-user")

    WorkflowTaskService.complete_task(tenant_a.id, task.id, approver, {}, "approve-once")
    with pytest.raises(OperationFailed) as exc:
        WorkflowTaskService.reject_task(tenant_a.id, task.id, approver, "too late", {}, "reject-terminal")
    assert exc.value.error_code == "ILLEGAL_TRANSITION"
    assert exc.value.public_message == "The requested lifecycle transition is no longer legal."


def test_task_listing_all_scope_requires_management_permission(tenant_a, tenant_a_user) -> None:
    with pytest.raises(PermissionDenied):
        WorkflowTaskService.list_tasks(tenant_a.id, tenant_a_user, {"scope": "all"}).count()


def test_service_helper_validation_and_registry_fail_closed(tenant_a, tenant_a_user) -> None:
    with pytest.raises(ValidationError) as invalid_key:
        _transition_key(tenant_a.id, "")
    assert "transition_key" in invalid_key.value.detail

    too_long = "x" * (WorkflowConfigurationService.value(tenant_a.id, "limits.transition_key_max_length") + 1)
    with pytest.raises(ValidationError) as long_key:
        _transition_key(tenant_a.id, too_long)
    assert "transition_key" in long_key.value.detail

    with pytest.raises(PermissionDenied):
        _actor_id(object())

    with pytest.raises(ValidationError) as invalid_json:
        _validate_tenant_json(tenant_a.id, {"too": {"deep": [{"value": "x" * 40000}]}}, path="context")
    assert "context" in str(invalid_json.value.detail)

    message = _safe_failure_message(tenant_a.id, "token=secret-value " + ("x" * 3000))
    assert "secret-value" not in message
    assert len(message) <= WorkflowConfigurationService.value(tenant_a.id, "limits.failure_message_max_length")

    class MissingRegistry:
        def get(self, key, schema_version=None):
            del key, schema_version
            raise KeyError("missing")

    with pytest.raises(Exception) as missing:
        _handler_from_registry(MissingRegistry(), "missing.action", schema_version="1")
    assert getattr(missing.value, "capability", "") == "missing.action"

    class LegacyRegistry:
        def get(self, key):
            return {"key": key}

    assert _handler_from_registry(LegacyRegistry(), "legacy.action", schema_version="1") == {"key": "legacy.action"}


def test_apply_machine_respects_disabled_transitions_and_normalizes_engine_errors(tenant_a, tenant_a_user) -> None:
    workflow = WorkflowDefinitionService.create_workflow(
        tenant_a.id, tenant_a_user, action_payload(key="machine-guard")
    )
    document = default_configuration_document()
    document["lifecycle"]["definition"]["draft"] = ["draft"]
    current = WorkflowConfigurationService.get_configuration(tenant_a.id)
    WorkflowConfigurationService.update_configuration(
        tenant_a.id,
        tenant_a_user,
        document,
        expected_version=current.version,
        change_reason="disable definition publish",
    )

    with pytest.raises(OperationFailed) as disabled:
        WorkflowDefinitionService.publish_workflow(tenant_a.id, workflow.id, tenant_a_user, "disabled-publish")
    assert disabled.value.error_code == "TRANSITION_DISABLED"

    class UnknownMachine:
        state_field = "status"
        transitions = ()

    with pytest.raises(OperationFailed) as unconfigured:
        _apply_machine(UnknownMachine(), workflow, "noop", transition_key="noop", tenant_id=tenant_a.id)
    assert unconfigured.value.error_code == "STATE_MACHINE_UNCONFIGURED"

    class FailingMachine:
        state_field = "status"
        transitions = ()

        @staticmethod
        def apply(*_args, **_kwargs):
            raise StateMachineError("storage failed")

    without_tenant = type("Aggregate", (), {"status": "draft", "transition_history": []})()
    with pytest.raises(OperationFailed) as failed:
        _apply_machine(FailingMachine(), without_tenant, "publish", transition_key="fail")
    assert failed.value.error_code == "STATE_TRANSITION_FAILED"


def test_handler_key_for_notification_requires_governed_configuration(tenant_a, tenant_a_user) -> None:
    workflow = Workflow.objects.for_tenant(tenant_a.id).create(
        tenant_id=tenant_a.id,
        key="handler-key",
        version=1,
        name="Handler key",
        workflow_type="sequential",
        trigger_type="manual",
        trigger_config={},
        status="draft",
        required_context_schema={},
        created_by=tenant_a_user,
    )
    action_step = WorkflowStep.objects.for_tenant(tenant_a.id).create(
        tenant_id=tenant_a.id,
        workflow=workflow,
        key="action",
        name="Action",
        step_type="action",
        order=1,
        config={"handler": "core.context_projection.v1", "schema_version": "2"},
    )
    notification_step = WorkflowStep.objects.for_tenant(tenant_a.id).create(
        tenant_id=tenant_a.id,
        workflow=workflow,
        key="notify",
        name="Notify",
        step_type="notification",
        order=2,
        config={"channel": "email"},
    )
    approval_step = WorkflowStep.objects.for_tenant(tenant_a.id).create(
        tenant_id=tenant_a.id,
        workflow=workflow,
        key="approval",
        name="Approval",
        step_type="approval",
        order=3,
        config={"assignment_kind": "user", "assignee_id": str(tenant_a_user.pk), "rejection_behavior": "fail"},
    )

    assert _handler_key_for_step(tenant_a.id, action_step) == ("core.context_projection.v1", "2")
    assert _handler_key_for_step(tenant_a.id, notification_step) == ("core.email_notification.v1", "1")
    with pytest.raises(ValueError, match="Only action and notification"):
        _handler_key_for_step(tenant_a.id, approval_step)

    document = default_configuration_document()
    document["notification_handlers"]["email"] = "unsafe-handler"
    current = WorkflowConfigurationService.get_configuration(tenant_a.id)
    WorkflowAutomationConfiguration = current.__class__
    WorkflowAutomationConfiguration.objects.for_tenant(tenant_a.id).filter(id=current.id).update(document=document)

    with pytest.raises(Exception) as unavailable:
        _handler_key_for_step(tenant_a.id, notification_step)
    assert getattr(unavailable.value, "capability", "") == "notification:email"


def test_configuration_service_rejects_non_object_sections_and_missing_history(tenant_a, tenant_a_user) -> None:
    service = WorkflowConfigurationService()
    with pytest.raises(ValidationError) as not_object:
        service.validate_document([])
    assert "document" in not_object.value.detail

    document = default_configuration_document()
    document["defaults"] = []
    with pytest.raises(ValidationError) as bad_sections:
        service.validate_document(document)
    assert "document" in bad_sections.value.detail

    with pytest.raises(NotFound):
        service.get_configuration(tenant_a.id, create=False)

    current = service.get_configuration(tenant_a.id)
    unchanged = service.update_configuration(
        tenant_a.id,
        tenant_a_user,
        current.document,
        expected_version=current.version,
        change_reason="no-op",
    )
    assert unchanged.version == current.version
    assert service.history(tenant_a.id).count() == 1

    with pytest.raises(ValidationError) as blank_reason:
        service.update_configuration(
            tenant_a.id,
            tenant_a_user,
            current.document,
            expected_version=current.version,
            change_reason=" ",
        )
    assert "change_reason" in blank_reason.value.detail

    with pytest.raises(NotFound):
        service.rollback(tenant_a.id, tenant_a_user, 99, expected_version=current.version)


def test_definition_validation_reports_trigger_schema_cycles_unreachable_and_degraded_handler(
    tenant_a, monkeypatch
) -> None:
    document = default_configuration_document()
    document["trigger_schemas"]["manual"] = {"required": ["source"], "allowed": ["source"]}
    current = WorkflowConfigurationService.get_configuration(tenant_a.id)
    current.document = document
    current.save(update_fields=("document", "updated_at"))

    trigger_invalid = action_payload(key="trigger-invalid")
    trigger_invalid["trigger_config"] = {}
    trigger_result = WorkflowDefinitionService.validate_definition(tenant_a.id, trigger_invalid)
    assert [issue.code for issue in trigger_result.issues] == ["TRIGGER_CONFIG_INVALID"]

    document["trigger_schemas"]["manual"] = {"required": [], "allowed": []}
    current.document = document
    current.save(update_fields=("document", "updated_at"))

    cyclic = action_payload(key="cycle")
    cyclic["steps"] = [
        {
            "key": "loop",
            "name": "Loop",
            "step_type": "action",
            "order": 1,
            "config": {
                "handler": "core.terminal_completion.v1",
                "schema_version": "1",
                "input_mapping": {},
                "configuration": {},
            },
            "is_terminal": False,
            "next_step_keys": ["loop"],
            "join_key": "",
        },
        {
            "key": "unreachable",
            "name": "Unreachable",
            "step_type": "action",
            "order": 2,
            "config": {
                "handler": "core.terminal_completion.v1",
                "schema_version": "1",
                "input_mapping": {},
                "configuration": {},
            },
            "is_terminal": True,
            "next_step_keys": [],
            "join_key": "",
        },
    ]

    class DegradedHandler:
        descriptor = type(
            "Descriptor",
            (),
            {"contract_version": "1", "contract_fingerprint": "fingerprint"},
        )()

        @staticmethod
        def validate_config(config):
            del config

        @staticmethod
        def health():
            return {"status": "degraded"}

    monkeypatch.setattr(
        "src.modules.workflow_automation.services._handler_from_registry", lambda *args, **kwargs: DegradedHandler()
    )
    result = WorkflowDefinitionService.validate_definition(tenant_a.id, cyclic)

    assert {"WORKFLOW_CYCLE", "STEP_UNREACHABLE"}.issubset({issue.code for issue in result.issues})
    assert [warning.code for warning in result.warnings] == ["HANDLER_DEGRADED"] * len(cyclic["steps"])


def test_notification_input_rejects_incomplete_in_app_payload(settings, tenant_a, tenant_a_user) -> None:
    workflow = Workflow.objects.for_tenant(tenant_a.id).create(
        tenant_id=tenant_a.id,
        key="notify-incomplete",
        version=1,
        name="Notify incomplete",
        workflow_type="sequential",
        trigger_type="manual",
        trigger_config={},
        status="draft",
        required_context_schema={},
        created_by=tenant_a_user,
    )
    step = WorkflowStep.objects.for_tenant(tenant_a.id).create(
        tenant_id=tenant_a.id,
        workflow=workflow,
        key="in-app",
        name="In app",
        step_type="notification",
        order=1,
        config={
            "channel": "in_app",
            "recipient_mapping": {"recipient_id": "recipient.id"},
            "template_key": "task-created",
        },
        is_terminal=True,
    )
    instance = WorkflowInstance.objects.for_tenant(tenant_a.id).create(
        tenant_id=tenant_a.id,
        workflow=workflow,
        workflow_version=1,
        current_step=step,
        state="running",
        context_data={"recipient": {"id": ""}},
        result_data={},
        priority=5,
        idempotency_key="notify-incomplete",
        correlation_id="corr-notify-incomplete",
        started_by=tenant_a_user,
    )
    settings.WORKFLOW_NOTIFICATION_TEMPLATES = {"task-created": {"title": "Task", "message": "Review"}}

    with pytest.raises(OperationFailed) as incomplete:
        _notification_input(instance, step)

    assert incomplete.value.error_code == "NOTIFICATION_INPUT_INVALID"
