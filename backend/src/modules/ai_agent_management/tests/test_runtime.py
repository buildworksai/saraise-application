"""Tests for Agent Runtime Service.

Task: 401.1 - Agent Runtime & Scheduler
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from datetime import datetime

from ..models import (
    Agent,
    AgentExecution,
    AgentLifecycleState,
    AgentIdentityType,
)
from ..runtime import AgentRuntime, AgentExecutionContext


@pytest.mark.django_db
class TestAgentRuntime:
    """Test agent runtime service."""

    def test_create_execution_user_bound(self) -> None:
        """Test creating user-bound agent execution."""
        tenant_id = "test-tenant-1"
        agent = Agent.objects.create(
            tenant_id=tenant_id,
            name="Test Agent",
            description="Test agent",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id="user-1",
            session_id="session-1",
            framework="langgraph",
            config={},
            created_by="user-1",
        )

        runtime = AgentRuntime()
        context = AgentExecutionContext(
            agent_id=agent.id,
            tenant_id=tenant_id,
            subject_id="user-1",
            session_id="session-1",
            identity_type=AgentIdentityType.USER_BOUND,
            task_definition={"goal": "test task"},
            metadata={},
        )

        execution = runtime.create_execution(context)

        assert execution is not None
        assert execution.agent_id == agent.id
        assert execution.tenant_id == tenant_id
        assert execution.state == AgentLifecycleState.CREATED
        assert execution.session_id == "session-1"

    def test_create_execution_system_bound(self) -> None:
        """Test creating system-bound agent execution."""
        tenant_id = "test-tenant-1"
        agent = Agent.objects.create(
            tenant_id=tenant_id,
            name="Test Agent",
            description="Test agent",
            identity_type=AgentIdentityType.SYSTEM_BOUND,
            subject_id="system-role-1",
            session_id=None,
            framework="langgraph",
            config={},
            created_by="user-1",
        )

        runtime = AgentRuntime()
        context = AgentExecutionContext(
            agent_id=agent.id,
            tenant_id=tenant_id,
            subject_id="system-role-1",
            session_id=None,
            identity_type=AgentIdentityType.SYSTEM_BOUND,
            task_definition={"goal": "test task"},
            metadata={},
        )

        execution = runtime.create_execution(context)

        assert execution is not None
        assert execution.agent_id == agent.id
        assert execution.tenant_id == tenant_id
        assert execution.state == AgentLifecycleState.CREATED
        assert execution.session_id is None

    def test_create_execution_missing_session(self) -> None:
        """Test creating user-bound execution without session fails."""
        tenant_id = "test-tenant-1"
        agent = Agent.objects.create(
            tenant_id=tenant_id,
            name="Test Agent",
            description="Test agent",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id="user-1",
            session_id="session-1",
            framework="langgraph",
            config={},
            created_by="user-1",
        )

        runtime = AgentRuntime()
        context = AgentExecutionContext(
            agent_id=agent.id,
            tenant_id=tenant_id,
            subject_id="user-1",
            session_id=None,  # Missing session
            identity_type=AgentIdentityType.USER_BOUND,
            task_definition={"goal": "test task"},
            metadata={},
        )

        with pytest.raises(ValueError, match="User-bound agents require session_id"):
            runtime.create_execution(context)

    def test_lifecycle_transitions(self) -> None:
        """Test agent execution lifecycle transitions."""
        tenant_id = "test-tenant-1"
        agent = Agent.objects.create(
            tenant_id=tenant_id,
            name="Test Agent",
            description="Test agent",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id="user-1",
            session_id="session-1",
            framework="langgraph",
            config={},
            created_by="user-1",
        )

        runtime = AgentRuntime()
        context = AgentExecutionContext(
            agent_id=agent.id,
            tenant_id=tenant_id,
            subject_id="user-1",
            session_id="session-1",
            identity_type=AgentIdentityType.USER_BOUND,
            task_definition={"goal": "test task"},
            metadata={},
        )

        # Create
        execution = runtime.create_execution(context)
        assert execution.state == AgentLifecycleState.CREATED

        # Validate
        execution = runtime.validate_execution(execution.id, tenant_id)
        assert execution.state == AgentLifecycleState.VALIDATED

        # Start
        execution = runtime.start_execution(execution.id, tenant_id)
        assert execution.state == AgentLifecycleState.RUNNING
        assert execution.started_at is not None

        # Pause
        execution = runtime.pause_execution(execution.id, tenant_id)
        assert execution.state == AgentLifecycleState.PAUSED

        # Resume
        execution = runtime.resume_execution(execution.id, tenant_id)
        assert execution.state == AgentLifecycleState.RUNNING

        # Complete
        execution = runtime.complete_execution(
            execution.id, tenant_id, result={"status": "success"}
        )
        assert execution.state == AgentLifecycleState.COMPLETED
        assert execution.completed_at is not None
        assert execution.result == {"status": "success"}

    def test_terminate_execution(self) -> None:
        """Test terminating agent execution."""
        tenant_id = "test-tenant-1"
        agent = Agent.objects.create(
            tenant_id=tenant_id,
            name="Test Agent",
            description="Test agent",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id="user-1",
            session_id="session-1",
            framework="langgraph",
            config={},
            created_by="user-1",
        )

        runtime = AgentRuntime()
        context = AgentExecutionContext(
            agent_id=agent.id,
            tenant_id=tenant_id,
            subject_id="user-1",
            session_id="session-1",
            identity_type=AgentIdentityType.USER_BOUND,
            task_definition={"goal": "test task"},
            metadata={},
        )

        execution = runtime.create_execution(context)
        execution = runtime.validate_execution(execution.id, tenant_id)
        execution = runtime.start_execution(execution.id, tenant_id)

        # Terminate
        execution = runtime.terminate_execution(execution.id, tenant_id)
        assert execution.state == AgentLifecycleState.TERMINATED
        assert execution.completed_at is not None

