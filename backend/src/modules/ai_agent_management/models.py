"""Tenant-safe persistence for governed AI agents and executions.

The string-returning ``generate_uuid`` function is intentionally retained: the
immutable 0001 migration imports it. Runtime models use native UUID columns.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from src.core.tenancy import TenantScopedModel, TimestampedModel
from src.core.tenancy.registry import TENANT_SCOPED, tenancy_scope


def generate_uuid() -> str:
    """Preserve the callable referenced by the historical migration."""

    return str(uuid.uuid4())


def _json_type(value: object, expected: type, field: str) -> None:
    if not isinstance(value, expected):
        raise ValidationError({field: f"Must be a JSON {expected.__name__}."})


def validate_same_tenant(instance: models.Model, *relations: str) -> None:
    """Reject ORM-level cross-tenant references before database triggers run."""

    tenant_id = getattr(instance, "tenant_id", None)
    if tenant_id is None:
        return
    for relation in relations:
        related_id = getattr(instance, f"{relation}_id", None)
        if related_id is None:
            continue
        field = instance._meta.get_field(relation)
        related_model = field.remote_field.model
        if not related_model._base_manager.filter(pk=related_id, tenant_id=tenant_id).exists():
            raise ValidationError(
                {relation: "The referenced record was not found in this tenant."},
                code="cross_tenant_reference",
            )


class AITenantModel(TenantScopedModel, TimestampedModel):
    """Canonical identity and timestamps for mutable module aggregates."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class GovernedStateQuerySet(models.QuerySet[models.Model]):
    """Lifecycle writes must hold a row lock and append transition evidence."""

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ValidationError("Lifecycle records must be changed through their service.", code="state_machine")


class GovernedStateManager(models.Manager.from_queryset(GovernedStateQuerySet)):  # type: ignore[misc]
    pass


class StatefulTenantModel(AITenantModel):
    """Allow state transitions until terminal, then make the row immutable."""

    state_field = "state"
    terminal_states: frozenset[str] = frozenset()
    objects = GovernedStateManager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding and self.pk:
            prior = (
                type(self)
                ._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id)
                .values(self.state_field, "transition_history")
                .first()
            )
            if prior:
                old_state = prior[self.state_field]
                new_state = getattr(self, self.state_field)
                if old_state in self.terminal_states:
                    raise ValidationError("Terminal lifecycle records are immutable.", code="terminal_immutable")
                if old_state != new_state and prior["transition_history"] == self.transition_history:
                    raise ValidationError("State changes require transition evidence.", code="state_machine")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Lifecycle records cannot be deleted.", code="evidence_protected")


class AppendOnlyQuerySet(models.QuerySet[models.Model]):
    """Prevent bulk APIs from bypassing evidence immutability."""

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ValidationError("Evidence records are append-only.", code="append_only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Evidence records are append-only.", code="append_only")


class AppendOnlyManager(models.Manager.from_queryset(AppendOnlyQuerySet)):  # type: ignore[misc]
    pass


