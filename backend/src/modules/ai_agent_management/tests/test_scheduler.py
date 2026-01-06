"""Tests for Agent Scheduler Service.

Task: 401.1 - Agent Runtime & Scheduler
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from datetime import timedelta

from ..models import Agent, AgentExecution, AgentSchedulerTask, AgentIdentityType
from ..scheduler import AgentScheduler, ScheduledTask


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
            task_definition={"goal": "task 1"},
            priority=1,
            status="pending",
        )

        # Create completed task (should not be returned)
        AgentSchedulerTask.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            task_definition={"goal": "task 2"},
            priority=1,
            status="completed",
        )

        pending = scheduler.get_pending_tasks(tenant_id=tenant_id)

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
            task_definition={"goal": "low priority"},
            priority=3,
            status="pending",
        )

        AgentSchedulerTask.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            task_definition={"goal": "high priority"},
            priority=1,
            status="pending",
        )

        pending = scheduler.get_pending_tasks(tenant_id=tenant_id, limit=10)

        # Should be ordered by priority (ascending)
        priorities = [t.priority for t in pending if t.status == "pending"]
        assert priorities == sorted(priorities)

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
            task_definition={"goal": "test task"},
            priority=1,
            status="pending",
        )

        scheduler.mark_task_running(task.id, tenant_id)

        task.refresh_from_db()
        assert task.status == "running"
        assert task.started_at is not None

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
            task_definition={"goal": "test task"},
            priority=1,
            status="running",
            started_at=timezone.now(),
        )

        scheduler.mark_task_completed(task.id, tenant_id, result={"status": "success"})

        task.refresh_from_db()
        assert task.status == "completed"
        assert task.completed_at is not None
        assert task.result == {"status": "success"}

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
            task_definition={"goal": "test task"},
            priority=1,
            status="running",
            started_at=timezone.now(),
            max_retries=3,
        )

        scheduler.mark_task_failed(task.id, tenant_id, error="Task failed")

        task.refresh_from_db()
        assert task.status == "failed"
        assert task.error_message == "Task failed"
        assert task.retry_count == 1

    def test_retry_task(self) -> None:
        """Test retrying a failed task."""
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
            task_definition={"goal": "test task"},
            priority=1,
            status="failed",
            retry_count=1,
            max_retries=3,
        )

        retried = scheduler.retry_task(task.id, tenant_id)

        assert retried is not None
        assert retried.status == "pending"
        assert retried.retry_count == 2

    def test_retry_task_max_retries_exceeded(self) -> None:
        """Test retrying task when max retries exceeded."""
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
            task_definition={"goal": "test task"},
            priority=1,
            status="failed",
            retry_count=3,
            max_retries=3,
        )

        retried = scheduler.retry_task(task.id, tenant_id)

        assert retried is None  # Should not retry

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
            task_definition={"goal": "test task"},
            priority=1,
            status="pending",
        )

        scheduler.cancel_task(task.id, tenant_id)

        task.refresh_from_db()
        assert task.status == "cancelled"
        assert task.completed_at is not None

