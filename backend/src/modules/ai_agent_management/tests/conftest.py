"""Production-faithful fixtures for the governed AI runtime.

The module tests intentionally use native UUID tenant/actor identities and real
database records.  API tests opt into ``src.core.testing.factories`` so session
authentication and CSRF are exercised instead of ``force_authenticate``.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.core.encryption.service import EncryptionService
from src.modules.ai_agent_management.models import Agent, AgentExecution
from src.modules.ai_agent_management.registries import evaluation_registry, runner_registry
from src.modules.ai_agent_management.tool_models import Tool

pytest_plugins = ["src.core.testing.factories"]


@pytest.fixture(autouse=True)
def configured_runtime(settings, monkeypatch):
    """Use real Fernet encryption and deterministic fail-closed settings."""

    monkeypatch.delenv("SARAISE_ENCRYPTION_KEYS", raising=False)
    monkeypatch.delenv("SARAISE_ENCRYPTION_KEY", raising=False)
    settings.SARAISE_MODE = "development"
    settings.SARAISE_ENCRYPTION_KEYS = None
    settings.SARAISE_ENCRYPTION_KEY = EncryptionService.rotate_key()
    settings.SARAISE_ENCRYPTION_KEY_ID = "test-kek-v1"
    EncryptionService._fernet = None
    EncryptionService._cached_keys = None
    yield
    EncryptionService._fernet = None
    EncryptionService._cached_keys = None


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def other_tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def actor_id() -> UUID:
    return uuid4()


@pytest.fixture
def approver_id() -> UUID:
    return uuid4()


@pytest.fixture
def agent(tenant_id: UUID, actor_id: UUID) -> Agent:
    return Agent.objects.create(
        tenant_id=tenant_id,
        name="Governed test agent",
        description="A deterministic test aggregate",
        identity_type="system_bound",
        subject_id=uuid4(),
        runner_key="test.runner",
        config={},
        created_by=actor_id,
    )


@pytest.fixture
def active_agent(agent: Agent) -> Agent:
    agent.status = "active"
    agent.transition_history = [
        {
            "transition_key": "fixture:activate",
            "command": "activate",
            "from_state": "draft",
            "to_state": "active",
        }
    ]
    agent.save(update_fields=("status", "transition_history", "updated_at"))
    return agent


@pytest.fixture
def execution(tenant_id: UUID, actor_id: UUID, agent: Agent) -> AgentExecution:
    return AgentExecution.objects.create(
        tenant_id=tenant_id,
        agent=agent,
        async_job_id=uuid4(),
        initiating_actor_id=actor_id,
        task_definition={"kind": "test"},
        input_metadata={},
        idempotency_key=f"test:{uuid4()}",
    )


@pytest.fixture
def tool(tenant_id: UUID, actor_id: UUID) -> Tool:
    return Tool.objects.create(
        tenant_id=tenant_id,
        name="test.tool",
        owning_module="ai_agent_management",
        version="1.0.0",
        required_permissions=["ai.tool:invoke"],
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        side_effect_class="data_mutation",
        registered_by=actor_id,
    )


@pytest.fixture
def registered_runner():
    def runner(**kwargs):
        return {"status": "completed", "execution_id": kwargs["execution_id"]}

    runner_registry.unregister("test.runner")
    runner_registry.register("test.runner", runner)
    yield runner
    runner_registry.unregister("test.runner")


@pytest.fixture
def registered_evaluation_suite():
    def suite(**kwargs):
        return {
            "status": "passed",
            "metrics": [{"name": "determinism", "value": 1.0}],
            "job_id": kwargs["job_id"],
            "agent_id": kwargs["agent_id"],
        }

    evaluation_registry.unregister("test.suite")
    evaluation_registry.register("test.suite", suite)
    yield suite
    evaluation_registry.unregister("test.suite")
