"""Agent Scheduler Service.

Implements task queue, priority, and retry logic for agent execution.
Task: 401.1 - Agent Runtime & Scheduler
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from .models import (
    Agent,
    AgentExecution,
    AgentSchedulerTask,
    AgentLifecycleState,
)

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTask:
    """Scheduled task data."""

    agent_id: str
    tenant_id: str
    task_definition: Dict[str, Any]
    priority: int = 0
    scheduled_at: Optional[datetime] = None
    max_retries: int = 3
    metadata: Optional[Dict[str, Any]] = None


class AgentScheduler:
    """Agent scheduler service for managing task queue and execution.

    Implements:
    - Task queue management
    - Priority-based scheduling
    - Retry logic
    - Task execution coordination
    """

    def __init__(self) -> None:
        """Initialize agent scheduler."""
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None

    def schedule_task(self, task: ScheduledTask) -> AgentSchedulerTask:
        """Schedule an agent execution task.

        Args:
            task: Scheduled task data.

        Returns:
            Created AgentSchedulerTask instance.

        Raises:
            ValueError: If agent not found or validation fails.
        """
        # Validate agent exists
        agent = Agent.objects.filter(
            id=task.agent_id, tenant_id=task.tenant_id
        ).first()

        if not agent:
            raise ValueError(f"Agent {task.agent_id} not found")

        # Default scheduled_at to now if not provided
        scheduled_at = task.scheduled_at or timezone.now()

        # Create scheduler task
        scheduler_task = AgentSchedulerTask.objects.create(
            tenant_id=task.tenant_id,
            agent=agent,
            priority=task.priority,
            scheduled_at=scheduled_at,
            max_retries=task.max_retries,
            task_data={
                "task_definition": task.task_definition,
                "metadata": task.metadata or {},
            },
            status="pending",
        )

        logger.info(
            f"Scheduled task {scheduler_task.id} for agent {agent.id} "
            f"at {scheduled_at}"
        )

        return scheduler_task

    def get_next_tasks(
        self, tenant_id: Optional[str] = None, limit: int = 10
    ) -> List[AgentSchedulerTask]:
        """Get next tasks to execute (priority-based).

        Args:
            tenant_id: Optional tenant ID filter.
            limit: Maximum number of tasks to return.

        Returns:
            List of scheduled tasks ordered by priority and scheduled_at.
        """
        query = AgentSchedulerTask.objects.filter(
            status="pending", scheduled_at__lte=timezone.now()
        )

        if tenant_id:
            query = query.filter(tenant_id=tenant_id)

        tasks = (
            query.order_by("-priority", "scheduled_at")
            .select_related("agent")
            .prefetch_related("execution")[:limit]
        )

        return list(tasks)

    def execute_task(
        self, task_id: str, tenant_id: str
    ) -> AgentExecution:
        """Execute a scheduled task.

        Args:
            task_id: Task ID.
            tenant_id: Tenant ID.

        Returns:
            Created AgentExecution instance.

        Raises:
            ValueError: If task not found or cannot be executed.
        """
        task = AgentSchedulerTask.objects.filter(
            id=task_id, tenant_id=tenant_id
        ).first()

        if not task:
            raise ValueError(f"Task {task_id} not found")

        if task.status != "pending":
            raise ValueError(f"Task {task_id} is not pending")

        # Update task status to running
        task.status = "running"
        task.started_at = timezone.now()
        task.save(update_fields=["status", "started_at", "updated_at"])

        try:
            # Create execution from task
            from .runtime import AgentRuntime, AgentExecutionContext

            runtime = AgentRuntime()

            # Extract task data
            task_definition = task.task_data.get("task_definition", {})
            metadata = task.task_data.get("metadata", {})

            # Create execution context
            context = AgentExecutionContext(
                agent_id=task.agent.id,
                tenant_id=task.tenant_id,
                subject_id=task.agent.subject_id,
                session_id=task.agent.session_id,
                identity_type=task.agent.identity_type,
                task_definition=task_definition,
                metadata=metadata,
            )

            # Create and start execution
            execution = runtime.create_execution(context)
            execution = runtime.validate_execution(execution.id, task.tenant_id)
            execution = runtime.start_execution(execution.id, task.tenant_id)

            # Link execution to task
            task.execution = execution
            task.save(update_fields=["execution", "updated_at"])

            logger.info(
                f"Executed task {task.id}, created execution {execution.id}"
            )

            return execution

        except Exception as e:
            # Handle execution failure
            logger.error(f"Failed to execute task {task.id}: {e}")

            # Check if we should retry
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = "pending"
                task.scheduled_at = timezone.now() + timedelta(
                    seconds=60 * task.retry_count
                )  # Exponential backoff
                task.error_message = str(e)
                task.save(
                    update_fields=[
                        "retry_count",
                        "status",
                        "scheduled_at",
                        "error_message",
                        "updated_at",
                    ]
                )
                logger.info(
                    f"Scheduled retry {task.retry_count}/{task.max_retries} "
                    f"for task {task.id}"
                )
            else:
                # Max retries exceeded
                task.status = "failed"
                task.completed_at = timezone.now()
                task.error_message = f"Max retries exceeded: {e}"
                task.save(
                    update_fields=[
                        "status",
                        "completed_at",
                        "error_message",
                        "updated_at",
                    ]
                )
                logger.error(
                    f"Task {task.id} failed after {task.max_retries} retries"
                )

            raise

    def complete_task(
        self, task_id: str, tenant_id: str, success: bool = True
    ) -> AgentSchedulerTask:
        """Mark a task as completed.

        Args:
            task_id: Task ID.
            tenant_id: Tenant ID.
            success: Whether task completed successfully.

        Returns:
            Updated AgentSchedulerTask instance.

        Raises:
            ValueError: If task not found.
        """
        task = AgentSchedulerTask.objects.filter(
            id=task_id, tenant_id=tenant_id
        ).first()

        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = "completed" if success else "failed"
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed_at", "updated_at"])

        logger.info(f"Completed task {task.id} (success={success})")

        return task

    def cancel_task(self, task_id: str, tenant_id: str) -> AgentSchedulerTask:
        """Cancel a scheduled task.

        Args:
            task_id: Task ID.
            tenant_id: Tenant ID.

        Returns:
            Cancelled AgentSchedulerTask instance.

        Raises:
            ValueError: If task not found or cannot be cancelled.
        """
        task = AgentSchedulerTask.objects.filter(
            id=task_id, tenant_id=tenant_id
        ).first()

        if not task:
            raise ValueError(f"Task {task_id} not found")

        if task.status not in ["pending", "running"]:
            raise ValueError(f"Task {task_id} cannot be cancelled")

        task.status = "cancelled"
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed_at", "updated_at"])

        # If execution is running, terminate it
        if task.execution:
            from .runtime import AgentRuntime

            runtime = AgentRuntime()
            try:
                runtime.terminate_execution(
                    task.execution.id, task.tenant_id
                )
            except Exception as e:
                logger.warning(
                    f"Failed to terminate execution for task {task.id}: {e}"
                )

        logger.info(f"Cancelled task {task.id}")

        return task

    async def worker_loop(self) -> None:
        """Worker loop for processing scheduled tasks."""
        logger.info("Agent scheduler worker started")

        while self._running:
            try:
                # Get next tasks
                tasks = self.get_next_tasks(limit=10)

                for task in tasks:
                    try:
                        self.execute_task(task.id, task.tenant_id)
                    except Exception as e:
                        logger.error(
                            f"Error executing task {task.id}: {e}",
                            exc_info=True,
                        )

                # Sleep before next iteration
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Error in scheduler worker loop: {e}", exc_info=True)
                await asyncio.sleep(10)

        logger.info("Agent scheduler worker stopped")

    def start(self) -> None:
        """Start the scheduler worker."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        self._worker_task = asyncio.create_task(self.worker_loop())
        logger.info("Agent scheduler started")

    def stop(self) -> None:
        """Stop the scheduler worker."""
        if not self._running:
            return

        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
        logger.info("Agent scheduler stopped")


# Global scheduler instance
agent_scheduler = AgentScheduler()

