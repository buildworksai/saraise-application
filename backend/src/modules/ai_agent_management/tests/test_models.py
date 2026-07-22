"""Domain-model contract tests for the governed AI runtime."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from src.core.tenancy import TenantScopedModel
from src.modules.ai_agent_management.approval_models import ApprovalRequest, SoDPolicy, SoDViolation
from src.modules.ai_agent_management.audit_models import AuditEvent, AuditTrail, AuditTrailEvent
from src.modules.ai_agent_management.egress_models import EgressRequest, EgressRule, Secret, SecretAccess
from src.modules.ai_agent_management.models import Agent, AgentExecution, AgentSchedulerTask
from src.modules.ai_agent_management.quota_models import KillSwitch, QuotaUsage, ShardSaturation
from src.modules.ai_agent_management.token_models import CostRecord, CostSummary, TokenUsage
from src.modules.ai_agent_management.tool_models import Tool, ToolInvocation

ALL_MODELS = (
    Agent,
    AgentExecution,
    AgentSchedulerTask,
    ApprovalRequest,
    SoDPolicy,
    SoDViolation,
    Tool,
    ToolInvocation,
    EgressRule,
    EgressRequest,
    Secret,
    SecretAccess,
    QuotaUsage,
    ShardSaturation,
    KillSwitch,
    TokenUsage,
    CostRecord,
    CostSummary,
    AuditEvent,
    AuditTrail,
    AuditTrailEvent,
)


def _fields(names: str) -> set[str]:
    return set(names.split())


EXPECTED_FIELDS = {
    Agent: _fields(
        "name description identity_type subject_id session_id runner_key provider_config_id config status "
        "transition_history created_by deleted_at"
    ),
    AgentExecution: _fields(
        "agent async_job_id state transition_history initiating_actor_id session_id task_definition input_metadata "
        "result error_code error_message started_at completed_at idempotency_key provider_config_id"
    ),
    AgentSchedulerTask: _fields(
        "agent execution async_job_id scheduled_at priority max_retries retry_count status transition_history "
        "task_data error_code error_message started_at completed_at created_by idempotency_key"
    ),
    ApprovalRequest: _fields(
        "tool agent_execution tool_invocation requested_by requested_for approver_id status transition_history "
        "tool_input justification rejection_reason requested_at expires_at decided_at metadata"
    ),
    SoDPolicy: _fields("name description action_1 action_2 is_active created_by"),
    SoDViolation: _fields(
        "policy agent_execution tool_invocation action_1_user action_2_user action_1_timestamp "
        "action_2_timestamp blocked violation_at evidence"
    ),
    Tool: _fields(
        "name owning_module version description required_permissions input_schema output_schema side_effect_class "
        "is_active metadata registered_by registered_at"
    ),
    ToolInvocation: _fields(
        "tool agent_execution approval_request status transition_history input_data output_data error_code "
        "error_message invoked_at completed_at duration_ms idempotency_key"
    ),
    EgressRule: _fields("name description destination_type destination port protocol is_active created_by"),
    EgressRequest: _fields(
        "agent_execution destination resolved_address port protocol allowed matched_rule requested_at "
        "reason_code metadata"
    ),
    Secret: _fields(
        "name description secret_type ciphertext wrapped_data_key key_id is_active expires_at last_rotated_at "
        "rotation_interval_days created_by"
    ),
    SecretAccess: _fields("secret agent_execution accessed_by accessed_at purpose metadata"),
    QuotaUsage: _fields("resource agent_execution usage_value remaining_after usage_timestamp metadata"),
    ShardSaturation: _fields(
        "shard_id saturation_level active_agents active_executions cpu_usage_percent memory_usage_percent measured_at"
    ),
    KillSwitch: _fields(
        "name description scope scope_id status transition_history reason activated_by activated_at "
        "deactivated_by deactivated_at"
    ),
    TokenUsage: _fields(
        "agent_execution provider model input_tokens output_tokens total_tokens usage_timestamp metadata"
    ),
    CostRecord: _fields(
        "agent_execution tool_invocation module_name cost_type provider amount currency pricing_version "
        "cost_timestamp metadata"
    ),
    CostSummary: _fields(
        "period_start period_end period_type total_cost currency cost_by_type cost_by_module cost_by_provider "
        "total_tokens total_executions calculated_at"
    ),
    AuditEvent: _fields(
        "event_type agent_execution tool_invocation approval_request initiating_principal subject_id session_id "
        "request_id correlation_id event_timestamp outcome outcome_details policy_decisions workflow_transitions "
        "affected_resources metadata"
    ),
    AuditTrail: _fields(
        "request_id correlation_id agent_execution initiating_principal request_timestamp completed_timestamp "
        "final_outcome events summary"
    ),
    AuditTrailEvent: _fields("audit_trail audit_event position linked_at"),
}


@pytest.mark.parametrize("model", ALL_MODELS)
def test_every_entity_uses_native_tenant_uuid_identity(model):
    assert issubclass(model, TenantScopedModel)
    assert isinstance(model._meta.get_field("id"), models.UUIDField)
    assert model._meta.get_field("id").primary_key
    tenant_field = model._meta.get_field("tenant_id")
    assert isinstance(tenant_field, models.UUIDField)
    assert tenant_field.db_index


@pytest.mark.parametrize("model", ALL_MODELS)
def test_schema_contains_every_brief_field(model):
    concrete = {field.name for field in model._meta.get_fields() if not field.auto_created}
    assert EXPECTED_FIELDS[model] <= concrete


@pytest.mark.parametrize("model", ALL_MODELS)
def test_documented_indexes_are_tenant_led(model):
    assert model._meta.indexes, f"{model.__name__} must declare its query indexes"
    for index in model._meta.indexes:
        assert index.fields[0] == "tenant_id", f"{model.__name__}.{index.name} is not tenant-led"


@pytest.mark.parametrize(
    ("model", "field"),
    (
        (AgentExecution, "agent"),
        (AgentSchedulerTask, "agent"),
        (AgentSchedulerTask, "execution"),
        (ApprovalRequest, "tool"),
        (ApprovalRequest, "agent_execution"),
        (ApprovalRequest, "tool_invocation"),
        (SoDViolation, "policy"),
        (ToolInvocation, "tool"),
        (EgressRequest, "agent_execution"),
        (SecretAccess, "secret"),
        (TokenUsage, "agent_execution"),
        (CostRecord, "agent_execution"),
        (AuditEvent, "agent_execution"),
        (AuditTrail, "agent_execution"),
    ),
)
def test_evidence_relations_protect_their_parents(model, field):
    assert model._meta.get_field(field).remote_field.on_delete is models.PROTECT


@pytest.mark.django_db
def test_agent_defaults_uuid_and_soft_retirement(agent):
    assert isinstance(agent.id, UUID)
    assert agent.status == "draft"
    assert agent.config == {}
    assert agent.transition_history == []
    assert agent.deleted_at is None

    agent.delete()
    agent.refresh_from_db()
    assert agent.status == "retired"
    assert agent.deleted_at is not None
    assert agent.transition_history[-1]["transition"] == "retire"


@pytest.mark.django_db
def test_identity_session_constraint_is_enforced(tenant_id, actor_id):
    with pytest.raises(ValidationError):
        Agent.objects.create(
            tenant_id=tenant_id,
            name="Unsafe user agent",
            identity_type="user_bound",
            subject_id=uuid4(),
            session_id=None,
            runner_key="test.runner",
            created_by=actor_id,
        )
    with pytest.raises(ValidationError):
        Agent.objects.create(
            tenant_id=tenant_id,
            name="Unsafe system agent",
            identity_type="system_bound",
            subject_id=uuid4(),
            session_id=uuid4(),
            runner_key="test.runner",
            created_by=actor_id,
        )


@pytest.mark.django_db
def test_live_agent_name_is_unique_per_tenant(agent, tenant_id, actor_id):
    duplicate = Agent(
        tenant_id=tenant_id,
        name=agent.name,
        identity_type="system_bound",
        subject_id=uuid4(),
        runner_key="other.runner",
        created_by=actor_id,
    )
    with pytest.raises(ValidationError):
        duplicate.full_clean()


@pytest.mark.django_db
def test_same_tenant_relation_guard_rejects_cross_tenant(agent, other_tenant_id, actor_id):
    execution = AgentExecution(
        tenant_id=other_tenant_id,
        agent=agent,
        async_job_id=uuid4(),
        initiating_actor_id=actor_id,
        task_definition={},
        idempotency_key="cross-tenant",
    )
    with pytest.raises(ValidationError, match="referenced record"):
        execution.full_clean()


@pytest.mark.django_db
def test_execution_idempotency_is_tenant_scoped(execution, tenant_id, actor_id, agent):
    duplicate = AgentExecution(
        tenant_id=tenant_id,
        agent=agent,
        async_job_id=uuid4(),
        initiating_actor_id=actor_id,
        task_definition={},
        idempotency_key=execution.idempotency_key,
    )
    with pytest.raises(ValidationError):
        duplicate.full_clean()


@pytest.mark.django_db
def test_terminal_execution_and_bulk_lifecycle_writes_are_rejected(execution):
    execution.state = "failed"
    execution.completed_at = timezone.now()
    execution.error_code = "TEST_FAILURE"
    execution.transition_history = [{"transition_key": "fail"}]
    execution.save()

    execution.error_message = "tampered"
    with pytest.raises(ValidationError, match="immutable"):
        execution.save()
    with pytest.raises(ValidationError, match="service"):
        AgentExecution.objects.filter(pk=execution.pk).update(state="running")
    with pytest.raises(ValidationError, match="cannot be deleted"):
        execution.delete()


@pytest.mark.django_db
def test_append_only_evidence_rejects_all_mutation(tenant_id):
    usage = QuotaUsage.objects.create(
        tenant_id=tenant_id,
        resource="ai.execution",
        usage_value=1,
        remaining_after=9,
    )
    usage.remaining_after = 8
    with pytest.raises(ValidationError, match="append-only"):
        usage.save()
    with pytest.raises(ValidationError, match="append-only"):
        QuotaUsage.objects.filter(pk=usage.pk).update(remaining_after=8)
    with pytest.raises(ValidationError, match="append-only"):
        QuotaUsage.objects.filter(pk=usage.pk).delete()


@pytest.mark.django_db
def test_tool_schema_defaults_and_string(tool):
    assert tool.is_active is True
    assert tool.metadata == {}
    assert tool.required_permissions == ["ai.tool:invoke"]
    assert str(tool) == "test.tool v1.0.0 (ai_agent_management)"


@pytest.mark.django_db
def test_egress_rejects_wildcards_and_non_public_addresses(tenant_id, actor_id):
    for destination_type, destination in (("domain", "*.example.com"), ("ip", "127.0.0.1"), ("cidr", "10.0.0.0/8")):
        rule = EgressRule(
            tenant_id=tenant_id,
            name=f"reject-{destination_type}",
            destination_type=destination_type,
            destination=destination,
            protocol="https",
            created_by=actor_id,
        )
        with pytest.raises(ValidationError):
            rule.full_clean()


@pytest.mark.django_db
def test_sod_actions_are_canonicalized_and_not_self_conflicting(tenant_id, actor_id):
    policy = SoDPolicy.objects.create(
        tenant_id=tenant_id,
        name="Release separation",
        action_1="release",
        action_2="approve",
        created_by=actor_id,
    )
    assert (policy.action_1, policy.action_2) == ("approve", "release")
    with pytest.raises(ValidationError):
        SoDPolicy.objects.create(
            tenant_id=tenant_id,
            name="Invalid",
            action_1="approve",
            action_2="approve",
            created_by=actor_id,
        )


@pytest.mark.django_db
def test_string_representations_are_stable(agent, execution):
    assert agent.name in str(agent)
    assert str(agent.id) in str(agent)
    assert str(execution.id) in str(execution)
    assert execution.state in str(execution)
