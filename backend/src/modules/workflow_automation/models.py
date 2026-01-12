import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class WorkflowStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    PUBLISHED = "published", _("Published")
    ARCHIVED = "archived", _("Archived")


class WorkflowTriggerType(models.TextChoices):
    MANUAL = "manual", _("Manual")
    EVENT = "event", _("Event")
    SCHEDULED = "scheduled", _("Scheduled")


class WorkflowStepType(models.TextChoices):
    ACTION = "action", _("Action")
    APPROVAL = "approval", _("Approval")
    NOTIFICATION = "notification", _("Notification")
    DECISION = "decision", _("Decision")


class WorkflowInstanceState(models.TextChoices):
    PENDING = "pending", _("Pending")
    RUNNING = "running", _("Running")
    COMPLETED = "completed", _("Completed")
    FAILED = "failed", _("Failed")
    CANCELLED = "cancelled", _("Cancelled")


class WorkflowTaskStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    COMPLETED = "completed", _("Completed")
    REJECTED = "rejected", _("Rejected")
    CANCELLED = "cancelled", _("Cancelled")


class Workflow(models.Model):
    """
    Defines a workflow template.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT)
    trigger_type = models.CharField(
        max_length=20, choices=WorkflowTriggerType.choices, default=WorkflowTriggerType.MANUAL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_workflows"
    )

    class Meta:
        db_table = "workflow_definitions"
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
        ]
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.name} ({self.status})"


class WorkflowStep(models.Model):
    """
    A single step within a workflow definition.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="steps")
    name = models.CharField(max_length=255)
    step_type = models.CharField(max_length=20, choices=WorkflowStepType.choices)
    order = models.PositiveIntegerField()
    config = models.JSONField(default=dict, blank=True)
    # Config can contain: assignee_role, next_step_id (for branching), etc.

    class Meta:
        db_table = "workflow_steps"
        ordering = ["order"]
        unique_together = ["workflow", "order"]

    def __str__(self):
        return f"{self.order}. {self.name} ({self.step_type})"


class WorkflowInstance(models.Model):
    """
    An execution instance of a workflow.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    workflow = models.ForeignKey(
        Workflow, on_delete=models.PROTECT, related_name="instances"  # Don't delete definition if it has history
    )
    current_step = models.ForeignKey(
        WorkflowStep, on_delete=models.SET_NULL, null=True, blank=True, related_name="active_instances"
    )
    state = models.CharField(
        max_length=20, choices=WorkflowInstanceState.choices, default=WorkflowInstanceState.PENDING
    )
    context_data = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="started_workflow_instances"
    )

    class Meta:
        db_table = "workflow_instances"
        indexes = [
            models.Index(fields=["tenant_id", "state"]),
        ]
        ordering = ["-started_at"]

    def __str__(self):
        return f"Instance of {self.workflow.name} - {self.state}"


class WorkflowTask(models.Model):
    """
    A task assigned to a user or role during workflow execution.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    instance = models.ForeignKey(WorkflowInstance, on_delete=models.CASCADE, related_name="tasks")
    step = models.ForeignKey(WorkflowStep, on_delete=models.PROTECT, related_name="generated_tasks")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_workflow_tasks",
    )
    # Could also support assignment by Role/Group here
    assignee_role_id = models.UUIDField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=WorkflowTaskStatus.choices, default=WorkflowTaskStatus.PENDING)
    due_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    meta_data = models.JSONField(default=dict, blank=True)  # Store approval comments etc.

    class Meta:
        db_table = "workflow_tasks"
        indexes = [
            models.Index(fields=["tenant_id", "status", "assignee"]),
        ]
        ordering = ["due_date", "created_at"]

    def __str__(self):
        return f"Task for {self.instance}: {self.step.name}"
