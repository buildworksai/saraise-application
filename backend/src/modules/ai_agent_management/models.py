"""AI Agent Management Models.

Defines data models for agent lifecycle, execution, and scheduling.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid

from django.db import models


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class AgentLifecycleState(models.TextChoices):
    """Agent lifecycle states as defined in AI Agent Execution & Safety Spec."""

    CREATED = "created", "Created"
    VALIDATED = "validated", "Validated"
    RUNNING = "running", "Running"
    PAUSED = "paused", "Paused"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    TERMINATED = "terminated", "Terminated"


class AgentIdentityType(models.TextChoices):
    """Agent identity types."""

    USER_BOUND = "user_bound", "User-Bound Agent"
    SYSTEM_BOUND = "system_bound", "System-Bound Agent"


class TenantBaseModel(models.Model):
    """Base model for tenant-scoped models with Row-Level Multitenancy.

    CRITICAL: All tenant-scoped models MUST inherit from this base class
    and include tenant_id. All queries MUST filter explicitly by tenant_id.
    """

    tenant_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class Agent(TenantBaseModel):
    """Agent definition model.

    Represents an AI agent that can be executed. Agents are either user-bound
    (created from an active user session) or system-bound (execute under
    system identities).
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    identity_type = models.CharField(
        max_length=20,
        choices=AgentIdentityType.choices,
        db_index=True,
        help_text="User-bound or system-bound agent",
    )
    subject_id = models.CharField(
        max_length=36,
        db_index=True,
        help_text="User ID (for user-bound) or system role ID (for system-bound)",
    )
    session_id = models.CharField(
        max_length=36,
        null=True,
        blank=True,
        db_index=True,
        help_text="Session ID for user-bound agents (null for system-bound)",
    )
    framework = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Agent framework (langgraph, crewai, autogen, etc.)",
    )
    config = models.JSONField(
        default=dict,
        help_text="Agent configuration (framework-specific)",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        db_table = "ai_agents"
        indexes = [
            models.Index(fields=["tenant_id", "identity_type"]),
            models.Index(fields=["tenant_id", "subject_id"]),
            models.Index(fields=["tenant_id", "session_id"]),
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["tenant_id", "framework"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"


class AgentExecution(TenantBaseModel):
    """Agent execution instance model.

    Tracks individual agent execution runs. Each execution has a lifecycle
    state and is bound to a session (for user-bound agents).
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    agent = models.ForeignKey(
        Agent,
        on_delete=models.CASCADE,
        related_name="executions",
        db_index=True,
    )
    state = models.CharField(
        max_length=20,
        choices=AgentLifecycleState.choices,
        default=AgentLifecycleState.CREATED,
        db_index=True,
    )
    session_id = models.CharField(
        max_length=36,
        null=True,
        blank=True,
        db_index=True,
        help_text="Session ID for user-bound agents",
    )
    task_definition = models.JSONField(help_text="Task/goal definition for this execution")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    result = models.JSONField(default=dict, null=True, blank=True)
    metadata = models.JSONField(default=dict, help_text="Execution metadata")

    class Meta:
        db_table = "ai_agent_executions"
        indexes = [
            models.Index(fields=["tenant_id", "agent_id"]),
            models.Index(fields=["tenant_id", "state"]),
            models.Index(fields=["tenant_id", "session_id"]),
            models.Index(fields=["tenant_id", "started_at"]),
        ]

    def __str__(self) -> str:
        return f"Execution {self.id} ({self.state})"


class AgentSchedulerTask(TenantBaseModel):
    """Agent scheduler task model.

    Represents a scheduled task for agent execution. Used by the scheduler
    to manage task queue, priority, and retry logic.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    agent = models.ForeignKey(
        Agent,
        on_delete=models.CASCADE,
        related_name="scheduled_tasks",
        db_index=True,
    )
    execution = models.ForeignKey(
        AgentExecution,
        on_delete=models.CASCADE,
        related_name="scheduler_tasks",
        null=True,
        blank=True,
        db_index=True,
    )
    priority = models.IntegerField(default=0, db_index=True, help_text="Higher priority = execute first")
    scheduled_at = models.DateTimeField(db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("running", "Running"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ],
        default="pending",
        db_index=True,
    )
    error_message = models.TextField(blank=True)
    task_data = models.JSONField(default=dict)

    class Meta:
        db_table = "ai_agent_scheduler_tasks"
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "scheduled_at"]),
            models.Index(fields=["tenant_id", "priority", "scheduled_at"]),
        ]

    def __str__(self) -> str:
        return f"Task {self.id} ({self.status})"
