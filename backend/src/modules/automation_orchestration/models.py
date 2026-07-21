"""Durable, tenant-safe persistence for technical DAG orchestration.

The ORM intentionally models exact definition versions and append-only execution
evidence.  Services remain the command authority, while these model guards stop
accidental cross-tenant relationships, illegal lifecycle rewinds, hard deletes,
and mutation of terminal history even when a caller bypasses a serializer.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.db import models

from src.core.tenancy.models import TenantQuerySet, TenantScopedModel, TimestampedModel


# Kept only because immutable migration 0001 imports this callable.  There is no
# runtime model or API for the legacy generic resource.
def generate_uuid() -> str:
    """Return a string UUID for the historical migration state only."""
    return str(uuid.uuid4())


class DefinitionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    RETIRED = "retired", "Retired"


class NodeType(models.TextChoices):
    INTERNAL = "internal", "Internal"
    WORKFLOW = "workflow", "Workflow"
    EXTENSION = "extension", "Extension"


class EdgeCondition(models.TextChoices):
    ON_SUCCESS = "on_success", "On success"
    ON_FAILURE = "on_failure", "On failure"
    ALWAYS = "always", "Always"


class ScheduleStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    RETIRED = "retired", "Retired"


class MisfirePolicy(models.TextChoices):
    SKIP = "skip", "Skip"
    RUN_ONCE = "run_once", "Run once"


class ConcurrencyPolicy(models.TextChoices):
    ALLOW = "allow", "Allow"
    FORBID = "forbid", "Forbid"


class RunTriggerType(models.TextChoices):
    MANUAL = "manual", "Manual"
    SCHEDULE = "schedule", "Schedule"
    WORKFLOW = "workflow", "Workflow"
    EVENT = "event", "Event"


class RunStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    PAUSED = "paused", "Paused"
    CANCELLING = "cancelling", "Cancelling"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class TaskRunStatus(models.TextChoices):
    BLOCKED = "blocked", "Blocked"
    READY = "ready", "Ready"
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    RETRY_WAIT = "retry_wait", "Retry wait"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"
    CANCELLED = "cancelled", "Cancelled"


class AttemptStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    TIMED_OUT = "timed_out", "Timed out"
    CANCELLED = "cancelled", "Cancelled"


class SoftDeleteOnlyMixin:
    """Disallow an ORM hard delete for configuration records."""

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Hard deletion is forbidden; use the tenant-scoped service soft-delete command.")


class DurableHistoryMixin:
    """Reject deletion and mutation after an execution record is terminal."""

    TERMINAL_STATUSES: ClassVar[frozenset[str]] = frozenset()
    ALLOWED_TRANSITIONS: ClassVar[dict[str, frozenset[str]]] = {}

    def _stored_values(self) -> dict[str, Any] | None:
        if self._state.adding or self.pk is None:  # type: ignore[attr-defined]
            return None
        field_names = [
            field.attname
            for field in self._meta.concrete_fields  # type: ignore[attr-defined]
            if field.attname != "updated_at"
        ]
        return type(self).objects.filter(pk=self.pk).values(*field_names).first()  # type: ignore[attr-defined]

    def _validate_lifecycle(self) -> None:
        stored = self._stored_values()
        if stored is None:
            return
        old_status = str(stored["status"])
        new_status = str(self.status)  # type: ignore[attr-defined]
        changed = {name for name, value in stored.items() if name != "updated_at" and value != getattr(self, name)}
        if old_status in self.TERMINAL_STATUSES and changed:
            raise ValidationError({"status": f"Terminal {type(self).__name__} records are immutable."})
        if new_status != old_status and new_status not in self.ALLOWED_TRANSITIONS.get(old_status, frozenset()):
            raise ValidationError({"status": f"Illegal transition from {old_status!r} to {new_status!r}."})

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError(f"{type(self).__name__} history cannot be deleted.")


class DurableHistoryQuerySet(TenantQuerySet):
    """Keep bulk ORM operations from bypassing durable history guarantees."""

    def update(self, **kwargs: Any) -> int:
        terminal_statuses = getattr(self.model, "TERMINAL_STATUSES", frozenset())
        if terminal_statuses and self.filter(status__in=terminal_statuses).exists():
            raise ValidationError(f"Terminal {self.model.__name__} records are immutable.")
        return super().update(**kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError(f"{self.model.__name__} history cannot be deleted.")


def _validate_soft_delete(instance: Any) -> None:
    if instance.is_deleted and instance.deleted_at is None:
        raise ValidationError({"deleted_at": "A soft-deleted record requires deleted_at."})
    if not instance.is_deleted and instance.deleted_at is not None:
        raise ValidationError({"is_deleted": "deleted_at is only valid for a soft-deleted record."})


def _validate_related_tenant(instance: Any, relation_name: str, *, definition_id: uuid.UUID | None = None) -> None:
    relation_id = getattr(instance, f"{relation_name}_id", None)
    if relation_id is None:
        return
    field = instance._meta.get_field(relation_name)
    related_model = field.remote_field.model
    matches = related_model.objects.for_tenant(instance.tenant_id).filter(pk=relation_id)
    if definition_id is not None:
        matches = matches.filter(definition_id=definition_id)
    if not matches.exists():
        raise ValidationError({relation_name: "The related record must belong to the same tenant and definition."})


class OrchestrationDefinition(SoftDeleteOnlyMixin, TenantScopedModel, TimestampedModel):
    """One immutable version of a logical orchestration DAG."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.SlugField(max_length=100)
    version = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=DefinitionStatus.choices, default=DefinitionStatus.DRAFT)
    is_current = models.BooleanField(default=False)
    graph_revision = models.PositiveIntegerField(default=1)
    max_parallel_tasks = models.PositiveSmallIntegerField(default=10)
    default_timeout_seconds = models.PositiveIntegerField(default=300)
    default_max_attempts = models.PositiveSmallIntegerField(default=3)
    input_schema = models.JSONField(default=dict, blank=True)
    output_schema = models.JSONField(default=dict, blank=True)
    output_mapping = models.JSONField(default=dict, blank=True)
    labels = models.JSONField(default=dict, blank=True)
    contract_snapshot = models.JSONField(default=dict, blank=True)
    transition_history = models.JSONField(default=list, blank=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.UUIDField()
    updated_by = models.UUIDField()

    class Meta:
        db_table = "automation_orchestration_definitions"
        ordering = ("key", "-version")
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "key", "version"), name="ao_def_tenant_key_ver_uniq"),
            models.UniqueConstraint(
                fields=("tenant_id", "key"),
                condition=models.Q(is_current=True, is_deleted=False),
                name="ao_def_current_key_uniq",
            ),
            models.CheckConstraint(condition=models.Q(version__gte=1), name="ao_def_version_gte_1"),
            models.CheckConstraint(condition=models.Q(graph_revision__gte=1), name="ao_def_graph_rev_gte_1"),
            models.CheckConstraint(
                condition=models.Q(max_parallel_tasks__gte=1, max_parallel_tasks__lte=100),
                name="ao_def_parallel_1_100",
            ),
            models.CheckConstraint(
                condition=models.Q(default_timeout_seconds__gte=1, default_timeout_seconds__lte=86400),
                name="ao_def_timeout_1_86400",
            ),
            models.CheckConstraint(
                condition=models.Q(default_max_attempts__gte=1, default_max_attempts__lte=20),
                name="ao_def_attempts_1_20",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "updated_at"), name="ao_def_tenant_status_upd_idx"),
            models.Index(fields=("tenant_id", "key", "version"), name="ao_def_tenant_key_ver_idx"),
            models.Index(fields=("tenant_id", "is_current", "is_deleted"), name="ao_def_current_deleted_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_soft_delete(self)
        if not isinstance(self.labels, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in self.labels.items()
        ):
            raise ValidationError({"labels": "Labels must contain only string keys and string values."})
        if self.is_deleted:
            if self.status not in {DefinitionStatus.DRAFT, DefinitionStatus.RETIRED}:
                raise ValidationError({"is_deleted": "Only draft or retired definitions can be soft-deleted."})
            if (
                not self._state.adding
                and self.schedules.filter(status=ScheduleStatus.ACTIVE, is_deleted=False).exists()
            ):
                raise ValidationError({"is_deleted": "A definition with an active schedule cannot be deleted."})

        if self._state.adding:
            return
        stored = type(self).objects.filter(pk=self.pk).values().first()
        if stored is None:
            return
        old_status = str(stored["status"])
        new_status = str(self.status)
        if (old_status, new_status) not in {
            (DefinitionStatus.DRAFT, DefinitionStatus.DRAFT),
            (DefinitionStatus.DRAFT, DefinitionStatus.PUBLISHED),
            (DefinitionStatus.PUBLISHED, DefinitionStatus.PUBLISHED),
            (DefinitionStatus.PUBLISHED, DefinitionStatus.RETIRED),
            (DefinitionStatus.RETIRED, DefinitionStatus.RETIRED),
        }:
            raise ValidationError({"status": f"Illegal transition from {old_status!r} to {new_status!r}."})
        if old_status in {DefinitionStatus.PUBLISHED, DefinitionStatus.RETIRED}:
            allowed = {"status", "is_current", "transition_history", "updated_by", "updated_at"}
            if old_status == DefinitionStatus.RETIRED:
                allowed.update({"is_deleted", "deleted_at"})
            changed = {
                field.attname
                for field in self._meta.concrete_fields
                if field.attname not in allowed and stored.get(field.attname) != getattr(self, field.attname)
            }
            if changed:
                raise ValidationError(
                    {
                        "status": (
                            "Published and retired definition contracts are immutable: "
                            f"{', '.join(sorted(changed))}."
                        )
                    }
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.key} v{self.version})"


