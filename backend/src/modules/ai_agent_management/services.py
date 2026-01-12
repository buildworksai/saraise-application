"""AI Agent Management Services.

High-level service layer for agent lifecycle management.
Task: 401.1 - Agent Runtime & Scheduler
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from .models import Agent, AgentExecution, AgentIdentityType, AgentLifecycleState, AgentSchedulerTask
from .runtime import AgentExecutionContext, AgentRuntime
from .scheduler import AgentScheduler, ScheduledTask

logger = logging.getLogger(__name__)


class AgentService:
    """Service for managing agent lifecycle."""

    def __init__(self) -> None:
        """Initialize agent service."""
        self.runtime = AgentRuntime()
        self.scheduler = AgentScheduler()

    def create_agent(
        self,
        tenant_id: str,
        name: str,
        description: str,
        identity_type: str,
        subject_id: str,
        session_id: Optional[str],
        framework: str,
        config: Dict[str, Any],
        created_by: str,
    ) -> Agent:
        """Create a new agent.

        Args:
            tenant_id: Tenant ID.
            name: Agent name.
            description: Agent description.
            identity_type: Identity type (user_bound or system_bound).
            subject_id: User ID or system role ID.
            session_id: Session ID (for user-bound agents).
            framework: Agent framework.
            config: Agent configuration.
            created_by: User ID who created the agent.

        Returns:
            Created Agent instance.

        Raises:
            ValueError: If validation fails.
        """
        # Validate identity type
        if identity_type not in [choice[0] for choice in AgentIdentityType.choices]:
            raise ValueError(f"Invalid identity_type: {identity_type}")

        # Validate session_id for user-bound agents
        if identity_type == AgentIdentityType.USER_BOUND and not session_id:
            raise ValueError("User-bound agents require session_id")

        # Create agent
        agent = Agent.objects.create(
            tenant_id=tenant_id,
            name=name,
            description=description,
            identity_type=identity_type,
            subject_id=subject_id,
            session_id=session_id,
            framework=framework,
            config=config,
            created_by=created_by,
        )

        logger.info(f"Created agent {agent.id} for tenant {tenant_id}")

        return agent

    def create_execution(
        self,
        agent_id: str,
        tenant_id: str,
        task_definition: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        schedule: bool = False,
        priority: int = 0,
        scheduled_at: Optional[datetime] = None,
    ) -> AgentExecution:
        """Create and optionally start an agent execution.

        Args:
            agent_id: Agent ID.
            tenant_id: Tenant ID.
            task_definition: Task/goal definition.
            metadata: Optional metadata.
            schedule: Whether to schedule execution (vs immediate).
            priority: Task priority (for scheduled tasks).
            scheduled_at: Scheduled execution time (for scheduled tasks).

        Returns:
            Created AgentExecution instance.

        Raises:
            ValueError: If agent not found or validation fails.
        """
        # Get agent
        agent = Agent.objects.filter(id=agent_id, tenant_id=tenant_id).first()

        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if not agent.is_active:
            raise ValueError(f"Agent {agent_id} is not active")

        if schedule:
            # Schedule execution
            task = ScheduledTask(
                agent_id=agent_id,
                tenant_id=tenant_id,
                task_definition=task_definition,
                priority=priority,
                scheduled_at=scheduled_at,
                metadata=metadata,
            )
            scheduler_task = self.scheduler.schedule_task(task)

            # Create execution linked to scheduler task
            context = AgentExecutionContext(
                agent_id=agent_id,
                tenant_id=tenant_id,
                subject_id=agent.subject_id,
                session_id=agent.session_id,
                identity_type=agent.identity_type,
                task_definition=task_definition,
                metadata=metadata or {},
            )
            execution = self.runtime.create_execution(context)

            # Link execution to scheduler task
            scheduler_task.execution = execution
            scheduler_task.save(update_fields=["execution", "updated_at"])

            logger.info(f"Scheduled execution {execution.id} for agent {agent_id}")

            return execution

        else:
            # Immediate execution
            context = AgentExecutionContext(
                agent_id=agent_id,
                tenant_id=tenant_id,
                subject_id=agent.subject_id,
                session_id=agent.session_id,
                identity_type=agent.identity_type,
                task_definition=task_definition,
                metadata=metadata or {},
            )

            execution = self.runtime.create_execution(context)
            execution = self.runtime.validate_execution(execution.id, tenant_id)
            execution = self.runtime.start_execution(execution.id, tenant_id)

            logger.info(f"Started immediate execution {execution.id} for agent {agent_id}")

            return execution

    def pause_execution(self, execution_id: str, tenant_id: str) -> AgentExecution:
        """Pause an agent execution.

        Args:
            execution_id: Execution ID.
            tenant_id: Tenant ID.

        Returns:
            Paused AgentExecution instance.
        """
        return self.runtime.pause_execution(execution_id, tenant_id)

    def resume_execution(self, execution_id: str, tenant_id: str) -> AgentExecution:
        """Resume a paused agent execution.

        Args:
            execution_id: Execution ID.
            tenant_id: Tenant ID.

        Returns:
            Resumed AgentExecution instance.
        """
        return self.runtime.resume_execution(execution_id, tenant_id)

    def terminate_execution(self, execution_id: str, tenant_id: str) -> AgentExecution:
        """Terminate an agent execution (kill switch).

        Args:
            execution_id: Execution ID.
            tenant_id: Tenant ID.

        Returns:
            Terminated AgentExecution instance.
        """
        return self.runtime.terminate_execution(execution_id, tenant_id)

    def get_execution(self, execution_id: str, tenant_id: str) -> Optional[AgentExecution]:
        """Get an agent execution.

        Args:
            execution_id: Execution ID.
            tenant_id: Tenant ID.

        Returns:
            AgentExecution instance or None if not found.
        """
        return AgentExecution.objects.filter(id=execution_id, tenant_id=tenant_id).first()

    def list_executions(
        self,
        tenant_id: str,
        agent_id: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 100,
    ) -> List[AgentExecution]:
        """List agent executions.

        Args:
            tenant_id: Tenant ID.
            agent_id: Optional agent ID filter.
            state: Optional state filter.
            limit: Maximum number of executions to return.

        Returns:
            List of AgentExecution instances.
        """
        query = AgentExecution.objects.filter(tenant_id=tenant_id)

        if agent_id:
            query = query.filter(agent_id=agent_id)

        if state:
            query = query.filter(state=state)

        return list(query.order_by("-created_at")[:limit])


# Global service instance
agent_service = AgentService()