class AppendOnlyTenantModel(TenantScopedModel):
    """Canonical base for immutable evidence records."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    objects = AppendOnlyManager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Evidence records are append-only.", code="append_only")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Evidence records are append-only.", code="append_only")


class AgentIdentityType(models.TextChoices):
    USER_BOUND = "user_bound", "User-bound"
    SYSTEM_BOUND = "system_bound", "System-bound"


class AgentStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    DISABLED = "disabled", "Disabled"
    RETIRED = "retired", "Retired"


class AgentLifecycleState(models.TextChoices):
    """Compatibility name for the execution state enumeration."""

    CREATED = "created", "Created"
    VALIDATED = "validated", "Validated"
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    PAUSED = "paused", "Paused"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    TERMINATED = "terminated", "Terminated"
    TIMED_OUT = "timed_out", "Timed out"


ExecutionState = AgentLifecycleState


class ScheduleStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


@tenancy_scope(TENANT_SCOPED)
class Agent(StatefulTenantModel):
    """A tenant-owned versioned agent definition."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    identity_type = models.CharField(max_length=20, choices=AgentIdentityType.choices)
    subject_id = models.UUIDField()
    session_id = models.UUIDField(null=True, blank=True)
    runner_key = models.CharField(max_length=100)
    provider_config_id = models.UUIDField(null=True, blank=True)
    config = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=AgentStatus.choices, default=AgentStatus.DRAFT)
    transition_history = models.JSONField(default=list, blank=True, editable=False)
    created_by = models.UUIDField()
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)

    state_field = "status"
    terminal_states = frozenset((AgentStatus.RETIRED,))

    class Meta:
        db_table = "ai_agents"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "name"),
                condition=~Q(status=AgentStatus.RETIRED),
                name="ai_agent_live_name_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(identity_type=AgentIdentityType.USER_BOUND, session_id__isnull=False)
                    | Q(identity_type=AgentIdentityType.SYSTEM_BOUND, session_id__isnull=True)
                ),
                name="ai_agent_identity_session_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status=AgentStatus.ACTIVE) | ~Q(runner_key=""),
                name="ai_agent_active_runner_ck",
            ),
            models.CheckConstraint(
                condition=(Q(status=AgentStatus.RETIRED, deleted_at__isnull=False) | ~Q(status=AgentStatus.RETIRED)),
                name="ai_agent_retired_deleted_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "name"), name="ai_agent_t_status_name_idx"),
            models.Index(fields=("tenant_id", "identity_type", "subject_id"), name="ai_agent_t_identity_idx"),
            models.Index(fields=("tenant_id", "runner_key"), name="ai_agent_t_runner_idx"),
            models.Index(fields=("tenant_id", "created_at"), name="ai_agent_t_created_idx"),
        ]
        ordering = ("name", "id")

    def clean(self) -> None:
        _json_type(self.config, dict, "config")
        _json_type(self.transition_history, list, "transition_history")
        if self.identity_type == AgentIdentityType.USER_BOUND and self.session_id is None:
            raise ValidationError({"session_id": "A user-bound agent requires a session."})
        if self.identity_type == AgentIdentityType.SYSTEM_BOUND and self.session_id is not None:
            raise ValidationError({"session_id": "A system-bound agent cannot retain a user session."})
        if self.status == AgentStatus.RETIRED and self.deleted_at is None:
            raise ValidationError({"deleted_at": "A retired agent requires a retirement timestamp."})
        if self.status != AgentStatus.RETIRED and self.deleted_at is not None:
            raise ValidationError({"deleted_at": "Only retired agents may have deleted_at set."})

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        if self.status != AgentStatus.RETIRED:
            now = timezone.now()
            self.status = AgentStatus.RETIRED
            self.deleted_at = now
            self.transition_history = [
                *self.transition_history,
                {"transition": "retire", "at": now.isoformat(), "source": "model_delete"},
            ]
            self.save(update_fields=["status", "deleted_at", "transition_history", "updated_at"])
        return 1, {self._meta.label: 1}

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"


@tenancy_scope(TENANT_SCOPED)
class AgentExecution(StatefulTenantModel):
    """Immutable-at-terminal evidence for one governed execution."""

    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="executions")
    async_job_id = models.UUIDField(unique=True)
    state = models.CharField(max_length=20, choices=ExecutionState.choices, default=ExecutionState.CREATED)
    transition_history = models.JSONField(default=list, blank=True, editable=False)
    initiating_actor_id = models.UUIDField()
    session_id = models.UUIDField(null=True, blank=True)
    task_definition = models.JSONField(default=dict, blank=True)
    input_metadata = models.JSONField(default=dict, blank=True)
    result = models.JSONField(null=True, blank=True)
    error_code = models.CharField(max_length=100, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255)
    provider_config_id = models.UUIDField(null=True, blank=True)

    terminal_states = frozenset(
        (ExecutionState.COMPLETED, ExecutionState.FAILED, ExecutionState.TERMINATED, ExecutionState.TIMED_OUT)
    )

    class Meta:
        db_table = "ai_agent_executions"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="ai_exec_t_idem_uniq"),
            models.CheckConstraint(
                condition=(
                    Q(
                        state__in=(
                            ExecutionState.COMPLETED,
                            ExecutionState.FAILED,
                            ExecutionState.TERMINATED,
                            ExecutionState.TIMED_OUT,
                        ),
                        completed_at__isnull=False,
                    )
                    | (
                        ~Q(
                            state__in=(
                                ExecutionState.COMPLETED,
                                ExecutionState.FAILED,
                                ExecutionState.TERMINATED,
                                ExecutionState.TIMED_OUT,
                            )
                        )
                        & Q(completed_at__isnull=True)
                    )
                ),
                name="ai_exec_terminal_time_ck",
            ),
            models.CheckConstraint(
                condition=~Q(state=ExecutionState.COMPLETED) | Q(result__isnull=False),
                name="ai_exec_success_result_ck",
            ),
            models.CheckConstraint(
                condition=~Q(state__in=(ExecutionState.FAILED, ExecutionState.TIMED_OUT)) | ~Q(error_code=""),
                name="ai_exec_failure_code_ck",
            ),
            models.CheckConstraint(
                condition=Q(started_at__isnull=True)
                | Q(completed_at__isnull=True)
                | Q(completed_at__gte=F("started_at")),
                name="ai_exec_time_order_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "agent", "state", "created_at"), name="ai_exec_t_agent_state_idx"),
            models.Index(fields=("tenant_id", "state", "created_at"), name="ai_exec_t_state_created_idx"),
            models.Index(fields=("tenant_id", "async_job_id"), name="ai_exec_t_job_idx"),
            models.Index(fields=("tenant_id", "session_id"), name="ai_exec_t_session_idx"),
        ]
        ordering = ("-created_at", "id")

    def clean(self) -> None:
        validate_same_tenant(self, "agent")
        _json_type(self.task_definition, dict, "task_definition")
        _json_type(self.input_metadata, dict, "input_metadata")
        _json_type(self.transition_history, list, "transition_history")

    def __str__(self) -> str:
        return f"Execution {self.id} ({self.state})"


