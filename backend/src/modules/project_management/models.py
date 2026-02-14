"""
Project Management Models.

Defines data models for projects, tasks, project members, time entries, and milestones.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class TenantBaseModel(models.Model):
    """Base model for tenant-scoped models with Row-Level Multitenancy.

    CRITICAL: All tenant-scoped models MUST inherit from this base class
    and include tenant_id. All queries MUST filter explicitly by tenant_id.
    """

    tenant_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class ProjectStatus(models.TextChoices):
    """Project status choices."""

    PLANNING = "planning", "Planning"
    ACTIVE = "active", "Active"
    ON_HOLD = "on_hold", "On Hold"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class Project(TenantBaseModel):
    """Project model - Project container."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    project_code = models.CharField(max_length=50, db_index=True)
    project_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_date = models.DateField(db_index=True, null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=50, choices=ProjectStatus.choices, default=ProjectStatus.PLANNING, db_index=True
    )
    project_manager_id = models.UUIDField(null=True, blank=True, help_text="FK to employee")
    budget = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")

    class Meta:
        db_table = "project_projects"
        indexes = [
            models.Index(fields=["tenant_id", "project_code"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "start_date"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "project_code"], name="unique_project_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.project_code} - {self.project_name}"


class TaskStatus(models.TextChoices):
    """Task status choices."""

    TODO = "todo", "To Do"
    IN_PROGRESS = "in_progress", "In Progress"
    REVIEW = "review", "Review"
    DONE = "done", "Done"
    BLOCKED = "blocked", "Blocked"
    CANCELLED = "cancelled", "Cancelled"


class Task(TenantBaseModel):
    """Task model - Individual task within a project."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    task_code = models.CharField(max_length=50, db_index=True)
    task_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assigned_to_id = models.UUIDField(null=True, blank=True, help_text="FK to employee")
    due_date = models.DateField(null=True, blank=True, db_index=True)
    estimated_hours = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    actual_hours = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=50, choices=TaskStatus.choices, default=TaskStatus.TODO, db_index=True)
    parent_task_id = models.UUIDField(null=True, blank=True, help_text="For subtasks")

    class Meta:
        db_table = "project_tasks"
        indexes = [
            models.Index(fields=["tenant_id", "project"]),
            models.Index(fields=["tenant_id", "assigned_to_id"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "due_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.task_code} - {self.task_name}"


class ProjectMember(TenantBaseModel):
    """Project member model - Team member assigned to project."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    employee_id = models.UUIDField(db_index=True, help_text="FK to employee")
    role = models.CharField(max_length=50, default="member")  # project_manager, team_lead, member, stakeholder
    allocation_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("100.00"), validators=[MinValueValidator(Decimal("0.00"))]
    )

    class Meta:
        db_table = "project_members"
        indexes = [
            models.Index(fields=["tenant_id", "project"]),
            models.Index(fields=["tenant_id", "employee_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "project", "employee_id"], name="unique_project_member_per_tenant"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.project.project_code} - Employee {self.employee_id}"


class TimeEntry(TenantBaseModel):
    """Time entry model - Time logged on tasks."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="time_entries")
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="time_entries", null=True, blank=True)
    employee_id = models.UUIDField(db_index=True, help_text="FK to employee")
    entry_date = models.DateField(db_index=True)
    hours_worked = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    description = models.TextField(blank=True)

    class Meta:
        db_table = "project_time_entries"
        indexes = [
            models.Index(fields=["tenant_id", "project"]),
            models.Index(fields=["tenant_id", "task"]),
            models.Index(fields=["tenant_id", "employee_id"]),
            models.Index(fields=["tenant_id", "entry_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.entry_date} - {self.hours_worked} hours"


class ProjectMilestone(TenantBaseModel):
    """Project milestone model - Key project milestones."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    milestone_name = models.CharField(max_length=255)
    target_date = models.DateField(db_index=True)
    achieved_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "project_milestones"
        indexes = [
            models.Index(fields=["tenant_id", "project"]),
            models.Index(fields=["tenant_id", "target_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.project.project_code} - {self.milestone_name}"