class OrchestrationNode(SoftDeleteOnlyMixin, TenantScopedModel, TimestampedModel):
    """Executable node configuration bound to an exact definition version."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    definition = models.ForeignKey(OrchestrationDefinition, models.PROTECT, related_name="nodes")
    key = models.SlugField(max_length=100)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    node_type = models.CharField(max_length=24, choices=NodeType.choices)
    handler_key = models.CharField(max_length=150)
    config = models.JSONField(default=dict, blank=True)
    input_mapping = models.JSONField(default=dict, blank=True)
    timeout_seconds = models.PositiveIntegerField(null=True, blank=True)
    max_attempts = models.PositiveSmallIntegerField(null=True, blank=True)
    retry_initial_delay_seconds = models.PositiveIntegerField(default=5)
    retry_backoff_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("2.00"))
    retry_max_delay_seconds = models.PositiveIntegerField(default=300)
    priority = models.SmallIntegerField(default=0)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.UUIDField()
    updated_by = models.UUIDField()

    class Meta:
        db_table = "automation_orchestration_nodes"
        ordering = ("priority", "key")
        constraints = [
            models.UniqueConstraint(
                fields=("definition", "key"),
                condition=models.Q(is_deleted=False),
                name="ao_node_def_key_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(timeout_seconds__isnull=True)
                | models.Q(timeout_seconds__gte=1, timeout_seconds__lte=86400),
                name="ao_node_timeout_1_86400",
            ),
            models.CheckConstraint(
                condition=models.Q(max_attempts__isnull=True) | models.Q(max_attempts__gte=1, max_attempts__lte=20),
                name="ao_node_attempts_1_20",
            ),
            models.CheckConstraint(
                condition=models.Q(retry_backoff_multiplier__gte=Decimal("1.00"))
                & models.Q(retry_backoff_multiplier__lte=Decimal("10.00")),
                name="ao_node_backoff_1_10",
            ),
            models.CheckConstraint(
                condition=models.Q(retry_max_delay_seconds__gte=models.F("retry_initial_delay_seconds")),
                name="ao_node_retry_max_gte_initial",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "definition", "is_deleted"), name="ao_node_tenant_def_del_idx"),
            models.Index(fields=("tenant_id", "handler_key"), name="ao_node_tenant_handler_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_soft_delete(self)
        _validate_related_tenant(self, "definition")
        if self.definition_id and self.definition.status != DefinitionStatus.DRAFT:
            raise ValidationError({"definition": "Nodes may only be changed on a draft definition."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.definition.key}:{self.key}"


class OrchestrationEdge(SoftDeleteOnlyMixin, TenantScopedModel, TimestampedModel):
    """Directed dependency between two nodes in one definition."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    definition = models.ForeignKey(OrchestrationDefinition, models.PROTECT, related_name="edges")
    upstream_node = models.ForeignKey(OrchestrationNode, models.PROTECT, related_name="outgoing_edges")
    downstream_node = models.ForeignKey(OrchestrationNode, models.PROTECT, related_name="incoming_edges")
    condition = models.CharField(max_length=16, choices=EdgeCondition.choices, default=EdgeCondition.ON_SUCCESS)
    priority = models.SmallIntegerField(default=0)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.UUIDField()
    updated_by = models.UUIDField()

    class Meta:
        db_table = "automation_orchestration_edges"
        ordering = ("priority", "created_at")
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(upstream_node=models.F("downstream_node")), name="ao_edge_endpoints_differ"
            ),
            models.UniqueConstraint(
                fields=("definition", "upstream_node", "downstream_node", "condition"),
                condition=models.Q(is_deleted=False),
                name="ao_edge_path_condition_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "definition", "upstream_node"), name="ao_edge_tenant_def_up_idx"),
            models.Index(fields=("tenant_id", "definition", "downstream_node"), name="ao_edge_tenant_def_down_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_soft_delete(self)
        if self.upstream_node_id == self.downstream_node_id:
            raise ValidationError({"downstream_node": "An edge cannot depend on itself."})
        _validate_related_tenant(self, "definition")
        _validate_related_tenant(self, "upstream_node", definition_id=self.definition_id)
        _validate_related_tenant(self, "downstream_node", definition_id=self.definition_id)
        if self.definition_id and self.definition.status != DefinitionStatus.DRAFT:
            raise ValidationError({"definition": "Edges may only be changed on a draft definition."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class OrchestrationSchedule(SoftDeleteOnlyMixin, TenantScopedModel, TimestampedModel):
    """Durable schedule pinned to an exact published definition."""

    ALLOWED_TRANSITIONS: ClassVar[dict[str, frozenset[str]]] = {
        ScheduleStatus.ACTIVE: frozenset({ScheduleStatus.PAUSED, ScheduleStatus.RETIRED}),
        ScheduleStatus.PAUSED: frozenset({ScheduleStatus.ACTIVE, ScheduleStatus.RETIRED}),
        ScheduleStatus.RETIRED: frozenset(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    definition = models.ForeignKey(OrchestrationDefinition, models.PROTECT, related_name="schedules")
    name = models.CharField(max_length=255)
    cron_expression = models.CharField(max_length=100)
    timezone = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=ScheduleStatus.choices, default=ScheduleStatus.ACTIVE)
    misfire_policy = models.CharField(max_length=16, choices=MisfirePolicy.choices, default=MisfirePolicy.SKIP)
    concurrency_policy = models.CharField(
        max_length=16, choices=ConcurrencyPolicy.choices, default=ConcurrencyPolicy.FORBID
    )
    input = models.JSONField(default=dict, blank=True)
    next_run_at = models.DateTimeField(db_index=True)
    last_enqueued_at = models.DateTimeField(null=True, blank=True)
    transition_history = models.JSONField(default=list, blank=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.UUIDField()
    updated_by = models.UUIDField()

    class Meta:
        db_table = "automation_orchestration_schedules"
        ordering = ("next_run_at", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "name"),
                condition=models.Q(is_deleted=False),
                name="ao_schedule_tenant_name_uniq",
            )
        ]
        indexes = [
            models.Index(fields=("status", "next_run_at"), name="ao_schedule_due_idx"),
            models.Index(fields=("tenant_id", "status", "next_run_at"), name="ao_schedule_tenant_due_idx"),
            models.Index(fields=("tenant_id", "definition", "is_deleted"), name="ao_schedule_tenant_def_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_soft_delete(self)
        _validate_related_tenant(self, "definition")
        if self.definition_id and (self.definition.status != DefinitionStatus.PUBLISHED or self.definition.is_deleted):
            raise ValidationError({"definition": "Schedules require a published, non-deleted definition version."})
        if self.is_deleted and self.status == ScheduleStatus.ACTIVE:
            raise ValidationError({"is_deleted": "An active schedule must be paused or retired before deletion."})
        if not self._state.adding:
            old_status = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if (
                old_status
                and self.status != old_status
                and self.status not in self.ALLOWED_TRANSITIONS.get(old_status, frozenset())
            ):
                raise ValidationError({"status": f"Illegal transition from {old_status!r} to {self.status!r}."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class OrchestrationRun(DurableHistoryMixin, TenantScopedModel, TimestampedModel):
    """Durable execution of one exact definition version."""

    TERMINAL_STATUSES = frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED})
    ALLOWED_TRANSITIONS = {
        RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
        RunStatus.RUNNING: frozenset({RunStatus.PAUSED, RunStatus.CANCELLING, RunStatus.SUCCEEDED, RunStatus.FAILED}),
        RunStatus.PAUSED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLING, RunStatus.FAILED}),
        RunStatus.CANCELLING: frozenset({RunStatus.CANCELLED, RunStatus.FAILED}),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    definition = models.ForeignKey(OrchestrationDefinition, models.PROTECT, related_name="runs")
    schedule = models.ForeignKey(OrchestrationSchedule, models.PROTECT, null=True, blank=True, related_name="runs")
    parent_run = models.ForeignKey("self", models.SET_NULL, null=True, blank=True, related_name="retry_runs")
    trigger_type = models.CharField(max_length=16, choices=RunTriggerType.choices)
    status = models.CharField(max_length=20, choices=RunStatus.choices, default=RunStatus.QUEUED)
    input = models.JSONField(default=dict, blank=True)
    output = models.JSONField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255)
    correlation_id = models.CharField(max_length=64)
    requested_by = models.UUIDField()
    task_count = models.PositiveIntegerField(default=0)
    completed_task_count = models.PositiveIntegerField(default=0)
    failed_task_count = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    transition_history = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = DurableHistoryQuerySet.as_manager()

    class Meta:
        db_table = "automation_orchestration_runs"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="ao_run_tenant_idem_uniq"),
            models.CheckConstraint(
                condition=models.Q(completed_task_count__lte=models.F("task_count")), name="ao_run_completed_lte_total"
            ),
            models.CheckConstraint(
                condition=models.Q(failed_task_count__lte=models.F("task_count")), name="ao_run_failed_lte_total"
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "created_at"), name="ao_run_tenant_status_idx"),
            models.Index(fields=("tenant_id", "definition", "created_at"), name="ao_run_tenant_def_idx"),
            models.Index(fields=("tenant_id", "schedule", "created_at"), name="ao_run_tenant_sched_idx"),
            models.Index(fields=("tenant_id", "correlation_id"), name="ao_run_tenant_corr_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_related_tenant(self, "definition")
        _validate_related_tenant(self, "schedule")
        _validate_related_tenant(self, "parent_run")
        if self.schedule_id and self.schedule.definition_id != self.definition_id:
            raise ValidationError({"schedule": "The schedule and run must reference the same definition."})
        if self.parent_run_id and self.parent_run.definition_id != self.definition_id:
            raise ValidationError({"parent_run": "Retry lineage must retain the exact definition version."})
        self._validate_lifecycle()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class OrchestrationTaskRun(DurableHistoryMixin, TenantScopedModel, TimestampedModel):
    """Run-local execution state for one definition node."""

    TERMINAL_STATUSES = frozenset(
        {TaskRunStatus.SUCCEEDED, TaskRunStatus.FAILED, TaskRunStatus.SKIPPED, TaskRunStatus.CANCELLED}
    )
    ALLOWED_TRANSITIONS = {
        TaskRunStatus.BLOCKED: frozenset({TaskRunStatus.READY, TaskRunStatus.SKIPPED, TaskRunStatus.CANCELLED}),
        TaskRunStatus.READY: frozenset({TaskRunStatus.QUEUED, TaskRunStatus.SKIPPED, TaskRunStatus.CANCELLED}),
        TaskRunStatus.QUEUED: frozenset({TaskRunStatus.RUNNING, TaskRunStatus.CANCELLED}),
        TaskRunStatus.RUNNING: frozenset(
            {TaskRunStatus.SUCCEEDED, TaskRunStatus.RETRY_WAIT, TaskRunStatus.FAILED, TaskRunStatus.CANCELLED}
        ),
        TaskRunStatus.RETRY_WAIT: frozenset({TaskRunStatus.QUEUED, TaskRunStatus.FAILED, TaskRunStatus.CANCELLED}),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(OrchestrationRun, models.PROTECT, related_name="task_runs")
    node = models.ForeignKey(OrchestrationNode, models.PROTECT, related_name="task_runs")
    status = models.CharField(max_length=20, choices=TaskRunStatus.choices, default=TaskRunStatus.BLOCKED)
    input = models.JSONField(default=dict, blank=True)
    output = models.JSONField(null=True, blank=True)
    remaining_dependencies = models.PositiveIntegerField(default=0)
    current_attempt = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField()
    operation_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    transition_history = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = DurableHistoryQuerySet.as_manager()

    class Meta:
        db_table = "automation_orchestration_task_runs"
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(fields=("run", "node"), name="ao_task_run_node_uniq"),
            models.CheckConstraint(
                condition=models.Q(max_attempts__gte=1, max_attempts__lte=20), name="ao_task_attempts_1_20"
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "run", "status"), name="ao_task_tenant_run_status_idx"),
            models.Index(fields=("tenant_id", "status", "updated_at"), name="ao_task_tenant_status_idx"),
            models.Index(fields=("tenant_id", "node", "created_at"), name="ao_task_tenant_node_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_related_tenant(self, "run")
        _validate_related_tenant(self, "node", definition_id=self.run.definition_id if self.run_id else None)
        self._validate_lifecycle()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class RetryAttempt(DurableHistoryMixin, TenantScopedModel, TimestampedModel):
    """One physical execution attempt linked to the durable async substrate."""

    TERMINAL_STATUSES = frozenset(
        {AttemptStatus.SUCCEEDED, AttemptStatus.FAILED, AttemptStatus.TIMED_OUT, AttemptStatus.CANCELLED}
    )
    ALLOWED_TRANSITIONS = {
        AttemptStatus.QUEUED: frozenset({AttemptStatus.RUNNING, AttemptStatus.CANCELLED}),
        AttemptStatus.RUNNING: frozenset(
            {AttemptStatus.SUCCEEDED, AttemptStatus.FAILED, AttemptStatus.TIMED_OUT, AttemptStatus.CANCELLED}
        ),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_run = models.ForeignKey(OrchestrationTaskRun, models.PROTECT, related_name="attempts")
    attempt_number = models.PositiveSmallIntegerField()
    async_job_id = models.UUIDField(unique=True)
    idempotency_key = models.CharField(max_length=255)
    delivery_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    request_fingerprint = models.CharField(max_length=64, blank=True, default="")
    commit_outcome = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=AttemptStatus.choices, default=AttemptStatus.QUEUED)
    available_at = models.DateTimeField(db_index=True)
    correlation_id = models.CharField(max_length=64)
    output = models.JSONField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    duration_ms = models.PositiveBigIntegerField(null=True, blank=True)
    transition_history = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = DurableHistoryQuerySet.as_manager()

    class Meta:
        db_table = "automation_orchestration_retry_attempts"
        ordering = ("attempt_number",)
        constraints = [
            models.UniqueConstraint(fields=("task_run", "attempt_number"), name="ao_attempt_task_number_uniq"),
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="ao_attempt_tenant_idem_uniq"),
            models.CheckConstraint(
                condition=models.Q(attempt_number__gte=1, attempt_number__lte=20), name="ao_attempt_number_1_20"
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "task_run", "attempt_number"), name="ao_attempt_tenant_task_idx"),
            models.Index(fields=("tenant_id", "status", "available_at"), name="ao_attempt_tenant_due_idx"),
            models.Index(fields=("tenant_id", "correlation_id"), name="ao_attempt_tenant_corr_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_related_tenant(self, "task_run")
        self._validate_lifecycle()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class OrchestrationEventQuerySet(TenantQuerySet):
    """Query operations for immutable orchestration evidence."""

    def update(self, **kwargs: Any) -> int:
        del kwargs
        raise ValidationError("Orchestration events are append-only and cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Orchestration events are append-only and cannot be deleted.")


class OrchestrationEvent(TenantScopedModel):
    """Append-only audit evidence for orchestration and extension activity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aggregate_type = models.CharField(max_length=32)
    aggregate_id = models.UUIDField()
    event_type = models.CharField(max_length=100)
    actor_id = models.UUIDField(null=True, blank=True)
    correlation_id = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = OrchestrationEventQuerySet.as_manager()

    class Meta:
        db_table = "automation_orchestration_events"
        ordering = ("occurred_at", "id")
        indexes = [
            models.Index(
                fields=("tenant_id", "aggregate_type", "aggregate_id", "occurred_at"),
                name="ao_event_tenant_aggregate_idx",
            ),
            models.Index(fields=("tenant_id", "event_type", "occurred_at"), name="ao_event_tenant_type_idx"),
            models.Index(fields=("tenant_id", "correlation_id"), name="ao_event_tenant_corr_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Orchestration events are append-only and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Orchestration events are append-only and cannot be deleted.")


__all__ = [
    "AttemptStatus",
    "ConcurrencyPolicy",
    "DefinitionStatus",
    "EdgeCondition",
    "MisfirePolicy",
    "NodeType",
    "OrchestrationDefinition",
    "OrchestrationEdge",
    "OrchestrationEvent",
    "OrchestrationNode",
    "OrchestrationRun",
    "OrchestrationSchedule",
    "OrchestrationTaskRun",
    "RetryAttempt",
    "RunStatus",
    "RunTriggerType",
    "ScheduleStatus",
    "TaskRunStatus",
]
