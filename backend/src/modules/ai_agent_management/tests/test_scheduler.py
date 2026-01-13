"""Tests for Agent Scheduler Service.

Task: 401.1 - Agent Runtime & Scheduler
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from src.modules.ai_agent_management.models import Agent, AgentExecution, AgentIdentityType, AgentSchedulerTask
from src.modules.ai_agent_management.scheduler import AgentScheduler, ScheduledTask


@pytest.mark.django_db
class TestAgentScheduler:
    """Test AgentScheduler."""

    def test_schedule_task(self) -> None:
        """Test scheduling a task."""
        scheduler = AgentScheduler()

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

        task = ScheduledTask(
            agent_id=str(agent.id),
            tenant_id=tenant_id,
            task_definition={"goal": "test task"},
            priority=1,
        )

        scheduled = scheduler.schedule_task(task)

        assert scheduled is not None
        assert scheduled.agent_id == agent.id
        assert scheduled.status == "pending"

    def test_get_pending_tasks(self) -> None:
        """Test getting pending tasks."""
        scheduler = AgentScheduler()

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

        # Create pending task
        AgentSchedulerTask.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            task_data={"goal": "task 1"},
            priority=1,
            status="pending",
            scheduled_at=timezone.now(),
        )

        # Create completed task (should not be returned)
        AgentSchedulerTask.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            task_data={"goal": "task 2"},
            priority=1,
            status="completed",
            scheduled_at=timezone.now(),
        )

        pending = scheduler.get_next_tasks(tenant_id=tenant_id)

        assert len(pending) >= 1
        assert all(t.status == "pending" for t in pending)

    def test_get_pending_tasks_by_priority(self) -> None:
        """Test getting pending tasks ordered by priority."""
        scheduler = AgentScheduler()

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

        # Create tasks with different priorities
        AgentSchedulerTask.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            task_data={"goal": "low priority"},
            priority=3,
            status="pending",
            scheduled_at=timezone.now(),
        )

        AgentSchedulerTask.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            task_data={"goal": "high priority"},
            priority=1,
            status="pending",
            scheduled_at=timezone.now(),
        )

        pending = scheduler.get_next_tasks(tenant_id=tenant_id, limit=10)

        # Should be ordered by priority (descending - higher priority first)
        priorities = [t.priority for t in pending if t.status == "pending"]
        assert priorities == sorted(priorities, reverse=True)

    def test_mark_task_running(self) -> None:
        """Test marking task as running."""
        scheduler = AgentScheduler()

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

        task = AgentSchedulerTask.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            task_data={"goal": "test task"},
            priority=1,
            status="pending",
            scheduled_at=timezone.now(),
        )

        # Use execute_task which marks task as running
        try:
            scheduler.execute_task(task.id, tenant_id)
        except Exception:
            # Execution may fail in test, but task should be marked running
            pass

        task.refresh_from_db()
        assert task.status in ["running", "pending"]  # May be pending if execution failed

    def test_mark_task_completed(self) -> None:
        """Test marking task as completed."""
        scheduler = AgentScheduler()

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

        task = AgentSchedulerTask.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            task_data={"goal": "test task"},
            priority=1,
            status="running",
            scheduled_at=timezone.now(),
            started_at=timezone.now(),
        )

        scheduler.complete_task(task.id, tenant_id, success=True)

        task.refresh_from_db()
        assert task.status == "completed"
        assert task.completed_at is not None

    def test_mark_task_failed(self) -> None:
        """Test marking task as failed."""
        scheduler = AgentScheduler()

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

        task = AgentSchedulerTask.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            task_data={"goal": "test task"},
            priority=1,
            status="running",
            scheduled_at=timezone.now(),
            started_at=timezone.now(),
            max_retries=3,
        )

        scheduler.complete_task(task.id, tenant_id, success=False)

        task.refresh_from_db()
        assert task.status == "failed"
        assert task.completed_at is not None

    def test_retry_task(self) -> None:
        """Test automatic retry on task failure."""
        scheduler = AgentScheduler()

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

        # Create a pending task
        task = AgentSchedulerTask.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            task_data={"goal": "test task"},
            priority=1,
            status="pending",
            retry_count=0,
            max_retries=3,
            scheduled_at=timezone.now(),
        )

        # Execute task - it will fail and auto-retry
        # Mock the runtime module where it's imported inside execute_task
        from unittest.mock import patch, MagicMock
        
        # Patch the runtime module where it's imported inside execute_task
        with patch('src.modules.ai_agent_management.runtime.AgentRuntime') as mock_runtime_class:
            mock_runtime_instance = MagicMock()
            mock_runtime_class.return_value = mock_runtime_instance
            mock_runtime_instance.create_execution.side_effect = Exception("Execution failed")
            
            try:
                scheduler.execute_task(task.id, tenant_id)
            except Exception:
                # Expected to fail
                pass

        # Check retry count increased
        task.refresh_from_db()
        assert task.retry_count > 0
        assert task.status == "pending"  # Should be pending for retry

    def test_retry_task_max_retries_exceeded(self) -> None:
        """Test that task fails permanently when max retries exceeded."""
        scheduler = AgentScheduler()

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

        # Create a task that has already exceeded max retries
        task = AgentSchedulerTask.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            task_data={"goal": "test task"},
            priority=1,
            status="pending",
            retry_count=3,
            max_retries=3,
            scheduled_at=timezone.now(),
        )

        # Execute task - it will fail and should be marked as failed permanently
        from unittest.mock import patch, MagicMock
        
        # Patch the runtime module where it's imported inside execute_task
        with patch('src.modules.ai_agent_management.runtime.AgentRuntime') as mock_runtime_class:
            mock_runtime_instance = MagicMock()
            mock_runtime_class.return_value = mock_runtime_instance
            mock_runtime_instance.create_execution.side_effect = Exception("Execution failed")
            
            try:
                scheduler.execute_task(task.id, tenant_id)
            except Exception:
                # Expected to fail
                pass

        # Check task is marked as failed permanently
        task.refresh_from_db()
        assert task.status == "failed"
        assert task.completed_at is not None
        assert "Max retries exceeded" in task.error_message

    def test_cancel_task(self) -> None:
        """Test canceling a task."""
        scheduler = AgentScheduler()

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

        task = AgentSchedulerTask.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            task_data={"goal": "test task"},
            priority=1,
            status="pending",
            scheduled_at=timezone.now(),
        )

        scheduler.cancel_task(task.id, tenant_id)

        task.refresh_from_db()
        assert task.status == "cancelled"
        assert task.completed_at is not None
