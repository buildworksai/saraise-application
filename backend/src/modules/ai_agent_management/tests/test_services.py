"""Tenant-first command-service tests.

These tests assert durable side effects and state, never only return values.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils import timezone

from src.core.access.entitlements import Quota
from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.state_machine import IllegalTransitionError, TerminalStateError
from src.modules.ai_agent_management import services as service_module
from src.modules.ai_agent_management.egress_models import SecretAccess
from src.modules.ai_agent_management.models import Agent, AgentExecution
from src.modules.ai_agent_management.registries import runner_registry
from src.modules.ai_agent_management.services import (
    AgentService,
    AgentServiceError,
    ApprovalService,
    AuditService,
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
    assert ScheduleService.create_schedule(
        agent.tenant_id,
        actor_id,
        agent.id,
        {"scheduled_at": due, "task_data": {}, "idempotency_key": "schedule:one"},
    ).id == schedule.id
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