@tenancy_scope(TENANT_SCOPED)
class AgentSchedulerTask(StatefulTenantModel):
    """Scheduling projection linked to the canonical async-job authority."""

    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="scheduled_tasks")
    execution = models.ForeignKey(
        AgentExecution,
        on_delete=models.PROTECT,
        related_name="scheduler_tasks",
        null=True,
        blank=True,
    )
    async_job_id = models.UUIDField(unique=True, null=True, blank=True)
    scheduled_at = models.DateTimeField()
    priority = models.SmallIntegerField(default=0)
    max_retries = models.PositiveSmallIntegerField(default=3)
    retry_count = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=ScheduleStatus.choices, default=ScheduleStatus.PENDING)
    transition_history = models.JSONField(default=list, blank=True, editable=False)
    task_data = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=100, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.UUIDField()
    idempotency_key = models.CharField(max_length=255)

    state_field = "status"
    terminal_states = frozenset((ScheduleStatus.COMPLETED, ScheduleStatus.FAILED, ScheduleStatus.CANCELLED))

    class Meta:
        db_table = "ai_agent_scheduler_tasks"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="ai_sched_t_idem_uniq"),
            models.CheckConstraint(condition=Q(priority__gte=-100, priority__lte=100), name="ai_sched_priority_ck"),
            models.CheckConstraint(condition=Q(retry_count__lte=F("max_retries")), name="ai_sched_retry_ck"),
            models.CheckConstraint(
                condition=Q(started_at__isnull=True)
                | Q(completed_at__isnull=True)
                | Q(completed_at__gte=F("started_at")),
                name="ai_sched_time_order_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "scheduled_at", "priority"), name="ai_sched_t_due_idx"),
            models.Index(fields=("tenant_id", "agent", "created_at"), name="ai_sched_t_agent_idx"),
        ]
        ordering = ("scheduled_at", "-priority", "id")

    def clean(self) -> None:
        validate_same_tenant(self, "agent", "execution")
        if self.execution_id and self.execution.agent_id != self.agent_id:
            raise ValidationError({"execution": "The execution must belong to the scheduled agent."})
        _json_type(self.task_data, dict, "task_data")
        _json_type(self.transition_history, list, "transition_history")

    def __str__(self) -> str:
        return f"Schedule {self.id} ({self.status})"


# Django imports only ``models`` during app discovery. Import the split domain
# files here so every model is registered even when URL configuration is not
# loaded (management commands and migration tests rely on this).
from .approval_models import ApprovalRequest, ApprovalStatus, SoDPolicy, SoDViolation  # noqa: E402
from .audit_models import AuditEvent, AuditEventType, AuditTrail, AuditTrailEvent  # noqa: E402
from .egress_models import EgressRequest, EgressRule, Secret, SecretAccess  # noqa: E402
from .quota_models import KillSwitch, QuotaUsage, ShardSaturation  # noqa: E402
from .token_models import CostRecord, CostSummary, TokenUsage  # noqa: E402
from .tool_models import Tool, ToolInvocation  # noqa: E402

__all__ = [
    "Agent",
    "AgentExecution",
    "AgentIdentityType",
    "AgentLifecycleState",
    "AgentSchedulerTask",
    "AgentStatus",
    "ApprovalRequest",
    "ApprovalStatus",
    "AuditEvent",
    "AuditEventType",
    "AuditTrail",
    "AuditTrailEvent",
    "CostRecord",
    "CostSummary",
    "EgressRequest",
    "EgressRule",
    "ExecutionState",
    "KillSwitch",
    "QuotaUsage",
    "ScheduleStatus",
    "Secret",
    "SecretAccess",
    "ShardSaturation",
    "SoDPolicy",
    "SoDViolation",
    "TokenUsage",
    "Tool",
    "ToolInvocation",
]
