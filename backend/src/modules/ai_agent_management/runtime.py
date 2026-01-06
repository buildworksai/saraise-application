"""Agent Runtime Service.

Implements agent runtime execution lifecycle and session-binding semantics.
Task: 401.1 - Agent Runtime & Scheduler
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from django.utils import timezone
from django.db import transaction

from .models import (
    Agent,
    AgentExecution,
    AgentLifecycleState,
    AgentIdentityType,
    AgentSchedulerTask,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentExecutionContext:
    """Context for agent execution."""

    agent_id: str
    tenant_id: str
    subject_id: str
    session_id: Optional[str]
    identity_type: str
    task_definition: Dict[str, Any]
    metadata: Dict[str, Any]


class AgentRuntime:
    """Agent runtime service for managing agent execution lifecycle.

    Implements:
    - Agent execution lifecycle management
    - Session-binding semantics (user-bound vs system-bound)
    - Agent state persistence
    - Agent execution isolation
    """

    def __init__(self) -> None:
        """Initialize agent runtime."""
        self._active_executions: Dict[str, AgentExecution] = {}

    def create_execution(
        self, context: AgentExecutionContext
    ) -> AgentExecution:
        """Create a new agent execution.

        Args:
            context: Agent execution context.

        Returns:
            Created AgentExecution instance.

        Raises:
            ValueError: If agent not found or validation fails.
        """
        # Validate agent exists
        agent = Agent.objects.filter(
            id=context.agent_id, tenant_id=context.tenant_id
        ).first()

        if not agent:
            raise ValueError(f"Agent {context.agent_id} not found")

        # Validate identity type matches
        if agent.identity_type != context.identity_type:
            raise ValueError(
                f"Identity type mismatch: agent={agent.identity_type}, "
                f"context={context.identity_type}"
            )

        # Validate session binding for user-bound agents
        if context.identity_type == AgentIdentityType.USER_BOUND:
            if not context.session_id:
                raise ValueError(
                    "User-bound agents require session_id"
                )
            # TODO: Validate session is active (Task 401.3)

        # Create execution
        execution = AgentExecution.objects.create(
            tenant_id=context.tenant_id,
            agent=agent,
            state=AgentLifecycleState.CREATED,
            session_id=context.session_id,
            task_definition=context.task_definition,
            metadata=context.metadata,
        )

        logger.info(
            f"Created agent execution {execution.id} for agent {agent.id}"
        )

        return execution

    def validate_execution(
        self, execution_id: str, tenant_id: str
    ) -> AgentExecution:
        """Validate agent execution before starting.

        Args:
            execution_id: Execution ID.
            tenant_id: Tenant ID.

        Returns:
            Validated AgentExecution instance.

        Raises:
            ValueError: If validation fails.
        """
        execution = AgentExecution.objects.filter(
            id=execution_id, tenant_id=tenant_id
        ).first()

        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.state != AgentLifecycleState.CREATED:
            raise ValueError(
                f"Execution {execution_id} is not in CREATED state"
            )

        # Validate session binding for user-bound agents
        if execution.agent.identity_type == AgentIdentityType.USER_BOUND:
            if not execution.session_id:
                raise ValueError(
                    "User-bound agent execution missing session_id"
                )
            # TODO: Validate session is still active (Task 401.3)

        # Update state to validated
        execution.state = AgentLifecycleState.VALIDATED
        execution.save(update_fields=["state", "updated_at"])

        logger.info(f"Validated agent execution {execution.id}")

        return execution

    def start_execution(
        self, execution_id: str, tenant_id: str
    ) -> AgentExecution:
        """Start agent execution.

        Args:
            execution_id: Execution ID.
            tenant_id: Tenant ID.

        Returns:
            Started AgentExecution instance.

        Raises:
            ValueError: If execution cannot be started.
        """
        execution = AgentExecution.objects.filter(
            id=execution_id, tenant_id=tenant_id
        ).first()

        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.state not in [
            AgentLifecycleState.CREATED,
            AgentLifecycleState.VALIDATED,
            AgentLifecycleState.PAUSED,
        ]:
            raise ValueError(
                f"Execution {execution_id} cannot be started from state "
                f"{execution.state}"
            )

        # Validate session binding for user-bound agents
        if execution.agent.identity_type == AgentIdentityType.USER_BOUND:
            if not execution.session_id:
                raise ValueError(
                    "User-bound agent execution missing session_id"
                )
            # TODO: Validate session is still active (Task 401.3)

        # Update state to running
        execution.state = AgentLifecycleState.RUNNING
        execution.started_at = timezone.now()
        execution.save(update_fields=["state", "started_at", "updated_at"])

        # Track active execution
        self._active_executions[execution.id] = execution

        logger.info(f"Started agent execution {execution.id}")

        return execution

    def pause_execution(
        self, execution_id: str, tenant_id: str
    ) -> AgentExecution:
        """Pause agent execution.

        Args:
            execution_id: Execution ID.
            tenant_id: Tenant ID.

        Returns:
            Paused AgentExecution instance.

        Raises:
            ValueError: If execution cannot be paused.
        """
        execution = AgentExecution.objects.filter(
            id=execution_id, tenant_id=tenant_id
        ).first()

        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.state != AgentLifecycleState.RUNNING:
            raise ValueError(
                f"Execution {execution_id} cannot be paused from state "
                f"{execution.state}"
            )

        # Update state to paused
        execution.state = AgentLifecycleState.PAUSED
        execution.save(update_fields=["state", "updated_at"])

        # Remove from active executions
        if execution.id in self._active_executions:
            del self._active_executions[execution.id]

        logger.info(f"Paused agent execution {execution.id}")

        return execution

    def resume_execution(
        self, execution_id: str, tenant_id: str
    ) -> AgentExecution:
        """Resume paused agent execution.

        Args:
            execution_id: Execution ID.
            tenant_id: Tenant ID.

        Returns:
            Resumed AgentExecution instance.

        Raises:
            ValueError: If execution cannot be resumed.
        """
        execution = AgentExecution.objects.filter(
            id=execution_id, tenant_id=tenant_id
        ).first()

        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.state != AgentLifecycleState.PAUSED:
            raise ValueError(
                f"Execution {execution_id} cannot be resumed from state "
                f"{execution.state}"
            )

        # Validate session binding for user-bound agents
        if execution.agent.identity_type == AgentIdentityType.USER_BOUND:
            if not execution.session_id:
                raise ValueError(
                    "User-bound agent execution missing session_id"
                )
            # TODO: Validate session is still active (Task 401.3)

        # Update state to running
        execution.state = AgentLifecycleState.RUNNING
        execution.save(update_fields=["state", "updated_at"])

        # Track active execution
        self._active_executions[execution.id] = execution

        logger.info(f"Resumed agent execution {execution.id}")

        return execution

    def complete_execution(
        self,
        execution_id: str,
        tenant_id: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> AgentExecution:
        """Complete agent execution.

        Args:
            execution_id: Execution ID.
            tenant_id: Tenant ID.
            result: Execution result.

        Returns:
            Completed AgentExecution instance.

        Raises:
            ValueError: If execution cannot be completed.
        """
        execution = AgentExecution.objects.filter(
            id=execution_id, tenant_id=tenant_id
        ).first()

        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.state != AgentLifecycleState.RUNNING:
            raise ValueError(
                f"Execution {execution_id} cannot be completed from state "
                f"{execution.state}"
            )

        # Update state to completed
        execution.state = AgentLifecycleState.COMPLETED
        execution.completed_at = timezone.now()
        if result:
            execution.result = result
        execution.save(
            update_fields=["state", "completed_at", "result", "updated_at"]
        )

        # Remove from active executions
        if execution.id in self._active_executions:
            del self._active_executions[execution.id]

        logger.info(f"Completed agent execution {execution.id}")

        return execution

    def fail_execution(
        self,
        execution_id: str,
        tenant_id: str,
        error_message: str,
    ) -> AgentExecution:
        """Fail agent execution.

        Args:
            execution_id: Execution ID.
            tenant_id: Tenant ID.
            error_message: Error message.

        Returns:
            Failed AgentExecution instance.

        Raises:
            ValueError: If execution cannot be failed.
        """
        execution = AgentExecution.objects.filter(
            id=execution_id, tenant_id=tenant_id
        ).first()

        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        # Update state to failed
        execution.state = AgentLifecycleState.FAILED
        execution.completed_at = timezone.now()
        execution.error_message = error_message
        execution.save(
            update_fields=[
                "state",
                "completed_at",
                "error_message",
                "updated_at",
            ]
        )

        # Remove from active executions
        if execution.id in self._active_executions:
            del self._active_executions[execution.id]

        logger.info(f"Failed agent execution {execution.id}: {error_message}")

        return execution

    def terminate_execution(
        self, execution_id: str, tenant_id: str
    ) -> AgentExecution:
        """Terminate agent execution (kill switch).

        Args:
            execution_id: Execution ID.
            tenant_id: Tenant ID.

        Returns:
            Terminated AgentExecution instance.

        Raises:
            ValueError: If execution cannot be terminated.
        """
        execution = AgentExecution.objects.filter(
            id=execution_id, tenant_id=tenant_id
        ).first()

        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        # Can terminate from any state except already terminated/completed
        if execution.state in [
            AgentLifecycleState.TERMINATED,
            AgentLifecycleState.COMPLETED,
        ]:
            raise ValueError(
                f"Execution {execution_id} already in terminal state"
            )

        # Update state to terminated
        execution.state = AgentLifecycleState.TERMINATED
        execution.completed_at = timezone.now()
        execution.save(
            update_fields=["state", "completed_at", "updated_at"]
        )

        # Remove from active executions
        if execution.id in self._active_executions:
            del self._active_executions[execution.id]

        logger.info(f"Terminated agent execution {execution.id}")

        return execution

    def check_session_validity(
        self, execution_id: str, tenant_id: str
    ) -> bool:
        """Check if session is still valid for user-bound agent execution.

        Args:
            execution_id: Execution ID.
            tenant_id: Tenant ID.

        Returns:
            True if session is valid, False otherwise.
        """
        execution = AgentExecution.objects.filter(
            id=execution_id, tenant_id=tenant_id
        ).first()

        if not execution:
            return False

        # System-bound agents don't have sessions
        if execution.agent.identity_type == AgentIdentityType.SYSTEM_BOUND:
            return True

        # User-bound agents require valid session
        if not execution.session_id:
            return False

        # TODO: Validate session is active (Task 401.3)
        # For now, return True if session_id exists
        return True

    def terminate_expired_sessions(self, tenant_id: str) -> int:
        """Terminate all agent executions with expired sessions.

        Args:
            tenant_id: Tenant ID.

        Returns:
            Number of terminated executions.
        """
        # Get all running user-bound executions
        executions = AgentExecution.objects.filter(
            tenant_id=tenant_id,
            agent__identity_type=AgentIdentityType.USER_BOUND,
            state=AgentLifecycleState.RUNNING,
        )

        terminated_count = 0
        for execution in executions:
            if not self.check_session_validity(execution.id, tenant_id):
                self.terminate_execution(execution.id, tenant_id)
                terminated_count += 1

        logger.info(
            f"Terminated {terminated_count} executions with expired sessions"
        )

        return terminated_count


# Global runtime instance
agent_runtime = AgentRuntime()

