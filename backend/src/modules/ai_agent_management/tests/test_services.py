"""Tenant-first command-service tests.

These tests assert durable side effects and state, never only return values.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import connection
from django.http import QueryDict
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from src.core.access.entitlements import Quota
from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.state_machine import IdempotencyConflictError, IllegalTransitionError, TerminalStateError
from src.modules.ai_agent_management import services as service_module
from src.modules.ai_agent_management.egress_models import EgressRequest, EgressRule, SecretAccess
from src.modules.ai_agent_management.models import Agent, AgentExecution
from src.modules.ai_agent_management.registries import runner_registry
from src.modules.ai_agent_management.services import (
    DEFAULT_CONFIGURATION,
    AgentService,
    AgentServiceError,
    ApprovalService,
    AuditService,
    ConfigurationService,
    EgressService,
    ExecutionService,
    KillSwitchService,
    ScheduleService,
    SecretService,
    SoDService,
    ToolService,
    UsageService,
)
from src.modules.ai_agent_management.tool_models import ToolInvocation


@pytest.mark.django_db
def test_agent_create_owns_tenant_and_creator_fields(tenant_id, other_tenant_id, actor_id):
    agent = AgentService.create_agent(
        tenant_id,
        actor_id,
        {
            "tenant_id": other_tenant_id,
            "created_by": uuid4(),
            "status": "active",
            "name": "Owned aggregate",
            "identity_type": "system_bound",
            "subject_id": uuid4(),
            "runner_key": "test.runner",
            "config": {},
        },
    )
    assert agent.tenant_id == tenant_id
    assert agent.created_by == actor_id
    assert agent.status == "draft"


@pytest.mark.django_db
def test_agent_update_rolls_back_server_controlled_changes(agent, actor_id, other_tenant_id):
    original_name = agent.name
    with pytest.raises(ValidationError):
        AgentService.update_agent(
            agent.tenant_id,
            actor_id,
            agent.id,
            {"name": "must rollback", "tenant_id": other_tenant_id},
        )
    agent.refresh_from_db()
    assert agent.name == original_name
    assert agent.tenant_id != other_tenant_id


@pytest.mark.django_db
def test_agent_create_rejects_identity_session_policy_violations(tenant_id, actor_id):
    base = {
        "name": "Identity policy agent",
        "subject_id": uuid4(),
        "runner_key": "test.runner",
        "config": {},
    }
    with pytest.raises(ValidationError, match="session"):
        AgentService.create_agent(tenant_id, actor_id, {**base, "identity_type": "user_bound"})
    with pytest.raises(ValidationError, match="session"):
        AgentService.create_agent(
            tenant_id,
            actor_id,
            {**base, "identity_type": "system_bound", "session_id": uuid4()},
        )
    with pytest.raises(ValidationError, match="runner"):
        AgentService.create_agent(
            tenant_id,
            actor_id,
            {**base, "identity_type": "system_bound", "runner_key": "   "},
        )


def test_database_session_validator_fails_closed_on_missing_or_corrupt_session(monkeypatch, tenant_id, actor_id):
    class QuerySetStub:
        def __init__(self, session):
            self.session = session

        def first(self):
            return self.session

    class ManagerStub:
        def __init__(self, session):
            self.session = session

        def filter(self, **_kwargs):
            return QuerySetStub(self.session)

    class CorruptSession:
        def get_decoded(self):
            raise ValueError("corrupt session")

    validator = service_module.DatabaseSessionValidator()
    monkeypatch.setattr(service_module.Session, "objects", ManagerStub(None))
    assert validator.is_active(tenant_id, actor_id, uuid4()) is False

    monkeypatch.setattr(service_module.Session, "objects", ManagerStub(CorruptSession()))
    assert validator.is_active(tenant_id, actor_id, uuid4()) is False

    replacement = Mock()
    service_module.configure_session_validator(replacement)
    assert service_module.session_validator is replacement


@pytest.mark.django_db
def test_agent_list_is_tenant_scoped_and_filterable(agent, other_tenant_id, actor_id):
    Agent.objects.create(
        tenant_id=other_tenant_id,
        name="Invisible agent",
        identity_type="system_bound",
        subject_id=uuid4(),
        runner_key="test.runner",
        created_by=actor_id,
    )
    assert list(AgentService.list_agents(agent.tenant_id, {"search": "Governed"})) == [agent]
    assert not AgentService.list_agents(agent.tenant_id, {"status": "active"}).exists()
    with pytest.raises(ValidationError):
        AgentService.list_agents(agent.tenant_id, {"ordering": "tenant_id"}).exists()


@pytest.mark.django_db
def test_agent_lifecycle_is_guarded_and_idempotent(agent, actor_id, registered_runner):
    active = AgentService.activate_agent(agent.tenant_id, actor_id, agent.id, "agent:activate:1")
    assert active.status == "active"
    assert active.transition_history[-1]["transition_key"] == "agent:activate:1"
    assert AgentService.activate_agent(agent.tenant_id, actor_id, agent.id, "agent:activate:1").status == "active"

    disabled = AgentService.disable_agent(agent.tenant_id, actor_id, agent.id, "maintenance", "agent:disable:1")
    assert disabled.status == "disabled"
    retired = AgentService.retire_agent(agent.tenant_id, actor_id, agent.id, "obsolete", "agent:retire:1")
    assert retired.status == "retired"
    assert retired.deleted_at is not None
    with pytest.raises((IllegalTransitionError, AgentServiceError)):
        AgentService.activate_agent(agent.tenant_id, actor_id, agent.id, "agent:activate:after-retire")


@pytest.mark.django_db
def test_get_agent_reports_exact_invalid_uuid_fields(agent) -> None:
    with pytest.raises(ValidationError) as invalid_tenant:
        AgentService.get_agent("not-a-uuid", agent.id)  # type: ignore[arg-type]
    assert invalid_tenant.value.message_dict == {"tenant_id": ["Must be a valid UUID."]}

    with pytest.raises(ValidationError) as invalid_agent:
        AgentService.get_agent(agent.tenant_id, "not-a-uuid")  # type: ignore[arg-type]
    assert invalid_agent.value.message_dict == {"agent_id": ["Must be a valid UUID."]}


@pytest.mark.django_db
def test_get_execution_reports_exact_invalid_uuid_fields(execution) -> None:
    with pytest.raises(ValidationError) as invalid_tenant:
        ExecutionService.get_execution("not-a-uuid", execution.id)  # type: ignore[arg-type]
    assert invalid_tenant.value.message_dict == {"tenant_id": ["Must be a valid UUID."]}

    with pytest.raises(ValidationError) as invalid_execution:
        ExecutionService.get_execution(execution.tenant_id, "not-a-uuid")  # type: ignore[arg-type]
    assert invalid_execution.value.message_dict == {"execution_id": ["Must be a valid UUID."]}


@pytest.mark.django_db
def test_owned_execution_reports_exact_invalid_uuid_fields(execution) -> None:
    with pytest.raises(ValidationError) as invalid_tenant:
        ExecutionService._owned("not-a-uuid", execution.agent_id, execution.id)  # type: ignore[arg-type]
    assert invalid_tenant.value.message_dict == {"tenant_id": ["Must be a valid UUID."]}

    with pytest.raises(ValidationError) as invalid_agent:
        ExecutionService._owned(execution.tenant_id, "not-a-uuid", execution.id)  # type: ignore[arg-type]
    assert invalid_agent.value.message_dict == {"agent_id": ["Must be a valid UUID."]}

    with pytest.raises(ValidationError) as invalid_execution:
        ExecutionService._owned(execution.tenant_id, execution.agent_id, "not-a-uuid")  # type: ignore[arg-type]
    assert invalid_execution.value.message_dict == {"execution_id": ["Must be a valid UUID."]}


@pytest.mark.django_db
def test_agent_activation_fails_explicitly_when_runner_is_missing(agent, actor_id):
    runner_registry.unregister(agent.runner_key)
    with pytest.raises(AgentServiceError) as caught:
        AgentService.activate_agent(agent.tenant_id, actor_id, agent.id, "agent:activate")
    assert caught.value.code == "RUNNER_UNAVAILABLE"
    agent.refresh_from_db()
    assert agent.status == "draft"


@pytest.mark.django_db
def test_execution_acceptance_is_durable_and_idempotent(active_agent, actor_id, registered_runner):
    result = ExecutionService.execute(
        active_agent.tenant_id,
        actor_id,
        active_agent.id,
        {"task": "safe opaque input"},
        "execute:one",
    )
    execution = result.unwrap()
    assert execution.state == "queued"
    job = AsyncJob.objects.get(id=execution.async_job_id, tenant_id=active_agent.tenant_id)
    assert job.command == "ai_agent_management.execute"
    outbox = OutboxEvent.objects.get(aggregate_id=job.id, tenant_id=active_agent.tenant_id)
    assert outbox.status == "pending"
    assert outbox.payload["job_id"] == str(job.id)

    duplicate = ExecutionService.execute(
        active_agent.tenant_id,
        actor_id,
        active_agent.id,
        {"task": "different replay payload"},
        "execute:one",
    )
    assert duplicate.unwrap().id == execution.id
    assert AgentExecution.objects.filter(tenant_id=active_agent.tenant_id, idempotency_key="execute:one").count() == 1
    assert OutboxEvent.objects.filter(tenant_id=active_agent.tenant_id, aggregate_id=job.id).count() == 1


@pytest.mark.django_db
def test_execution_with_schedule_uses_schedule_branch(active_agent, actor_id, registered_runner):
    due = timezone.now() + timedelta(minutes=30)
    result = ExecutionService.execute(
        active_agent.tenant_id,
        actor_id,
        active_agent.id,
        {"task": "scheduled"},
        "execute:scheduled",
        schedule_at=due,
    )
    execution = result.unwrap()
    assert execution.state == "created"
    assert execution.async_job_id is not None
    assert result.evidence["schedule_id"]
    assert AsyncJob.objects.filter(id=execution.async_job_id, tenant_id=active_agent.tenant_id).exists()


@pytest.mark.django_db
def test_execution_schedule_branch_fails_closed_when_execution_is_missing(
    active_agent, actor_id, registered_runner, monkeypatch
) -> None:
    due = timezone.now() + timedelta(minutes=30)

    class MissingExecutionSchedule:
        execution = None

    monkeypatch.setattr(ScheduleService, "create_schedule", Mock(return_value=MissingExecutionSchedule()))

    with pytest.raises(AgentServiceError) as caught:
        ExecutionService.execute(
            active_agent.tenant_id,
            actor_id,
            active_agent.id,
            {"task": "scheduled"},
            "execute:missing-schedule-execution",
            schedule_at=due,
        )
    assert caught.value.code == "SCHEDULE_EXECUTION_MISSING"
    assert str(caught.value) == "Scheduled execution was not persisted."


@pytest.mark.django_db
def test_execute_inactive_killed_and_unavailable_paths_have_no_durable_job(agent, actor_id):
    inactive = ExecutionService.execute(agent.tenant_id, actor_id, agent.id, {}, "inactive")
    assert inactive.status == "failed"
    assert inactive.error_code == "AGENT_NOT_ACTIVE"
    assert not AsyncJob.objects.filter(tenant_id=agent.tenant_id).exists()


@pytest.mark.django_db
def test_stale_user_session_denies_execution_without_side_effects(
    tenant_id,
    actor_id,
    registered_runner,
    monkeypatch,
):
    class RevokedSession:
        def is_active(self, tenant_id, subject_id, session_id):
            return False

    monkeypatch.setattr(service_module, "session_validator", RevokedSession())
    agent = Agent.objects.create(
        tenant_id=tenant_id,
        name="Revoked user agent",
        identity_type="user_bound",
        subject_id=uuid4(),
        session_id=uuid4(),
        runner_key="test.runner",
        status="active",
        transition_history=[{"transition_key": "fixture", "command": "activate"}],
        created_by=actor_id,
    )
    result = ExecutionService.execute(tenant_id, actor_id, agent.id, {}, "stale-session")
    assert result.status == "failed"
    assert result.error_code == "SESSION_STALE"
    assert not AgentExecution.objects.filter(tenant_id=tenant_id, agent=agent).exists()
    assert not AsyncJob.objects.filter(tenant_id=tenant_id).exists()

    agent.status = "active"
    agent.transition_history = [{"transition_key": "fixture", "command": "activate"}]
    agent.save()
    runner_registry.unregister(agent.runner_key)
    unavailable = ExecutionService.execute(agent.tenant_id, actor_id, agent.id, {}, "missing-runner")
    assert unavailable.status == "unavailable"
    assert unavailable.http_status == 503
    assert not AsyncJob.objects.filter(tenant_id=agent.tenant_id).exists()


@pytest.mark.django_db
def test_execution_actions_require_matching_agent(execution, tenant_id, actor_id):
    another = Agent.objects.create(
        tenant_id=tenant_id,
        name="Different agent",
        identity_type="system_bound",
        subject_id=uuid4(),
        runner_key="test.runner",
        created_by=actor_id,
    )
    for action, args in (
        (ExecutionService.pause, ("pause",)),
        (ExecutionService.resume, ("resume",)),
        (ExecutionService.terminate, ("reason", "terminate")),
    ):
        with pytest.raises(ObjectDoesNotExist):
            action(tenant_id, actor_id, another.id, execution.id, *args)


@pytest.mark.django_db
def test_querydict_filters_keep_scalar_ordering_values(execution, agent, actor_id):
    due = timezone.now() + timedelta(hours=1)
    schedule = ScheduleService.create_schedule(
        agent.tenant_id,
        actor_id,
        agent.id,
        {"scheduled_at": due, "task_data": {"task": "later"}, "idempotency_key": "schedule:querydict"},
    )

    executions = ExecutionService.list_executions(
        execution.tenant_id, QueryDict("ordering=-created_at&page=1&page_size=25")
    )
    schedules = ScheduleService.list_schedules(
        schedule.tenant_id, QueryDict("ordering=scheduled_at&page=1&page_size=25")
    )

    assert execution in list(executions)
    assert list(schedules) == [schedule]


@pytest.mark.django_db
def test_get_schedule_reports_exact_invalid_uuid_fields(agent, actor_id) -> None:
    schedule = ScheduleService.create_schedule(
        agent.tenant_id,
        actor_id,
        agent.id,
        {
            "scheduled_at": timezone.now() + timedelta(hours=1),
            "task_data": {"task": "later"},
            "idempotency_key": "schedule:invalid-uuid",
        },
    )

    with pytest.raises(ValidationError) as invalid_tenant:
        ScheduleService.get_schedule("not-a-uuid", schedule.id)  # type: ignore[arg-type]
    assert invalid_tenant.value.message_dict == {"tenant_id": ["Must be a valid UUID."]}

    with pytest.raises(ValidationError) as invalid_task:
        ScheduleService.get_schedule(schedule.tenant_id, "not-a-uuid")  # type: ignore[arg-type]
    assert invalid_task.value.message_dict == {"task_id": ["Must be a valid UUID."]}


@pytest.mark.django_db
def test_schedule_is_durable_idempotent_and_recovers_stale(agent, actor_id):
    due = timezone.now() - timedelta(minutes=1)
    schedule = ScheduleService.create_schedule(
        agent.tenant_id,
        actor_id,
        agent.id,
        {"scheduled_at": due, "task_data": {"task": "later"}, "idempotency_key": "schedule:one"},
    )
    assert schedule.async_job_id
    assert AsyncJob.objects.filter(id=schedule.async_job_id, tenant_id=agent.tenant_id).exists()
    assert (
        ScheduleService.create_schedule(
            agent.tenant_id,
            actor_id,
            agent.id,
            {"scheduled_at": due, "task_data": {}, "idempotency_key": "schedule:one"},
        ).id
        == schedule.id
    )
    assert ScheduleService.dispatch_due(agent.tenant_id, timezone.now(), 10) == 1
    schedule.refresh_from_db()
    assert schedule.status == "queued"


@pytest.mark.django_db
def test_approval_self_decision_and_blank_rejection_roll_back(execution, tool, actor_id, approver_id):
    approval = ApprovalService.create_request(
        execution.tenant_id,
        actor_id,
        execution.id,
        None,
        {"tool_id": tool.id, "tool_input": {}, "justification": "controlled mutation"},
    )
    with pytest.raises(AgentServiceError) as self_decision:
        ApprovalService.approve(execution.tenant_id, actor_id, approval.id, "approve:self")
    assert self_decision.value.code == "SELF_APPROVAL_FORBIDDEN"
    with pytest.raises(ValidationError):
        ApprovalService.reject(execution.tenant_id, approver_id, approval.id, "", "reject:blank")
    approval.refresh_from_db()
    assert approval.status == "pending"
    assert approval.approver_id is None


@pytest.mark.django_db
def test_get_approval_request_reports_exact_invalid_uuid_fields(execution, tool, actor_id) -> None:
    approval = ApprovalService.create_request(
        execution.tenant_id,
        actor_id,
        execution.id,
        None,
        {"tool_id": tool.id, "tool_input": {}, "justification": "invalid uuid contract"},
    )

    with pytest.raises(ValidationError) as invalid_tenant:
        ApprovalService.get_request("not-a-uuid", approval.id)  # type: ignore[arg-type]
    assert invalid_tenant.value.message_dict == {"tenant_id": ["Must be a valid UUID."]}

    with pytest.raises(ValidationError) as invalid_approval:
        ApprovalService.get_request(approval.tenant_id, "not-a-uuid")  # type: ignore[arg-type]
    assert invalid_approval.value.message_dict == {"approval_id": ["Must be a valid UUID."]}


@pytest.mark.django_db
def test_approval_decision_and_expiry_are_terminal(execution, tool, actor_id, approver_id):
    approval = ApprovalService.create_request(
        execution.tenant_id,
        actor_id,
        execution.id,
        None,
        {"tool_id": tool.id, "tool_input": {}, "expires_at": timezone.now() + timedelta(hours=1)},
    )
    decided = ApprovalService.approve(execution.tenant_id, approver_id, approval.id, "approve:one")
    assert decided.status == "approved"
    assert decided.approver_id == approver_id
    assert decided.decided_at is not None
    with pytest.raises((IllegalTransitionError, TerminalStateError)):
        ApprovalService.reject(execution.tenant_id, uuid4(), approval.id, "changed", "reject:after")


@pytest.mark.django_db
def test_approval_cancel_policy_and_expire_pending_paths(execution, tool, actor_id, approver_id):
    cancellable = ApprovalService.create_request(
        execution.tenant_id,
        actor_id,
        execution.id,
        None,
        {"tool_id": tool.id, "tool_input": {}, "justification": "cancel test"},
    )
    with pytest.raises(AgentServiceError) as forbidden:
        ApprovalService.cancel(execution.tenant_id, approver_id, cancellable.id, "cancel:wrong-actor")
    assert forbidden.value.code == "APPROVAL_CANCEL_FORBIDDEN"
    cancelled = ApprovalService.cancel(execution.tenant_id, actor_id, cancellable.id, "cancel:requester")
    assert cancelled.status == "cancelled"
    assert cancelled.decided_at is not None

    expired = ApprovalService.create_request(
        execution.tenant_id,
        actor_id,
        execution.id,
        None,
        {
            "tool_id": tool.id,
            "tool_input": {},
            "requested_for": approver_id,
            "expires_at": timezone.now() + timedelta(hours=1),
        },
    )
    requested_at = timezone.now() - timedelta(hours=2)
    expires_at = timezone.now() - timedelta(hours=1)
    service_module.ApprovalRequest._base_manager.filter(pk=expired.pk).update(
        requested_at=requested_at,
        expires_at=expires_at,
    )
    assert ApprovalService.expire_pending(execution.tenant_id, timezone.now()) == 1
    expired.refresh_from_db()
    assert expired.status == "expired"
    assert expired.approver_id == approver_id


@pytest.mark.django_db
def test_sod_evaluates_immutable_audit_history(execution, tenant_id, actor_id):
    SoDService.create_policy(
        tenant_id,
        actor_id,
        {"name": "separate release", "action_1": "approve", "action_2": "release"},
    )
    AuditService.record_event(
        tenant_id,
        "release",
        actor_id,
        uuid4(),
        "success",
        request_id=uuid4(),
        agent_execution=execution,
    )
    denied = SoDService.evaluate(tenant_id, actor_id, "approve", execution.id)
    assert denied.status == "failed"
    assert denied.error_code == "SOD_VIOLATION"
    assert SoDService.evaluate(tenant_id, uuid4(), "approve", execution.id).status == "succeeded"


@pytest.mark.django_db
def test_sod_record_violation_reports_exact_invalid_tenant_field() -> None:
    with pytest.raises(ValidationError) as invalid_tenant:
        SoDService.record_violation("not-a-uuid")  # type: ignore[arg-type]
    assert invalid_tenant.value.message_dict == {"tenant_id": ["Must be a valid UUID."]}


@pytest.mark.django_db
def test_sod_policy_validation_update_filter_and_deactivation(tenant_id, actor_id):
    with pytest.raises(ValidationError):
        SoDService.create_policy(
            tenant_id,
            actor_id,
            {"name": "invalid", "action_1": "approve", "action_2": "approve"},
        )
    policy = SoDService.create_policy(
        tenant_id,
        actor_id,
        {"name": "ordered", "action_1": "release", "action_2": "approve"},
    )
    assert (policy.action_1, policy.action_2) == ("approve", "release")
    with pytest.raises(ValidationError):
        SoDService.update_policy(tenant_id, actor_id, policy.id, {"tenant_id": uuid4()})
    updated = SoDService.update_policy(
        tenant_id,
        actor_id,
        policy.id,
        {"name": "renamed", "action_1": "deploy", "action_2": "approve", "is_active": False},
    )
    assert (updated.name, updated.action_1, updated.action_2, updated.is_active) == (
        "renamed",
        "approve",
        "deploy",
        False,
    )
    assert list(SoDService.list_policies(tenant_id, {"is_active": False})) == [updated]
    assert SoDService.deactivate_policy(tenant_id, actor_id, policy.id).is_active is False


@pytest.mark.django_db
def test_tool_schema_failure_and_missing_implementation_are_explicit(execution, tool, actor_id):
    tool.input_schema = {
        "type": "object",
        "required": ["value"],
        "properties": {"value": {"type": "integer"}},
        "additionalProperties": False,
    }
    tool.save()
    with pytest.raises(ValueError, match="Schema validation failed"):
        ToolService.validate_input(tool.tenant_id, tool.id, {"value": "wrong"})
    unavailable = ToolService.invoke(tool.tenant_id, actor_id, execution.id, tool.id, {"value": 1}, "invoke:one")
    assert unavailable.status == "unavailable"
    assert unavailable.http_status == 503
    assert not ToolInvocation.objects.filter(tenant_id=tool.tenant_id).exists()


@pytest.mark.django_db
def test_tool_lifecycle_filters_and_validation_diagnostics_are_policy_bound(tool, tenant_id, actor_id):
    updated = ToolService.update_tool(
        tenant_id,
        actor_id,
        tool.id,
        {
            "description": "Updated tool",
            "input_schema": {
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "integer"}},
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "additionalProperties": False,
            },
        },
    )

    assert updated.description == "Updated tool"
    assert ToolService.validation_diagnostic(tenant_id, tool.id, "input", {"value": 1}) == {
        "valid": True,
        "direction": "input",
        "issues": (),
    }
    with pytest.raises(ValueError, match="Schema validation failed"):
        ToolService.validation_diagnostic(tenant_id, tool.id, "output", {"extra": True})
    with pytest.raises(ValidationError):
        ToolService.update_tool(tenant_id, actor_id, tool.id, {"tenant_id": uuid4()})

    assert list(ToolService.list_tools(tenant_id, {"owning_module": "ai_agent_management", "search": "test"})) == [tool]
    assert ToolService.deactivate_tool(tenant_id, actor_id, tool.id).is_active is False


@pytest.mark.django_db
def test_secret_round_trip_records_access_and_never_stringifies(execution, tenant_id, actor_id):
    secret = SecretService.create_secret(
        tenant_id,
        actor_id,
        {"name": "provider-token", "secret_type": "token", "plaintext": "test-secret-value"},
    )
    assert "test-secret-value" not in secret.ciphertext
    wrapped_before = secret.wrapped_data_key
    value = SecretService.resolve_for_execution(tenant_id, actor_id, secret.id, execution.id, "provider-call")
    assert value.reveal() == "test-secret-value"
    assert repr(value) == "SecretValue(***)"
    with pytest.raises(TypeError):
        str(value)
    assert SecretAccess.objects.filter(tenant_id=tenant_id, secret=secret, agent_execution=execution).count() == 1

    SecretService.rotate_secret(tenant_id, actor_id, secret.id, "rotated-secret")
    secret.refresh_from_db()
    assert secret.wrapped_data_key != wrapped_before
    rotated = SecretService.resolve_for_execution(tenant_id, actor_id, secret.id, execution.id, "retry")
    assert rotated.reveal() == "rotated-secret"


@pytest.mark.django_db
def test_secret_creation_validation_deactivation_and_blank_purpose_fail_closed(execution, tenant_id, actor_id):
    with pytest.raises(ValidationError):
        SecretService.create_secret(
            tenant_id,
            actor_id,
            {"name": "blank", "secret_type": "token", "plaintext": ""},
        )
    secret = SecretService.create_secret(
        tenant_id,
        actor_id,
        {"tenant_id": uuid4(), "created_by": uuid4(), "name": "token", "secret_type": "token", "plaintext": "value"},
    )

    assert secret.tenant_id == tenant_id
    assert secret.created_by == actor_id
    assert list(SecretService.list_metadata(tenant_id, {"secret_type": "token", "is_active": True})) == [secret]
    with pytest.raises(ValidationError):
        SecretService.resolve_for_execution(tenant_id, actor_id, secret.id, execution.id, "")
    SecretService.deactivate_secret(tenant_id, actor_id, secret.id)
    with pytest.raises(AgentServiceError) as inactive:
        SecretService.resolve_for_execution(tenant_id, actor_id, secret.id, execution.id, "provider-call")
    assert inactive.value.code == "SECRET_UNAVAILABLE"


@pytest.mark.django_db
def test_secret_rotation_is_idempotent_and_conflict_checked(tenant_id, actor_id):
    first = SecretService.create_secret(
        tenant_id,
        actor_id,
        {"name": "primary-token", "secret_type": "token", "plaintext": "first-value"},
    )
    second = SecretService.create_secret(
        tenant_id,
        actor_id,
        {"name": "secondary-token", "secret_type": "token", "plaintext": "second-value"},
    )

    rotated = SecretService.rotate_secret(
        tenant_id,
        actor_id,
        first.id,
        "first-rotated",
        idempotency_key="rotate:primary",
        correlation_id=uuid4(),
    )
    replay = SecretService.rotate_secret(
        tenant_id,
        actor_id,
        first.id,
        "ignored-replay-value",
        idempotency_key="rotate:primary",
        correlation_id=uuid4(),
    )

    assert replay.id == rotated.id
    with pytest.raises(IdempotencyConflictError):
        SecretService.rotate_secret(
            tenant_id,
            actor_id,
            second.id,
            "conflicting-value",
            idempotency_key="rotate:primary",
        )


@pytest.mark.django_db
def test_expired_secret_denies_without_access_evidence(execution, tenant_id, actor_id, monkeypatch):
    expires_at = timezone.now() + timedelta(minutes=1)
    secret = SecretService.create_secret(
        tenant_id,
        actor_id,
        {
            "name": "expired",
            "secret_type": "api_key",
            "plaintext": "expired-value",
            "expires_at": expires_at,
        },
    )
    monkeypatch.setattr(
        "src.modules.ai_agent_management.services.timezone.now",
        lambda: expires_at + timedelta(seconds=1),
    )
    with pytest.raises(AgentServiceError) as caught:
        SecretService.resolve_for_execution(tenant_id, actor_id, secret.id, execution.id, "provider-call")
    assert caught.value.code == "SECRET_UNAVAILABLE"
    assert not SecretAccess.objects.filter(secret=secret).exists()


@pytest.mark.django_db
def test_unknown_pricing_is_unavailable_and_never_records_zero(tenant_id):
    result = UsageService.record_cost(
        tenant_id,
        Decimal("1.25000000"),
        None,
        module_name="ai_agent_management",
        cost_type="api_call",
        currency="USD",
    )
    assert result.status == "unavailable"
    assert result.error_code == "CAPABILITY_UNAVAILABLE"
    assert not result.evidence


@pytest.mark.django_db
def test_quota_reservation_never_overspends_and_records_only_success(tenant_id):
    quota = Quota.objects.create(
        tenant_id=tenant_id,
        resource="ai.execution",
        limit=1,
        remaining=1,
    )
    first = UsageService.reserve_quota(tenant_id, "ai.execution", 1)
    second = UsageService.reserve_quota(tenant_id, "ai.execution", 1)
    quota.refresh_from_db()
    assert first.status == "succeeded"
    assert first.unwrap() == 0
    assert second.status == "failed"
    assert second.error_code == "QUOTA_EXCEEDED"
    assert quota.remaining == 0
    usage = UsageService.get_usage(tenant_id)["usage"]
    assert usage.count() == 1
    assert usage.get().remaining_after == 0


@pytest.mark.django_db
def test_record_quota_usage_reports_exact_invalid_tenant_field() -> None:
    with pytest.raises(ValidationError) as invalid_tenant:
        UsageService.record_quota_usage("not-a-uuid", "ai.execution", 1, 0)  # type: ignore[arg-type]
    assert invalid_tenant.value.message_dict == {"tenant_id": ["Must be a valid UUID."]}


@pytest.mark.django_db
def test_record_token_usage_reports_exact_invalid_tenant_field(execution) -> None:
    with pytest.raises(ValidationError) as invalid_tenant:
        UsageService.record_token_usage(  # type: ignore[arg-type]
            "not-a-uuid",
            execution.id,
            provider="test-provider",
            model="test-model",
            input_tokens=1,
            output_tokens=1,
        )
    assert invalid_tenant.value.message_dict == {"tenant_id": ["Must be a valid UUID."]}


@pytest.mark.django_db
def test_usage_cost_breakdown_and_summary_are_period_scoped(tenant_id, execution):
    start = timezone.now() - timedelta(hours=1)
    end = timezone.now() + timedelta(hours=1)
    UsageService.record_cost(
        tenant_id,
        Decimal("1.25000000"),
        "pricing-2026.08",
        agent_execution=execution,
        module_name="ai_agent_management",
        cost_type="api_call",
        currency="USD",
    ).unwrap()
    UsageService.record_cost(
        tenant_id,
        Decimal("0.75000000"),
        "pricing-2026.08",
        module_name="ai_agent_management",
        cost_type="token",
        currency="USD",
    ).unwrap()
    UsageService.record_token_usage(
        tenant_id,
        execution.id,
        provider="test-provider",
        model="test-model",
        input_tokens=11,
        output_tokens=7,
        metadata={"tenant_id": str(uuid4()), "model": "redacted", "safe": "kept"},
    )

    breakdown = UsageService.get_cost_breakdown(tenant_id, start, end)
    summary = UsageService.generate_cost_summary(tenant_id, start, end, "hourly", "USD")

    assert breakdown["total"] == Decimal("2")
    assert {row["cost_type"]: row["total"] for row in breakdown["by_type"]} == {
        "api_call": Decimal("1.25"),
        "token": Decimal("0.75"),
    }
    assert summary.total_cost == Decimal("2")
    assert summary.cost_by_type == {"api_call": "1.25", "token": "0.75"}
    assert summary.total_tokens == 18
    assert summary.total_executions == 1


@pytest.mark.django_db
def test_egress_normalization_rejects_unsafe_destinations(tenant_id):
    assert EgressService.normalize("domain", "Example.COM.", tenant_id) == "example.com"
    assert EgressService.normalize("url_pattern", "https://Example.COM:8443/path", tenant_id) == (
        "https://example.com:8443/path"
    )
    with pytest.raises(ValidationError):
        EgressService.normalize("domain", "*.example.com", tenant_id)
    with pytest.raises(ValidationError):
        EgressService.normalize("domain", "localhost", tenant_id)
    with pytest.raises(ValidationError):
        EgressService.normalize("url_pattern", "https://" + "user" + ":" + "pass" + "@example.com/path", tenant_id)
    with pytest.raises(ValidationError):
        EgressService.normalize("cidr", "10.0.0.0/24", tenant_id)
    with pytest.raises(ValidationError):
        EgressService.normalize("unsupported", "example.com", tenant_id)


@pytest.mark.django_db
def test_egress_evaluation_records_allowlist_match_and_denial(execution, tenant_id, actor_id, monkeypatch):
    rule = EgressService.create_rule(
        tenant_id,
        actor_id,
        {
            "name": "Example HTTPS",
            "destination_type": "domain",
            "destination": "example.com",
            "port": 443,
            "protocol": "https",
        },
    )

    def resolve_public_address(host, port):
        assert host == "example.com"
        return [(None, None, None, None, ("93.184.216.34", port))]

    monkeypatch.setattr(service_module.socket, "getaddrinfo", resolve_public_address)

    allowed = EgressService.evaluate(tenant_id, execution.id, "https://example.com/resource", 443, "https")
    denied = EgressService.evaluate(tenant_id, execution.id, "https://example.com/resource", 444, "https")

    assert allowed.allowed is True
    assert allowed.reason_code == "ALLOWLIST_MATCH"
    assert allowed.matched_rule_id == rule.id
    assert allowed.resolved_address == "93.184.216.34"
    assert denied.allowed is False
    assert denied.reason_code == "EGRESS_DENIED"
    assert denied.matched_rule is None
    assert list(EgressRule.objects.filter(tenant_id=tenant_id)) == [rule]
    assert EgressRequest.objects.filter(tenant_id=tenant_id, agent_execution=execution).count() == 2


@pytest.mark.django_db
def test_egress_rule_update_list_deactivate_and_dns_failure_are_explicit(execution, tenant_id, actor_id, monkeypatch):
    rule = EgressService.create_rule(
        tenant_id,
        actor_id,
        {
            "tenant_id": uuid4(),
            "created_by": uuid4(),
            "name": "Example",
            "destination_type": "domain",
            "destination": "Example.COM.",
            "port": None,
            "protocol": "https",
        },
    )
    updated = EgressService.update_rule(
        tenant_id,
        actor_id,
        rule.id,
        {"name": "Example API", "destination_type": "url_pattern", "destination": "https://Example.COM/api"},
    )
    assert updated.destination == "https://example.com/api"
    with pytest.raises(ValidationError):
        EgressService.update_rule(tenant_id, actor_id, rule.id, {"created_by": uuid4()})
    assert list(EgressService.list_rules(tenant_id, {"destination_type": "url_pattern", "protocol": "https"})) == [
        updated
    ]

    monkeypatch.setattr(service_module.socket, "getaddrinfo", Mock(side_effect=OSError("dns unavailable")))
    denied = EgressService.evaluate(tenant_id, execution.id, "https://example.com/api", 443, "https")
    assert denied.allowed is False
    assert denied.reason_code == "EGRESS_DENIED"
    assert denied.resolved_address is None

    assert EgressService.deactivate_rule(tenant_id, actor_id, rule.id).is_active is False


@pytest.mark.django_db
def test_kill_switch_is_tenant_scoped_and_enqueues_enforcement(tenant_id, other_tenant_id, actor_id):
    switch = KillSwitchService.activate(tenant_id, actor_id, "tenant", None, "incident", "kill:one")
    assert KillSwitchService.check(tenant_id).error_code == "KILL_SWITCH_ACTIVE"
    assert KillSwitchService.check(other_tenant_id).status == "succeeded"
    assert AsyncJob.objects.filter(tenant_id=tenant_id, command="ai_agent_management.enforce_kill_switch").exists()
    KillSwitchService.deactivate(tenant_id, actor_id, switch.id, "recovered", "kill:off")
    switch.refresh_from_db()
    assert switch.status == "inactive"
    assert switch.deactivated_by == actor_id


@pytest.mark.django_db
def test_list_kill_switches_reports_exact_invalid_tenant_field() -> None:
    with pytest.raises(ValidationError) as invalid_tenant:
        list(KillSwitchService.list_switches("not-a-uuid"))  # type: ignore[arg-type]
    assert invalid_tenant.value.message_dict == {"tenant_id": ["Must be a valid UUID."]}


@pytest.mark.django_db
def test_deactivate_kill_switch_reports_exact_invalid_uuid_fields(tenant_id, actor_id) -> None:
    switch = KillSwitchService.activate(tenant_id, actor_id, "tenant", None, "incident", "kill:invalid-uuid")

    with pytest.raises(ValidationError) as invalid_tenant:
        KillSwitchService.deactivate(  # type: ignore[arg-type]
            "not-a-uuid", actor_id, switch.id, "recovered", "kill:bad-tenant"
        )
    assert invalid_tenant.value.message_dict == {"tenant_id": ["Must be a valid UUID."]}

    with pytest.raises(ValidationError) as invalid_switch:
        KillSwitchService.deactivate(  # type: ignore[arg-type]
            tenant_id, actor_id, "not-a-uuid", "recovered", "kill:bad-id"
        )
    assert invalid_switch.value.message_dict == {"kill_switch_id": ["Must be a valid UUID."]}


@pytest.mark.django_db
def test_audit_metadata_is_allowlisted_and_tenant_scoped(execution, tenant_id, other_tenant_id, actor_id):
    event = AuditService.record_event(
        tenant_id,
        "agent_started",
        actor_id,
        uuid4(),
        "pending",
        request_id=uuid4(),
        agent_execution=execution,
        metadata={
            "runner_key": "test.runner",
            "prompt": "must never persist",
            "authorization": "must never persist",
            "provider_body": "must never persist",
        },
    )
    assert event.metadata == {"runner_key": "test.runner"}
    assert list(AuditService.query_events(tenant_id)) == [event]
    assert not AuditService.query_events(other_tenant_id).exists()


@pytest.mark.django_db
def test_audit_record_event_requires_exact_request_id_relation(tenant_id, actor_id):
    with pytest.raises(ValidationError) as missing_request:
        AuditService.record_event(tenant_id, "agent_started", actor_id, uuid4(), "pending")
    assert missing_request.value.message_dict == {"request_id": ["This relation is required."]}

    with pytest.raises(ValidationError) as invalid_request:
        AuditService.record_event(
            tenant_id,
            "agent_started",
            actor_id,
            uuid4(),
            "pending",
            request_id="not-a-uuid",
        )
    assert invalid_request.value.message_dict == {"request_id": ["Must be a valid UUID."]}

    request_id = uuid4()
    with pytest.raises(ValidationError) as invalid_tenant:
        AuditService.record_event(  # type: ignore[arg-type]
            "not-a-uuid",
            "agent_started",
            actor_id,
            uuid4(),
            "pending",
            request_id=request_id,
        )
    assert invalid_tenant.value.message_dict == {"tenant_id": ["Must be a valid UUID."]}

    with pytest.raises(ValidationError) as invalid_actor:
        AuditService.record_event(  # type: ignore[arg-type]
            tenant_id,
            "agent_started",
            "not-a-uuid",
            uuid4(),
            "pending",
            request_id=request_id,
        )
    assert invalid_actor.value.message_dict == {"actor_id": ["Must be a valid UUID."]}

    with pytest.raises(ValidationError) as invalid_subject:
        AuditService.record_event(  # type: ignore[arg-type]
            tenant_id,
            "agent_started",
            actor_id,
            "not-a-uuid",
            "pending",
            request_id=request_id,
        )
    assert invalid_subject.value.message_dict == {"subject_id": ["Must be a valid UUID."]}


@pytest.mark.django_db
def test_get_audit_trail_reports_exact_invalid_uuid_fields(tenant_id) -> None:
    request_id = uuid4()

    with pytest.raises(ValidationError) as invalid_tenant:
        AuditService.get_trail("not-a-uuid", request_id)  # type: ignore[arg-type]
    assert invalid_tenant.value.message_dict == {"tenant_id": ["Must be a valid UUID."]}

    with pytest.raises(ValidationError) as invalid_request:
        AuditService.get_trail(tenant_id, "not-a-uuid")  # type: ignore[arg-type]
    assert invalid_request.value.message_dict == {"request_id": ["Must be a valid UUID."]}


@pytest.mark.django_db
def test_get_audit_trail_eager_loads_execution(execution, actor_id) -> None:
    request_id = uuid4()
    AuditService.start_trail(execution.tenant_id, request_id, execution.id, actor_id)

    with CaptureQueriesContext(connection) as queries:
        trail = AuditService.get_trail(execution.tenant_id, request_id)
        assert trail.agent_execution.id == execution.id

    assert len(queries) == 1


def test_configuration_rejects_weakened_runtime_guards_and_duplicate_navigation():
    with pytest.raises(ValidationError) as non_object:
        ConfigurationService.validate_document([])  # type: ignore[arg-type]
    assert "document" in non_object.value.message_dict

    document = deepcopy(DEFAULT_CONFIGURATION)
    document["schema_version"] = "future"
    with pytest.raises(ValidationError) as bad_schema:
        ConfigurationService.validate_document(document)
    assert "schema_version" in bad_schema.value.message_dict

    document = deepcopy(DEFAULT_CONFIGURATION)
    del document["runner"]["allowed_roles"]
    with pytest.raises(ValidationError) as incomplete_section:
        ConfigurationService.validate_document(document)
    assert "runner" in incomplete_section.value.message_dict

    invalid_cases = [
        ("provider.max_tokens", {"provider": {"max_tokens": True}}),
        ("schedule.default_priority", {"schedule": {"priority_minimum": 10, "default_priority": 0}}),
        ("schedule.dispatch_batch_minimum", {"schedule": {"dispatch_batch_minimum": 5, "dispatch_batch_maximum": 1}}),
        (
            "evaluation.quality_warn_threshold",
            {"evaluation": {"quality_warn_threshold": 0.9, "quality_pass_threshold": 0.8}},
        ),
        ("runner.allowed_task_fields", {"runner": {"allowed_task_fields": ["messages", "unsafe"]}}),
        ("runner.allowed_roles", {"runner": {"allowed_roles": ["user", "root"]}}),
        ("agent.metadata_fields", {"agent": {"metadata_fields": ["runner_key", "prompt"]}}),
        ("agent.ordering_fields", {"agent": {"ordering_fields": ["name", "tenant_id"]}}),
        ("egress.allowed_url_schemes", {"egress": {"allowed_url_schemes": ["file"]}}),
        ("egress.forbidden_ip_addresses", {"egress": {"forbidden_ip_addresses": ["169.254.169.254", "not-ip"]}}),
        ("egress.internal_hostname_suffixes", {"egress": {"internal_hostname_suffixes": ["localhost", "bad host"]}}),
        ("evaluation.latency_percentiles", {"evaluation": {"latency_percentiles": [0.5, 1]}}),
        ("approval.requester_may_approve_own_request", {"approval": {"requester_may_approve_own_request": "no"}}),
        (
            "agent.identity_session_rules.user_bound_requires_session",
            {"agent": {"identity_session_rules": {"user_bound_requires_session": "yes"}}},
        ),
        (
            "agent.execution_state_transitions.queued",
            {"agent": {"execution_state_transitions": {"queued": ["queued"]}}},
        ),
        ("ui.status_tokens", {"ui": {"status_tokens": {"success": "green"}}}),
        ("ui.status_token_by_state", {"ui": {"status_token_by_state": {"queued": "unknown"}}}),
        ("ui.navigation_order", {"ui": {"navigation_order": {"agents": 1}}}),
        ("rollout.roles", {"rollout": {"roles": [""]}}),
    ]
    for field, patch in invalid_cases:
        document = deepcopy(DEFAULT_CONFIGURATION)
        for section, values in patch.items():
            if section == "agent" and "identity_session_rules" in values:
                document[section]["identity_session_rules"].update(values["identity_session_rules"])
            elif section == "agent" and "execution_state_transitions" in values:
                document[section]["execution_state_transitions"].update(values["execution_state_transitions"])
            elif isinstance(values, dict) and isinstance(document.get(section), dict):
                document[section].update(values)
            else:
                document[section] = values
        with pytest.raises(ValidationError) as caught:
            ConfigurationService.validate_document(document)
        assert field in caught.value.message_dict

    document = deepcopy(DEFAULT_CONFIGURATION)
    document["egress"]["forbidden_ip_addresses"].remove("169.254.169.254")
    with pytest.raises(ValidationError) as denied_ssrf_policy:
        ConfigurationService.validate_document(document)
    assert "egress.forbidden_ip_addresses" in denied_ssrf_policy.value.message_dict

    document = deepcopy(DEFAULT_CONFIGURATION)
    document["ui"]["navigation_order"]["agents"] = document["ui"]["navigation_order"]["executions"]
    with pytest.raises(ValidationError) as duplicate_order:
        ConfigurationService.validate_document(document)
    assert "ui.navigation_order" in duplicate_order.value.message_dict

    document = deepcopy(DEFAULT_CONFIGURATION)
    document["agent"]["execution_state_transitions"]["completed"] = ["queued"]
    with pytest.raises(ValidationError) as terminal_escape:
        ConfigurationService.validate_document(document)
    assert "agent.execution_state_transitions.completed" in terminal_escape.value.message_dict


@pytest.mark.django_db
def test_correlation_and_database_session_validation_fail_closed(monkeypatch, tenant_id, actor_id):
    validator = service_module.DatabaseSessionValidator()
    assert validator.is_active(tenant_id, actor_id, uuid4()) is False

    monkeypatch.setattr(service_module, "get_correlation_id", lambda: "not-a-uuid")
    assert service_module._correlation_uuid(actor_id) == actor_id
    with pytest.raises(ValidationError) as missing_correlation:
        service_module._correlation_uuid()
    assert "correlation_id" in missing_correlation.value.message_dict


@pytest.mark.django_db
def test_configuration_replace_export_rollback_and_import_are_versioned(tenant_id, actor_id):
    correlation_id = uuid4()
    proposed = deepcopy(DEFAULT_CONFIGURATION)
    proposed["schedule"]["dispatch_batch_maximum"] = 25

    preview = ConfigurationService.preview(
        tenant_id,
        actor_id,
        correlation_id,
        proposed,
        environment="staging",
        expected_version=1,
    )
    assert preview["proposed_version"] == 2
    replaced = ConfigurationService.replace(
        tenant_id,
        actor_id,
        correlation_id,
        proposed,
        environment="staging",
        expected_version=1,
    )
    assert replaced.version == 2
    exported = ConfigurationService.export_document(tenant_id, actor_id, correlation_id, "staging")
    assert exported["configuration"]["schedule"]["dispatch_batch_maximum"] == 25
    exported["expected_version"] = 3
    rolled_back = ConfigurationService.rollback(tenant_id, actor_id, correlation_id, 1, "staging")
    assert rolled_back.version == 3
    imported = ConfigurationService.import_document(tenant_id, actor_id, correlation_id, exported)
    assert imported.version == 4
    assert ConfigurationService.versions(tenant_id, "staging").count() == 4


@pytest.mark.django_db
def test_schedule_limits_recover_stale_and_cancel_are_policy_bound(agent, actor_id):
    with pytest.raises(ValidationError) as bad_batch:
        ScheduleService.dispatch_due(agent.tenant_id, timezone.now(), 0)
    assert "limit" in bad_batch.value.message_dict

    due = timezone.now() - timedelta(minutes=5)
    schedule = ScheduleService.create_schedule(
        agent.tenant_id,
        actor_id,
        agent.id,
        {
            "scheduled_at": due,
            "task_data": {"task": "recover"},
            "idempotency_key": "schedule:recover",
            "max_retries": 1,
        },
    )
    ScheduleService.dispatch_due(agent.tenant_id, timezone.now(), 1)
    schedule.refresh_from_db()
    type(schedule)._base_manager.filter(pk=schedule.pk).update(
        status="running",
        updated_at=timezone.now() - timedelta(hours=2),
    )

    assert ScheduleService.recover_stale(agent.tenant_id, timezone.now() - timedelta(hours=1)) == 1
    schedule.refresh_from_db()
    assert schedule.status == "pending"
    assert schedule.retry_count == 1
    cancelled = ScheduleService.cancel_schedule(agent.tenant_id, actor_id, schedule.id, "cancel:recover")
    assert cancelled.status == "cancelled"
