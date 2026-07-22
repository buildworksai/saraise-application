"""Complete API isolation matrix using the canonical reusable contract."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework import status

from src.core.access.permissions import RequiresAccess
from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.testing import TenantIsolationContract
from src.modules.ai_agent_management.approval_models import ApprovalRequest, SoDPolicy
from src.modules.ai_agent_management.audit_models import AuditEvent
from src.modules.ai_agent_management.egress_models import EgressRequest, EgressRule, Secret
from src.modules.ai_agent_management.models import Agent, AgentExecution, AgentSchedulerTask
from src.modules.ai_agent_management.quota_models import KillSwitch, QuotaUsage
from src.modules.ai_agent_management.token_models import CostRecord, TokenUsage
from src.modules.ai_agent_management.tool_models import Tool, ToolInvocation

BASE = "/api/v2/ai-agent-management"


@pytest.fixture(autouse=True)
def allow_isolation_access(monkeypatch):
    """Keep session identity real while isolating the external policy decision."""

    monkeypatch.setattr(RequiresAccess, "has_permission", lambda self, request, view: True)
    monkeypatch.setattr(RequiresAccess, "has_object_permission", lambda self, request, view, obj: True)


def _agent(tenant_id, name, actor):
    return Agent.objects.create(
        tenant_id=tenant_id,
        name=name,
        identity_type="system_bound",
        subject_id=uuid4(),
        runner_key="isolation.runner",
        created_by=actor,
    )


def _execution(tenant_id, agent, actor, key):
    return AgentExecution.objects.create(
        tenant_id=tenant_id,
        agent=agent,
        async_job_id=uuid4(),
        initiating_actor_id=actor,
        task_definition={},
        idempotency_key=key,
    )


def _tool(tenant_id, name, actor):
    return Tool.objects.create(
        tenant_id=tenant_id,
        name=name,
        owning_module="ai_agent_management",
        version="1.0.0",
        required_permissions=[],
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        side_effect_class="read_only",
        registered_by=actor,
    )


@pytest.fixture
def isolation_world(db, tenant_a, tenant_b):
    actor_a, actor_b = uuid4(), uuid4()
    agent_a = _agent(tenant_a.id, "Tenant A agent", actor_a)
    agent_b = _agent(tenant_b.id, "Tenant B agent", actor_b)
    execution_a = _execution(tenant_a.id, agent_a, actor_a, "isolation-a")
    execution_b = _execution(tenant_b.id, agent_b, actor_b, "isolation-b")
    tool_a = _tool(tenant_a.id, "tenant-a.tool", actor_a)
    tool_b = _tool(tenant_b.id, "tenant-b.tool", actor_b)
    now = timezone.now()
    world = {
        "tenant_a": tenant_a.id,
        "tenant_b": tenant_b.id,
        "actor_a": actor_a,
        "actor_b": actor_b,
        "agent_a": agent_a,
        "agent_b": agent_b,
        "execution_a": execution_a,
        "execution_b": execution_b,
        "tool_a": tool_a,
        "tool_b": tool_b,
        "schedule_a": AgentSchedulerTask.objects.create(
            tenant_id=tenant_a.id,
            agent=agent_a,
            execution=execution_a,
            scheduled_at=now + timedelta(hours=1),
            created_by=actor_a,
            idempotency_key="schedule-a",
        ),
        "schedule_b": AgentSchedulerTask.objects.create(
            tenant_id=tenant_b.id,
            agent=agent_b,
            execution=execution_b,
            scheduled_at=now + timedelta(hours=1),
            created_by=actor_b,
            idempotency_key="schedule-b",
        ),
        "approval_a": ApprovalRequest.objects.create(
            tenant_id=tenant_a.id,
            tool=tool_a,
            agent_execution=execution_a,
            requested_by=actor_a,
            requested_for=uuid4(),
            tool_input={},
        ),
        "approval_b": ApprovalRequest.objects.create(
            tenant_id=tenant_b.id,
            tool=tool_b,
            agent_execution=execution_b,
            requested_by=actor_b,
            requested_for=uuid4(),
            tool_input={},
        ),
        "sod_a": SoDPolicy.objects.create(
            tenant_id=tenant_a.id,
            name="Tenant A separation",
            action_1="approve",
            action_2="release",
            created_by=actor_a,
        ),
        "sod_b": SoDPolicy.objects.create(
            tenant_id=tenant_b.id,
            name="Tenant B separation",
            action_1="approve",
            action_2="release",
            created_by=actor_b,
        ),
        "egress_a": EgressRule.objects.create(
            tenant_id=tenant_a.id,
            name="Tenant A API",
            destination_type="domain",
            destination="api.example.com",
            protocol="https",
            created_by=actor_a,
        ),
        "egress_b": EgressRule.objects.create(
            tenant_id=tenant_b.id,
            name="Tenant B API",
            destination_type="domain",
            destination="api.example.com",
            protocol="https",
            created_by=actor_b,
        ),
        "secret_a": Secret.objects.create(
            tenant_id=tenant_a.id,
            name="Tenant A secret",
            secret_type="token",
            ciphertext="ciphertext-a",
            wrapped_data_key="wrapped-a",
            key_id="key-a",
            created_by=actor_a,
        ),
        "secret_b": Secret.objects.create(
            tenant_id=tenant_b.id,
            name="Tenant B secret",
            secret_type="token",
            ciphertext="ciphertext-b",
            wrapped_data_key="wrapped-b",
            key_id="key-b",
            created_by=actor_b,
        ),
        "kill_a": KillSwitch.objects.create(
            tenant_id=tenant_a.id,
            name="Tenant A control",
            scope="agent",
            scope_id=agent_a.id,
            reason="test",
            activated_by=actor_a,
        ),
        "kill_b": KillSwitch.objects.create(
            tenant_id=tenant_b.id,
            name="Tenant B control",
            scope="agent",
            scope_id=agent_b.id,
            reason="test",
            activated_by=actor_b,
        ),
    }
    world.update(
        {
            "invocation_a": ToolInvocation.objects.create(
                tenant_id=tenant_a.id,
                tool=tool_a,
                agent_execution=execution_a,
                input_data={},
                idempotency_key="invocation-a",
            ),
            "invocation_b": ToolInvocation.objects.create(
                tenant_id=tenant_b.id,
                tool=tool_b,
                agent_execution=execution_b,
                input_data={},
                idempotency_key="invocation-b",
            ),
            "egress_request_a": EgressRequest.objects.create(
                tenant_id=tenant_a.id,
                agent_execution=execution_a,
                destination="blocked.example",
                port=443,
                protocol="https",
                allowed=False,
                reason_code="EGRESS_DENIED",
            ),
            "egress_request_b": EgressRequest.objects.create(
                tenant_id=tenant_b.id,
                agent_execution=execution_b,
                destination="blocked.example",
                port=443,
                protocol="https",
                allowed=False,
                reason_code="EGRESS_DENIED",
            ),
            "quota_usage_a": QuotaUsage.objects.create(
                tenant_id=tenant_a.id,
                agent_execution=execution_a,
                resource="ai.execution",
                usage_value=1,
                remaining_after=9,
            ),
            "quota_usage_b": QuotaUsage.objects.create(
                tenant_id=tenant_b.id,
                agent_execution=execution_b,
                resource="ai.execution",
                usage_value=1,
                remaining_after=9,
            ),
            "token_usage_a": TokenUsage.objects.create(
                tenant_id=tenant_a.id,
                agent_execution=execution_a,
                provider="test",
                model="reference",
                input_tokens=2,
                output_tokens=3,
                total_tokens=5,
            ),
            "token_usage_b": TokenUsage.objects.create(
                tenant_id=tenant_b.id,
                agent_execution=execution_b,
                provider="test",
                model="reference",
                input_tokens=2,
                output_tokens=3,
                total_tokens=5,
            ),
            "cost_a": CostRecord.objects.create(
                tenant_id=tenant_a.id,
                agent_execution=execution_a,
                cost_type="api_call",
                amount=Decimal("0.10000000"),
                currency="USD",
                pricing_version="test-v1",
            ),
            "cost_b": CostRecord.objects.create(
                tenant_id=tenant_b.id,
                agent_execution=execution_b,
                cost_type="api_call",
                amount=Decimal("0.10000000"),
                currency="USD",
                pricing_version="test-v1",
            ),
            "audit_a": AuditEvent.objects.create(
                tenant_id=tenant_a.id,
                event_type="agent_started",
                agent_execution=execution_a,
                initiating_principal=actor_a,
                subject_id=uuid4(),
                request_id=uuid4(),
                correlation_id=uuid4(),
                outcome="pending",
            ),
            "audit_b": AuditEvent.objects.create(
                tenant_id=tenant_b.id,
                event_type="agent_started",
                agent_execution=execution_b,
                initiating_principal=actor_b,
                subject_id=uuid4(),
                request_id=uuid4(),
                correlation_id=uuid4(),
                outcome="pending",
            ),
        }
    )
    return world


class GovernedIsolationContract(TenantIsolationContract):
    read_denial_statuses = frozenset({status.HTTP_404_NOT_FOUND})

    def get_list_items(self, response):
        payload = response.json()
        assert set(payload) == {"data", "meta"}
        data = payload["data"]
        return data.get("results", data) if isinstance(data, dict) else data


class UnsupportedGenericMutationMixin:
    """Resources with command-only mutation expose 405 on their own rows."""

    def test_cross_tenant_update_is_denied_and_unchanged(self):
        row = self.get_tenant_a_row()
        before = self._row_snapshot(row)
        response = self.get_client().patch(self.get_detail_url(row), self.get_update_payload(), format="json")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert self._row_snapshot(row) == before

    def test_cross_tenant_delete_is_denied_and_unchanged(self):
        row = self.get_tenant_a_row()
        before = self._row_snapshot(row)
        response = self.get_client().delete(self.get_detail_url(row))
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert self._row_snapshot(row) == before


@pytest.mark.django_db
class TestAgentIsolation(GovernedIsolationContract):
    model = Agent
    list_url = f"{BASE}/agents/"
    detail_url_template = f"{BASE}/agents/{{pk}}/"
    create_payload = {
        "name": "Spoof attempt",
        "identity_type": "system_bound",
        "subject_id": str(uuid4()),
        "runner_key": "isolation.runner",
        "config": {},
    }
    update_payload = {"name": "Cross tenant mutation"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, isolation_world):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = isolation_world["agent_a"]
        self.tenant_b_row = isolation_world["agent_b"]


@pytest.mark.django_db
class TestScheduleIsolation(UnsupportedGenericMutationMixin, GovernedIsolationContract):
    model = AgentSchedulerTask
    list_url = f"{BASE}/schedules/"
    detail_url_template = f"{BASE}/schedules/{{pk}}/"
    update_payload = {"priority": 99}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, isolation_world):
        self.client = authenticated_tenant_a_client
        self.world = isolation_world
        self.tenant_a_row = isolation_world["schedule_a"]
        self.tenant_b_row = isolation_world["schedule_b"]

    def get_create_payload(self):
        return {
            "agent_id": str(self.world["agent_a"].id),
            "scheduled_at": (timezone.now() + timedelta(hours=2)).isoformat(),
            "task_data": {},
            "idempotency_key": f"spoof-{uuid4()}",
        }


@pytest.mark.django_db
class TestApprovalIsolation(UnsupportedGenericMutationMixin, GovernedIsolationContract):
    model = ApprovalRequest
    list_url = f"{BASE}/approvals/"
    detail_url_template = f"{BASE}/approvals/{{pk}}/"
    update_payload = {"status": "approved"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, isolation_world):
        self.client = authenticated_tenant_a_client
        self.world = isolation_world
        self.tenant_a_row = isolation_world["approval_a"]
        self.tenant_b_row = isolation_world["approval_b"]

    def get_create_payload(self):
        return {
            "execution_id": str(self.world["execution_a"].id),
            "tool_id": str(self.world["tool_a"].id),
            "requested_for": str(uuid4()),
            "tool_input": {},
        }


@pytest.mark.django_db
def test_cross_tenant_foreign_keys_are_rejected_without_side_effects(
    authenticated_tenant_a_client,
    isolation_world,
):
    """Known tenant-B identifiers cannot be smuggled into tenant-A commands."""

    schedule_count = AgentSchedulerTask.objects.count()
    approval_count = ApprovalRequest.objects.count()
    job_count = AsyncJob.objects.count()
    outbox_count = OutboxEvent.objects.count()

    schedule_response = authenticated_tenant_a_client.post(
        f"{BASE}/schedules/",
        {
            "agent_id": str(isolation_world["agent_b"].id),
            "scheduled_at": (timezone.now() + timedelta(hours=2)).isoformat(),
            "task_data": {},
            "idempotency_key": f"foreign-agent-{uuid4()}",
        },
        format="json",
    )
    assert schedule_response.status_code == status.HTTP_404_NOT_FOUND

    approval_response = authenticated_tenant_a_client.post(
        f"{BASE}/approvals/",
        {
            "execution_id": str(isolation_world["execution_b"].id),
            "tool_id": str(isolation_world["tool_b"].id),
            "requested_for": str(uuid4()),
            "tool_input": {},
        },
        format="json",
    )
    assert approval_response.status_code == status.HTTP_404_NOT_FOUND
    assert AgentSchedulerTask.objects.count() == schedule_count
    assert ApprovalRequest.objects.count() == approval_count
    assert AsyncJob.objects.count() == job_count
    assert OutboxEvent.objects.count() == outbox_count


@pytest.mark.django_db
class TestSoDPolicyIsolation(GovernedIsolationContract):
    model = SoDPolicy
    list_url = f"{BASE}/sod-policies/"
    detail_url_template = f"{BASE}/sod-policies/{{pk}}/"
    create_payload = {"name": "Spoof", "action_1": "deploy", "action_2": "review"}
    update_payload = {"name": "Cross tenant mutation"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, isolation_world):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = isolation_world["sod_a"]
        self.tenant_b_row = isolation_world["sod_b"]


@pytest.mark.django_db
class TestToolIsolation(GovernedIsolationContract):
    model = Tool
    list_url = f"{BASE}/tools/"
    detail_url_template = f"{BASE}/tools/{{pk}}/"
    create_payload = {
        "name": "spoof.tool",
        "owning_module": "ai_agent_management",
        "version": "1.0.0",
        "required_permissions": ["ai.tool:invoke"],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "side_effect_class": "read_only",
    }
    update_payload = {"description": "Cross tenant mutation"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, isolation_world):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = isolation_world["tool_a"]
        self.tenant_b_row = isolation_world["tool_b"]


@pytest.mark.django_db
class TestEgressRuleIsolation(GovernedIsolationContract):
    model = EgressRule
    list_url = f"{BASE}/egress-rules/"
    detail_url_template = f"{BASE}/egress-rules/{{pk}}/"
    create_payload = {
        "name": "Spoof API",
        "destination_type": "domain",
        "destination": "public.example.com",
        "protocol": "https",
    }
    update_payload = {"description": "Cross tenant mutation"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, isolation_world):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = isolation_world["egress_a"]
        self.tenant_b_row = isolation_world["egress_b"]


@pytest.mark.django_db
class TestSecretIsolation(UnsupportedGenericMutationMixin, GovernedIsolationContract):
    model = Secret
    list_url = f"{BASE}/secrets/"
    detail_url_template = f"{BASE}/secrets/{{pk}}/"
    create_payload = {"name": "spoof-secret", "secret_type": "token", "plaintext": "not-a-real-secret"}
    update_payload = {"name": "Cross tenant mutation"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, isolation_world):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = isolation_world["secret_a"]
        self.tenant_b_row = isolation_world["secret_b"]


@pytest.mark.django_db
class TestKillSwitchIsolation(UnsupportedGenericMutationMixin, GovernedIsolationContract):
    model = KillSwitch
    list_url = f"{BASE}/kill-switches/"
    detail_url_template = f"{BASE}/kill-switches/{{pk}}/"
    create_payload = {"scope": "tenant", "reason": "spoof", "transition_key": "spoof"}
    update_payload = {"status": "inactive"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, isolation_world):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = isolation_world["kill_a"]
        self.tenant_b_row = isolation_world["kill_b"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("resource", "row_key"),
    (
        ("executions", "execution"),
        ("tool-invocations", "invocation"),
        ("egress-requests", "egress_request"),
        ("quota-usage", "quota_usage"),
        ("token-usage", "token_usage"),
        ("cost-records", "cost"),
        ("audit-events", "audit"),
    ),
)
def test_read_only_evidence_is_tenant_hidden_and_has_no_mutation_route(
    authenticated_tenant_a_client,
    isolation_world,
    resource,
    row_key,
):
    own = isolation_world[f"{row_key}_a"]
    foreign = isolation_world[f"{row_key}_b"]
    response = authenticated_tenant_a_client.get(f"{BASE}/{resource}/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    items = data.get("results", data) if isinstance(data, dict) else data
    identities = {item["id"] for item in items}
    assert str(own.pk) in identities
    assert str(foreign.pk) not in identities
    foreign_url = f"{BASE}/{resource}/{foreign.pk}/"
    assert authenticated_tenant_a_client.get(foreign_url).status_code == status.HTTP_404_NOT_FOUND
    own_url = f"{BASE}/{resource}/{own.pk}/"
    patch_response = authenticated_tenant_a_client.patch(own_url, {}, format="json")
    assert patch_response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    assert authenticated_tenant_a_client.delete(own_url).status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
def test_cross_tenant_custom_action_records_no_side_effects(authenticated_tenant_a_client, isolation_world):
    counts = {
        "jobs": AsyncJob.objects.count(),
        "outbox": OutboxEvent.objects.count(),
        "audit": AuditEvent.objects.count(),
        "usage": QuotaUsage.objects.count(),
    }
    actions = (
        ("agents", "agent_b", "activate", {"transition_key": "foreign-activate"}),
        ("agents", "agent_b", "disable", {"transition_key": "foreign-disable", "reason": "test"}),
        ("agents", "agent_b", "retire", {"transition_key": "foreign-retire", "reason": "test"}),
        ("agents", "agent_b", "execute", {"task": {}, "idempotency_key": "foreign-execute"}),
        ("agents", "agent_b", "evaluate", {"suite_key": "missing", "idempotency_key": "foreign-eval"}),
        (
            "executions",
            "execution_b",
            "pause",
            {"agent_id": str(isolation_world["agent_b"].id), "transition_key": "foreign-pause"},
        ),
        (
            "executions",
            "execution_b",
            "resume",
            {"agent_id": str(isolation_world["agent_b"].id), "transition_key": "foreign-resume"},
        ),
        (
            "executions",
            "execution_b",
            "terminate",
            {
                "agent_id": str(isolation_world["agent_b"].id),
                "transition_key": "foreign-stop",
                "reason": "test",
            },
        ),
        ("schedules", "schedule_b", "cancel", {"transition_key": "foreign-cancel"}),
        ("approvals", "approval_b", "approve", {"transition_key": "foreign-approve"}),
        ("approvals", "approval_b", "reject", {"transition_key": "foreign-reject", "reason": "test"}),
        ("approvals", "approval_b", "cancel", {"transition_key": "foreign-cancel"}),
        ("tools", "tool_b", "validate", {"direction": "input", "value": {}}),
        ("secrets", "secret_b", "rotate", {"plaintext": "foreign-secret"}),
        ("secrets", "secret_b", "deactivate", {}),
        ("kill-switches", "kill_b", "deactivate", {"transition_key": "foreign-off", "reason": "test"}),
    )
    for resource, row_key, action, payload in actions:
        row = isolation_world[row_key]
        response = authenticated_tenant_a_client.post(
            f"{BASE}/{resource}/{row.id}/{action}/",
            payload,
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND, (resource, action, response.json())
    assert AsyncJob.objects.count() == counts["jobs"]
    assert OutboxEvent.objects.count() == counts["outbox"]
    assert AuditEvent.objects.count() == counts["audit"]
    assert QuotaUsage.objects.count() == counts["usage"]
    isolation_world["agent_b"].refresh_from_db()
    assert isolation_world["agent_b"].transition_history == []
