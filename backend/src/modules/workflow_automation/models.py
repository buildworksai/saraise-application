"""Tenant-safe persistence for human and business workflow automation.

Definitions are immutable after publication, execution rows are durable
history, and every relationship is validated against the owning tenant.  The
service layer remains the command authority; these guards are the final line of
defence against accidental direct ORM mutation.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from src.core.tenancy.models import TenantQuerySet, TenantScopedModel, TimestampedModel


class WorkflowStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class WorkflowType(models.TextChoices):
    APPROVAL = "approval", "Approval"
    STATE_MACHINE = "state_machine", "State machine"
    SEQUENTIAL = "sequential", "Sequential"
    PARALLEL = "parallel", "Parallel"
    CONDITIONAL = "conditional", "Conditional"


class WorkflowTriggerType(models.TextChoices):
    MANUAL = "manual", "Manual"
    EVENT = "event", "Event"
    SCHEDULED = "scheduled", "Scheduled"


class WorkflowStepType(models.TextChoices):
    ACTION = "action", "Action"
    APPROVAL = "approval", "Approval"
    NOTIFICATION = "notification", "Notification"
    DECISION = "decision", "Decision"


class WorkflowTimeoutAction(models.TextChoices):
    FAIL = "fail", "Fail"
    NOTIFY = "notify", "Notify"
    ESCALATE = "escalate", "Escalate"
    CANCEL = "cancel", "Cancel"


class WorkflowInstanceState(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    WAITING = "waiting", "Waiting"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class WorkflowTaskStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"


class WorkflowAssignmentKind(models.TextChoices):
    USER = "user", "User"
    ROLE = "role", "Role"


class StepExecutionState(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


def _require_object(value: Any, field_name: str) -> None:
    if not isinstance(value, dict):
        raise ValidationError({field_name: "Must be a JSON object."})


def _require_list(value: Any, field_name: str) -> None:
    if not isinstance(value, list):
        raise ValidationError({field_name: "Must be a JSON array."})


def _stored_values(instance: models.Model, fields: Sequence[str]) -> dict[str, Any] | None:
    if instance._state.adding or instance.pk is None:
        return None
    return type(instance).objects.for_tenant(instance.tenant_id).filter(pk=instance.pk).values(*fields).first()


def _validate_immutable(instance: models.Model, fields: Sequence[str]) -> None:
    stored = _stored_values(instance, fields)
    if stored is None:
        return
    changed = [name for name, value in stored.items() if value != getattr(instance, name)]
    if changed:
        raise ValidationError({name: "This field is immutable after creation." for name in changed})


def _validate_append_only_history(instance: models.Model, *, state_field: str) -> None:
    history = getattr(instance, "transition_history")
    _require_list(history, "transition_history")
    if not all(isinstance(entry, dict) for entry in history):
        raise ValidationError({"transition_history": "Every transition must be a JSON object."})
    stored = _stored_values(instance, (state_field, "transition_history"))
    if stored is None:
        return
    old_history = stored["transition_history"]
    if not isinstance(old_history, list) or history[: len(old_history)] != old_history:
        raise ValidationError({"transition_history": "Transition history is append-only."})
    state_changed = stored[state_field] != getattr(instance, state_field)
    if state_changed and len(history) != len(old_history) + 1:
        raise ValidationError({"transition_history": "A state change must append exactly one transition."})
    if not state_changed and len(history) > len(old_history) + 1:
        raise ValidationError({"transition_history": "Only one transition may be appended per command."})


def _related_belongs_to_tenant(
    instance: TenantScopedModel,
    relation_name: str,
    *,
    extra_filters: dict[str, Any] | None = None,
) -> None:
    relation_id = getattr(instance, f"{relation_name}_id", None)
    if relation_id is None:
        return
    field = instance._meta.get_field(relation_name)
    related_model = field.remote_field.model
    queryset = related_model.objects.for_tenant(instance.tenant_id).filter(pk=relation_id)
    if extra_filters:
        queryset = queryset.filter(**extra_filters)
    if not queryset.exists():
        raise ValidationError({relation_name: "The related record must belong to the same tenant."})


class HistoricalTenantQuerySet(TenantQuerySet):
    """Prevent bulk deletion from bypassing durable evidence ownership."""

    def update(self, **kwargs: Any) -> int:
        model_name = self.model._meta.model_name
        state_field = "status" if model_name == "workflowtask" else "state"
        if model_name in {"workflowinstance", "workflowtask"} and state_field in kwargs:
            raise ValidationError("Lifecycle state changes must use the registered state machine.")
        terminal_states = getattr(self.model, "TERMINAL_STATES", frozenset())
        if terminal_states and self.filter(**{f"{state_field}__in": terminal_states}).exists():
            raise ValidationError("Terminal workflow execution evidence is immutable.")
        return super().update(**kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Workflow execution history cannot be deleted.")


class WorkflowQuerySet(TenantQuerySet):
    """Keep definition lifecycle and retention behind guarded services."""

    def update(self, **kwargs: Any) -> int:
        if "status" in kwargs or self.filter(status__in=("published", "archived")).exists():
            raise ValidationError("Published/archived definitions and lifecycle state are immutable.")
        return super().update(**kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Workflow definitions cannot be hard-deleted.")


class WorkflowStepQuerySet(TenantQuerySet):
    """Reject bulk edits to steps of immutable definition versions."""

    def update(self, **kwargs: Any) -> int:
        if self.filter(workflow__status__in=("published", "archived")).exists():
            raise ValidationError("Steps of published or archived definitions are immutable.")
        return super().update(**kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        if self.filter(workflow__status__in=("published", "archived")).exists():
            raise ValidationError("Steps of published or archived definitions are immutable.")
        return super().delete()


class HistoricalRecordMixin:
    """Execution evidence is retained and cannot be hard-deleted."""

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Workflow execution history cannot be deleted.")


class Workflow(TenantScopedModel, TimestampedModel):
    """One immutable version of a logical workflow definition."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    workflow_type = models.CharField(
        max_length=32,
        choices=WorkflowType.choices,
        default=WorkflowType.SEQUENTIAL,
    )
    trigger_type = models.CharField(
        max_length=20,
        choices=WorkflowTriggerType.choices,
        default=WorkflowTriggerType.MANUAL,
    )
    trigger_config = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT)
    required_context_schema = models.JSONField(default=dict, blank=True)
    transition_history = models.JSONField(default=list, blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_workflows",
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_workflows",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = WorkflowQuerySet.as_manager()

    class Meta:
        db_table = "workflow_definitions"
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "key", "version"), name="wf_def_tenant_key_ver_uniq"),
            models.UniqueConstraint(
                fields=("tenant_id", "key"),
                condition=models.Q(status=WorkflowStatus.PUBLISHED, deleted_at__isnull=True),
                name="wf_def_published_key_uniq",
            ),
            models.CheckConstraint(condition=models.Q(version__gte=1), name="wf_def_version_gte_1"),
            models.CheckConstraint(
                condition=~models.Q(status=WorkflowStatus.PUBLISHED) | models.Q(published_at__isnull=False),
                name="wf_def_published_at_required",
            ),
            models.CheckConstraint(
                condition=~models.Q(status=WorkflowStatus.ARCHIVED) | models.Q(archived_at__isnull=False),
                name="wf_def_archived_at_required",
            ),
            models.CheckConstraint(
                condition=models.Q(deleted_at__isnull=True) | models.Q(status=WorkflowStatus.DRAFT),
                name="wf_def_deleted_draft_only",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "-updated_at"), name="wf_def_tenant_status_upd_idx"),
            models.Index(fields=("tenant_id", "workflow_type", "status"), name="wf_def_tenant_type_status_idx"),
            models.Index(fields=("tenant_id", "trigger_type", "status"), name="wf_def_tenant_trigger_idx"),
            models.Index(fields=("tenant_id", "key", "-version"), name="wf_def_tenant_key_ver_idx"),
            models.Index(fields=("tenant_id", "deleted_at"), name="wf_def_tenant_deleted_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if not self.name or not self.name.strip():
            raise ValidationError({"name": "Name must not be blank."})
        if not self.key or not self.key.strip():
            raise ValidationError({"key": "Key must not be blank."})
        if self.key != self.key.strip():
            raise ValidationError({"key": "Key must not have leading or trailing whitespace."})
        _require_object(self.required_context_schema, "required_context_schema")
        _require_object(self.trigger_config, "trigger_config")
        _validate_append_only_history(self, state_field="status")
        _validate_immutable(self, ("tenant_id", "key", "version", "created_by_id"))
        if self.deleted_at is not None and self.status != WorkflowStatus.DRAFT:
            raise ValidationError({"deleted_at": "Only a draft workflow can be soft-deleted."})

        stored = _stored_values(self, tuple(field.attname for field in self._meta.concrete_fields))
        if stored is None:
            return
        old_status = str(stored["status"])
        if old_status not in {WorkflowStatus.PUBLISHED, WorkflowStatus.ARCHIVED}:
            return
        allowed = {"status", "transition_history", "archived_at", "updated_at"}
        changed = {
            field.attname
            for field in self._meta.concrete_fields
            if field.attname not in allowed and stored.get(field.attname) != getattr(self, field.attname)
        }
        if changed or (old_status == WorkflowStatus.ARCHIVED and stored["status"] != self.status):
            raise ValidationError(
                {"status": "Published and archived workflow versions are immutable; clone a new draft version."}
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Hard deletion is forbidden; use the draft soft-delete service.")

    def __str__(self) -> str:
        return f"{self.name} ({self.key} v{self.version}, {self.status})"


class WorkflowStep(TenantScopedModel, TimestampedModel):
    """A validated node in one exact workflow definition version."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="steps")
    key = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    step_type = models.CharField(max_length=20, choices=WorkflowStepType.choices)
    order = models.PositiveIntegerField()
    config = models.JSONField(default=dict, blank=True)
    next_step_keys = models.JSONField(default=list, blank=True)
    join_key = models.CharField(max_length=64, blank=True, default="")
    handler_contract_version = models.CharField(max_length=128, blank=True, default="")
    handler_contract_fingerprint = models.CharField(max_length=64, blank=True, default="")
    timeout_seconds = models.PositiveIntegerField(null=True, blank=True)
    timeout_action = models.CharField(
        max_length=20,
        choices=WorkflowTimeoutAction.choices,
        null=True,
        blank=True,
    )
    is_terminal = models.BooleanField(default=False)

    objects = WorkflowStepQuerySet.as_manager()

    class Meta:
        db_table = "workflow_steps"
        ordering = ("order", "id")
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "workflow", "key"), name="wf_step_tenant_key_uniq"),
            models.UniqueConstraint(fields=("tenant_id", "workflow", "order"), name="wf_step_tenant_order_uniq"),
            models.CheckConstraint(condition=models.Q(order__gte=1), name="wf_step_order_gte_1"),
            models.CheckConstraint(
                condition=models.Q(timeout_seconds__isnull=True) | models.Q(timeout_seconds__gt=0),
                name="wf_step_timeout_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(timeout_seconds__isnull=False) | models.Q(timeout_action__isnull=True),
                name="wf_step_timeout_action_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "workflow", "order"), name="wf_step_tenant_order_idx"),
            models.Index(fields=("tenant_id", "workflow", "step_type"), name="wf_step_tenant_type_idx"),
            models.Index(fields=("tenant_id", "is_terminal"), name="wf_step_tenant_terminal_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if not self.name or not self.name.strip():
            raise ValidationError({"name": "Name must not be blank."})
        if not self.key or not self.key.strip():
            raise ValidationError({"key": "Key must not be blank."})
        if self.key != self.key.strip():
            raise ValidationError({"key": "Key must not have leading or trailing whitespace."})
        _require_object(self.config, "config")
        _require_list(self.next_step_keys, "next_step_keys")
        if not all(isinstance(key, str) and key.strip() for key in self.next_step_keys):
            raise ValidationError({"next_step_keys": "Every graph edge must be a non-empty step key."})
        if len(self.next_step_keys) != len(set(self.next_step_keys)):
            raise ValidationError({"next_step_keys": "Graph edges must be unique."})
        if self.timeout_seconds is None and self.timeout_action is not None:
            raise ValidationError({"timeout_action": "A timeout action requires timeout_seconds."})
        _validate_immutable(self, ("tenant_id", "workflow_id"))
        _related_belongs_to_tenant(self, "workflow")
        if self.workflow_id is not None:
            workflow_status = (
                Workflow.objects.for_tenant(self.tenant_id)
                .filter(pk=self.workflow_id)
                .values_list("status", flat=True)
                .first()
            )
            if workflow_status in {WorkflowStatus.PUBLISHED, WorkflowStatus.ARCHIVED}:
                if self._state.adding:
                    raise ValidationError("Steps cannot be added to published or archived workflow versions.")
                stored = _stored_values(self, tuple(field.attname for field in self._meta.concrete_fields))
                if stored and any(
                    stored[field.attname] != getattr(self, field.attname) for field in self._meta.concrete_fields
                ):
                    raise ValidationError("Steps of published or archived workflow versions are immutable.")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.workflow.status != WorkflowStatus.DRAFT:
            raise ValidationError("Steps of published or archived workflows cannot be deleted.")
        return super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.order}. {self.name} ({self.step_type})"


class WorkflowInstance(HistoricalRecordMixin, TenantScopedModel, TimestampedModel):
    """Durable execution of an exact, immutable workflow version."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name="instances")
    workflow_version = models.PositiveIntegerField()
    current_step = models.ForeignKey(
        WorkflowStep,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_instances",
    )
    active_step_keys = models.JSONField(default=list, blank=True)
    state = models.CharField(
        max_length=20,
        choices=WorkflowInstanceState.choices,
        default=WorkflowInstanceState.PENDING,
    )
    context_data = models.JSONField(default=dict, blank=True)
    result_data = models.JSONField(default=dict, blank=True)
    entity_type = models.CharField(max_length=100, blank=True, default="")
    entity_id = models.UUIDField(null=True, blank=True)
    priority = models.PositiveSmallIntegerField(default=5)
    idempotency_key = models.CharField(max_length=255)
    transition_history = models.JSONField(default=list, blank=True, editable=False)
    correlation_id = models.CharField(max_length=64, db_index=True)
    async_job_id = models.UUIDField(null=True, blank=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="started_workflow_instances",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=64, blank=True, default="")
    failure_message = models.TextField(blank=True, default="")

    objects = HistoricalTenantQuerySet.as_manager()

    TERMINAL_STATES: ClassVar[frozenset[str]] = frozenset(
        {WorkflowInstanceState.COMPLETED, WorkflowInstanceState.FAILED, WorkflowInstanceState.CANCELLED}
    )

    class Meta:
        db_table = "workflow_instances"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="wf_inst_tenant_idem_uniq"),
            models.CheckConstraint(condition=models.Q(priority__gte=1, priority__lte=9), name="wf_inst_priority_1_9"),
            models.CheckConstraint(
                condition=(
                    models.Q(state__in=("completed", "failed", "cancelled"), completed_at__isnull=False)
                    | models.Q(state__in=("pending", "running", "waiting"), completed_at__isnull=True)
                ),
                name="wf_inst_terminal_completed_at",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(state=WorkflowInstanceState.FAILED, failure_code__gt="")
                    | (~models.Q(state=WorkflowInstanceState.FAILED) & models.Q(failure_code=""))
                ),
                name="wf_inst_failure_code_state",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "state", "-created_at"), name="wf_inst_state_created_idx"),
            models.Index(fields=("tenant_id", "workflow", "-created_at"), name="wf_inst_workflow_created_idx"),
            models.Index(fields=("tenant_id", "entity_type", "entity_id"), name="wf_inst_tenant_entity_idx"),
            models.Index(fields=("tenant_id", "started_by", "-created_at"), name="wf_inst_actor_created_idx"),
            models.Index(fields=("tenant_id", "correlation_id"), name="wf_inst_tenant_corr_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_object(self.context_data, "context_data")
        _require_object(self.result_data, "result_data")
        _require_list(self.active_step_keys, "active_step_keys")
        if not all(isinstance(key, str) and key.strip() for key in self.active_step_keys):
            raise ValidationError({"active_step_keys": "Active step keys must be non-empty strings."})
        _validate_append_only_history(self, state_field="state")
        _validate_immutable(
            self,
            ("tenant_id", "workflow_id", "workflow_version", "idempotency_key", "started_by_id", "correlation_id"),
        )
        _related_belongs_to_tenant(self, "workflow")
        if self.workflow_id is not None:
            version = (
                Workflow.objects.for_tenant(self.tenant_id)
                .filter(pk=self.workflow_id)
                .values_list("version", flat=True)
                .first()
            )
            if version is not None and version != self.workflow_version:
                raise ValidationError({"workflow_version": "Must match the referenced workflow version."})
        if self.current_step_id is not None:
            _related_belongs_to_tenant(self, "current_step", extra_filters={"workflow_id": self.workflow_id})
        stored = _stored_values(self, ("state",))
        if stored and stored["state"] in self.TERMINAL_STATES:
            prior = type(self).objects.for_tenant(self.tenant_id).filter(pk=self.pk).values().first()
            assert prior is not None
            changed = {
                field.attname
                for field in self._meta.concrete_fields
                if field.attname != "updated_at" and prior[field.attname] != getattr(self, field.attname)
            }
            if changed:
                raise ValidationError({"state": "Terminal workflow instance evidence is immutable."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.workflow_id} v{self.workflow_version} / {self.state}"


class WorkflowTask(HistoricalRecordMixin, TenantScopedModel, TimestampedModel):
    """A durable, attributable human decision request."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instance = models.ForeignKey(WorkflowInstance, on_delete=models.PROTECT, related_name="tasks")
    step = models.ForeignKey(WorkflowStep, on_delete=models.PROTECT, related_name="generated_tasks")
    assignment_kind = models.CharField(max_length=20, choices=WorkflowAssignmentKind.choices)
    assignment_key = models.CharField(max_length=255)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_workflow_tasks",
    )
    assignee_role_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=WorkflowTaskStatus.choices, default=WorkflowTaskStatus.PENDING)
    due_date = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_workflow_tasks",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    meta_data = models.JSONField(default=dict, blank=True)
    transition_history = models.JSONField(default=list, blank=True, editable=False)
    correlation_id = models.CharField(max_length=64, db_index=True)

    objects = HistoricalTenantQuerySet.as_manager()

    TERMINAL_STATES: ClassVar[frozenset[str]] = frozenset(
        {
            WorkflowTaskStatus.COMPLETED,
            WorkflowTaskStatus.REJECTED,
            WorkflowTaskStatus.CANCELLED,
            WorkflowTaskStatus.EXPIRED,
        }
    )

    class Meta:
        db_table = "workflow_tasks"
        ordering = ("due_date", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "instance", "step", "assignment_key"), name="wf_task_assignment_uniq"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        assignment_kind=WorkflowAssignmentKind.USER,
                        assignee__isnull=False,
                        assignee_role_id__isnull=True,
                    )
                    | models.Q(
                        assignment_kind=WorkflowAssignmentKind.ROLE,
                        assignee__isnull=True,
                        assignee_role_id__isnull=False,
                    )
                ),
                name="wf_task_assignment_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status=WorkflowTaskStatus.PENDING, completed_at__isnull=True)
                    | models.Q(status__in=("completed", "rejected", "cancelled", "expired"), completed_at__isnull=False)
                ),
                name="wf_task_terminal_completed_at",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "assignee", "due_date"), name="wf_task_tenant_user_due_idx"),
            models.Index(
                fields=("tenant_id", "status", "assignee_role_id", "due_date"), name="wf_task_tenant_role_due_idx"
            ),
            models.Index(fields=("tenant_id", "instance", "created_at"), name="wf_task_tenant_instance_idx"),
            models.Index(
                fields=("tenant_id", "due_date"),
                condition=models.Q(status=WorkflowTaskStatus.PENDING),
                name="wf_task_pending_due_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _require_object(self.meta_data, "meta_data")
        _validate_append_only_history(self, state_field="status")
        _validate_immutable(
            self,
            ("tenant_id", "instance_id", "step_id", "assignment_kind", "assignment_key", "correlation_id"),
        )
        _related_belongs_to_tenant(self, "instance")
        _related_belongs_to_tenant(self, "step")
        if self.instance_id and self.step_id:
            instance = (
                WorkflowInstance.objects.for_tenant(self.tenant_id)
                .filter(pk=self.instance_id)
                .values("workflow_id")
                .first()
            )
            step_workflow_id = (
                WorkflowStep.objects.for_tenant(self.tenant_id)
                .filter(pk=self.step_id)
                .values_list("workflow_id", flat=True)
                .first()
            )
            if instance and instance["workflow_id"] != step_workflow_id:
                raise ValidationError({"step": "The task step must belong to the instance workflow."})
        if self.assignment_kind == WorkflowAssignmentKind.USER:
            if self.assignee_id is None or self.assignee_role_id is not None:
                raise ValidationError({"assignment_kind": "User assignment requires only an assignee."})
            expected = f"user:{self.assignee_id}"
        elif self.assignment_kind == WorkflowAssignmentKind.ROLE:
            if self.assignee_role_id is None or self.assignee_id is not None:
                raise ValidationError({"assignment_kind": "Role assignment requires only assignee_role_id."})
            expected = f"role:{self.assignee_role_id}"
        else:
            expected = ""
        if expected and self.assignment_key != expected:
            raise ValidationError({"assignment_key": f"Must use normalized value {expected}."})
        stored = _stored_values(self, ("status",))
        if stored and stored["status"] in self.TERMINAL_STATES:
            prior = type(self).objects.for_tenant(self.tenant_id).filter(pk=self.pk).values().first()
            assert prior is not None
            changed = {
                field.attname
                for field in self._meta.concrete_fields
                if field.attname != "updated_at" and prior[field.attname] != getattr(self, field.attname)
            }
            if changed:
                raise ValidationError({"status": "Terminal workflow task evidence is immutable."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.instance_id}: {self.step_id} ({self.status})"


class WorkflowStepExecution(HistoricalRecordMixin, TenantScopedModel, TimestampedModel):
    """Immutable per-attempt evidence for one workflow step execution.

    This ledger supplies the exact handler contract, timings, outcome, and
    durable operation key needed for safe retries and paid-module upgrades.
    Input payloads are intentionally not retained; ``input_fingerprint`` proves
    what was invoked without persisting workflow context or secrets.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instance = models.ForeignKey(WorkflowInstance, on_delete=models.PROTECT, related_name="step_executions")
    step = models.ForeignKey(WorkflowStep, on_delete=models.PROTECT, related_name="executions")
    attempt = models.PositiveSmallIntegerField(default=1)
    operation_key = models.CharField(max_length=255)
    state = models.CharField(max_length=20, choices=StepExecutionState.choices, default=StepExecutionState.PENDING)
    handler_key = models.CharField(max_length=150)
    handler_contract_version = models.CharField(max_length=128)
    handler_contract_fingerprint = models.CharField(max_length=64)
    input_fingerprint = models.CharField(max_length=64)
    output_evidence = models.JSONField(default=dict, blank=True)
    provider_evidence = models.JSONField(default=dict, blank=True)
    correlation_id = models.CharField(max_length=64, db_index=True)
    async_job_id = models.UUIDField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveBigIntegerField(null=True, blank=True)
    failure_code = models.CharField(max_length=64, blank=True, default="")
    failure_message = models.TextField(blank=True, default="")

    objects = HistoricalTenantQuerySet.as_manager()

    TERMINAL_STATES: ClassVar[frozenset[str]] = frozenset(
        {StepExecutionState.SUCCEEDED, StepExecutionState.FAILED, StepExecutionState.CANCELLED}
    )

    class Meta:
        db_table = "workflow_step_executions"
        ordering = ("created_at", "attempt")
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "operation_key"), name="wf_step_exec_operation_uniq"),
            models.UniqueConstraint(
                fields=("tenant_id", "instance", "step", "attempt"), name="wf_step_exec_attempt_uniq"
            ),
            models.CheckConstraint(condition=models.Q(attempt__gte=1), name="wf_step_exec_attempt_gte_1"),
            models.CheckConstraint(
                condition=(
                    models.Q(state__in=("succeeded", "failed", "cancelled"), completed_at__isnull=False)
                    | models.Q(state__in=("pending", "running"), completed_at__isnull=True)
                ),
                name="wf_step_exec_terminal_time",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(state=StepExecutionState.FAILED, failure_code__gt="")
                    | (~models.Q(state=StepExecutionState.FAILED) & models.Q(failure_code=""))
                ),
                name="wf_step_exec_failure_state",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "instance", "created_at"), name="wf_step_exec_instance_idx"),
            models.Index(fields=("tenant_id", "state", "created_at"), name="wf_step_exec_state_idx"),
            models.Index(fields=("tenant_id", "handler_key", "created_at"), name="wf_step_exec_handler_idx"),
            models.Index(fields=("tenant_id", "correlation_id"), name="wf_step_exec_corr_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        _require_object(self.output_evidence, "output_evidence")
        _require_object(self.provider_evidence, "provider_evidence")
        _validate_immutable(
            self,
            (
                "tenant_id",
                "instance_id",
                "step_id",
                "attempt",
                "operation_key",
                "handler_key",
                "handler_contract_version",
                "handler_contract_fingerprint",
                "input_fingerprint",
                "correlation_id",
            ),
        )
        _related_belongs_to_tenant(self, "instance")
        _related_belongs_to_tenant(self, "step")
        if self.instance_id and self.step_id:
            instance = (
                WorkflowInstance.objects.for_tenant(self.tenant_id)
                .filter(pk=self.instance_id)
                .values("workflow_id")
                .first()
            )
            step_workflow_id = (
                WorkflowStep.objects.for_tenant(self.tenant_id)
                .filter(pk=self.step_id)
                .values_list("workflow_id", flat=True)
                .first()
            )
            if instance and instance["workflow_id"] != step_workflow_id:
                raise ValidationError({"step": "The execution step must belong to the instance workflow."})
        stored = _stored_values(self, ("state",))
        if stored and stored["state"] in self.TERMINAL_STATES:
            prior = type(self).objects.for_tenant(self.tenant_id).filter(pk=self.pk).values().first()
            assert prior is not None
            changed = {
                field.attname
                for field in self._meta.concrete_fields
                if field.attname != "updated_at" and prior[field.attname] != getattr(self, field.attname)
            }
            if changed:
                raise ValidationError({"state": "Completed step execution evidence is immutable."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.instance_id}/{self.step_id} attempt {self.attempt}: {self.state}"


__all__ = [
    "StepExecutionState",
    "Workflow",
    "WorkflowAssignmentKind",
    "WorkflowInstance",
    "WorkflowInstanceState",
    "WorkflowStatus",
    "WorkflowStep",
    "WorkflowStepExecution",
    "WorkflowStepType",
    "WorkflowTask",
    "WorkflowTaskStatus",
    "WorkflowTimeoutAction",
    "WorkflowTriggerType",
    "WorkflowType",
]
