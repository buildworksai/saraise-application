"""Tenant-safe persistence for project execution.

The models deliberately contain structural invariants only. Workflow,
idempotency, optimistic concurrency, audit and configurable policy live in
``services.py`` so every API and extension follows the same path.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from src.core.tenancy import TenantQuerySet, TenantScopedModel, TimestampedModel
from src.core.tenancy.registry import TENANT_SCOPED, tenancy_scope


class ActiveQuerySet(TenantQuerySet):
    def active(self):
        return self.filter(archived_at__isnull=True)

class ActiveManager(models.Manager.from_queryset(ActiveQuerySet)):
    def get_queryset(self): return super().get_queryset().filter(archived_at__isnull=True)


class MutableTenantModel(TenantScopedModel, TimestampedModel):
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by_id = models.UUIDField(null=True, blank=True)
    objects = ActiveManager()
    all_objects = TenantQuerySet.as_manager()

    class Meta:
        abstract = True


class ProjectStatus(models.TextChoices):
    PLANNING = "planning", "Planning"
    ACTIVE = "active", "Active"
    ON_HOLD = "on_hold", "On hold"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class TaskStatus(models.TextChoices):
    TODO = "todo", "To do"
    IN_PROGRESS = "in_progress", "In progress"
    REVIEW = "review", "Review"
    DONE = "done", "Done"
    BLOCKED = "blocked", "Blocked"
    CANCELLED = "cancelled", "Cancelled"


class TaskPriority(models.TextChoices):
    CRITICAL = "critical", "Critical"
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"


class MemberRole(models.TextChoices):
    PROJECT_MANAGER = "project_manager", "Project manager"
    TEAM_LEAD = "team_lead", "Team lead"
    MEMBER = "member", "Member"
    STAKEHOLDER = "stakeholder", "Stakeholder"


class ConfigurationEnvironment(models.TextChoices):
    DEVELOPMENT = "development", "Development"
    STAGING = "staging", "Staging"
    PRODUCTION = "production", "Production"


class ConfigurationState(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    SUPERSEDED = "superseded", "Superseded"


@tenancy_scope(TENANT_SCOPED)
class Project(MutableTenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_code = models.CharField(max_length=50)
    project_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=ProjectStatus.choices, default=ProjectStatus.PLANNING)
    project_manager_id = models.UUIDField(null=True, blank=True)
    budget = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    transition_history = models.JSONField(default=list, blank=True)
    version = models.PositiveBigIntegerField(default=1)

    class Meta:
        db_table = "project_projects"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "project_code"), condition=Q(archived_at__isnull=True), name="pm_project_active_code_uniq"),
            models.UniqueConstraint(fields=("tenant_id", "id"), name="pm_project_tenant_id_uniq"),
            models.CheckConstraint(condition=Q(budget__isnull=True) | Q(budget__gte=0), name="pm_project_budget_nonnegative"),
            models.CheckConstraint(condition=Q(start_date__isnull=True) | Q(end_date__isnull=True) | Q(start_date__lte=models.F("end_date")), name="pm_project_dates_valid"),
            models.CheckConstraint(condition=Q(version__gte=1), name="pm_project_version_positive"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "archived_at"), name="pm_project_status_idx"),
            models.Index(fields=("tenant_id", "project_manager_id", "status"), name="pm_project_manager_idx"),
            models.Index(fields=("tenant_id", "start_date"), name="pm_project_start_idx"),
            models.Index(fields=("tenant_id", "updated_at"), name="pm_project_updated_idx"),
        ]

    def clean(self):
        self.project_code = self.project_code.strip().upper()
        self.project_name = self.project_name.strip()
        self.currency = self.currency.strip().upper()
        errors = {}
        if not self.project_code: errors["project_code"] = "Project code is required."
        if not self.project_name: errors["project_name"] = "Project name is required."
        if len(self.description) > 20_000: errors["description"] = "Description cannot exceed 20000 characters."
        if len(self.currency) != 3 or not self.currency.isalpha(): errors["currency"] = "Use a three-letter ISO currency code."
        if self.start_date and self.end_date and self.start_date > self.end_date: errors["end_date"] = "End date cannot precede start date."
        if errors: raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.project_code} - {self.project_name}"


@tenancy_scope(TENANT_SCOPED)
class Task(MutableTenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="tasks")
    task_code = models.CharField(max_length=50)
    task_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    assigned_to_id = models.UUIDField(null=True, blank=True)
    parent_task = models.ForeignKey("self", on_delete=models.PROTECT, related_name="children", null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=12, choices=TaskPriority.choices, default=TaskPriority.MEDIUM)
    estimated_hours = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    actual_hours = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    percent_complete = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.TODO)
    position = models.PositiveIntegerField(default=1)
    transition_history = models.JSONField(default=list, blank=True)
    version = models.PositiveBigIntegerField(default=1)

    class Meta:
        db_table = "project_tasks"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "project", "task_code"), condition=Q(archived_at__isnull=True), name="pm_task_active_code_uniq"),
            models.UniqueConstraint(fields=("tenant_id", "id"), name="pm_task_tenant_id_uniq"),
            models.CheckConstraint(condition=Q(estimated_hours__isnull=True) | Q(estimated_hours__gte=0), name="pm_task_estimate_nonnegative"),
            models.CheckConstraint(condition=Q(actual_hours__gte=0), name="pm_task_actual_nonnegative"),
            models.CheckConstraint(condition=Q(percent_complete__gte=0, percent_complete__lte=100), name="pm_task_progress_range"),
            models.CheckConstraint(condition=Q(start_date__isnull=True) | Q(due_date__isnull=True) | Q(start_date__lte=models.F("due_date")), name="pm_task_dates_valid"),
            models.CheckConstraint(condition=Q(position__gte=1), name="pm_task_position_positive"),
            models.CheckConstraint(condition=Q(version__gte=1), name="pm_task_version_positive"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "project", "status", "position"), name="pm_task_project_idx"),
            models.Index(fields=("tenant_id", "assigned_to_id", "status"), name="pm_task_assignee_idx"),
            models.Index(fields=("tenant_id", "due_date", "status"), name="pm_task_due_idx"),
            models.Index(fields=("tenant_id", "parent_task"), name="pm_task_parent_idx"),
        ]

    @property
    def parent_task_id_legacy(self):
        return self.parent_task_id

    def clean(self):
        self.task_code = self.task_code.strip().upper()
        self.task_name = self.task_name.strip()
        errors = {}
        if not self.task_code: errors["task_code"] = "Task code is required."
        if not self.task_name: errors["task_name"] = "Task name is required."
        if len(self.description) > 20_000: errors["description"] = "Description cannot exceed 20000 characters."
        if self.project_id and self.tenant_id != self.project.tenant_id: errors["project"] = "Project must belong to this tenant."
        if self.parent_task_id:
            if self.pk and self.parent_task_id == self.pk: errors["parent_task"] = "A task cannot be its own parent."
            elif self.parent_task.tenant_id != self.tenant_id or self.parent_task.project_id != self.project_id: errors["parent_task"] = "Parent must belong to the same tenant and project."
            else:
                seen = {self.pk} if self.pk else set()
                node = self.parent_task
                while node:
                    if node.pk in seen: errors["parent_task"] = "Parent relationship creates a cycle."; break
                    seen.add(node.pk); node = node.parent_task
        if self.start_date and self.due_date and self.start_date > self.due_date: errors["due_date"] = "Due date cannot precede start date."
        if errors: raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self): return f"{self.task_code} - {self.task_name}"


@tenancy_scope(TENANT_SCOPED)
class ProjectMember(MutableTenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="members")
    employee_id = models.UUIDField()
    role = models.CharField(max_length=24, choices=MemberRole.choices, default=MemberRole.MEMBER)
    allocation_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("100.00"), validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("100.00"))])
    joined_at = models.DateField(default=timezone.localdate)
    left_at = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "project_members"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "project", "employee_id"), condition=Q(archived_at__isnull=True), name="pm_member_active_uniq"),
            models.CheckConstraint(condition=Q(allocation_percentage__gt=0, allocation_percentage__lte=100), name="pm_member_allocation_range"),
            models.CheckConstraint(condition=Q(left_at__isnull=True) | Q(left_at__gte=models.F("joined_at")), name="pm_member_dates_valid"),
        ]
        indexes = [models.Index(fields=("tenant_id", "project", "role"), name="pm_member_project_idx"), models.Index(fields=("tenant_id", "employee_id", "archived_at"), name="pm_member_employee_idx")]

    def clean(self):
        if self.project_id and self.project.tenant_id != self.tenant_id: raise ValidationError({"project": "Project must belong to this tenant."})
        if self.left_at and self.joined_at and self.left_at < self.joined_at: raise ValidationError({"left_at": "Left date cannot precede joined date."})

    def save(self, *args, **kwargs): self.full_clean(); return super().save(*args, **kwargs)
    def __str__(self): return f"{self.project.project_code} - Employee {self.employee_id}"


@tenancy_scope(TENANT_SCOPED)
class TimeEntry(MutableTenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="time_entries")
    task = models.ForeignKey(Task, on_delete=models.PROTECT, related_name="time_entries", null=True, blank=True)
    employee_id = models.UUIDField()
    entry_date = models.DateField()
    hours_worked = models.DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("24.00"))])
    description = models.TextField()
    billable = models.BooleanField(default=False)
    version = models.PositiveBigIntegerField(default=1)
    idempotency_key = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "project_time_entries"
        constraints = [
            models.CheckConstraint(condition=Q(hours_worked__gt=0, hours_worked__lte=24), name="pm_time_hours_range"),
            models.CheckConstraint(condition=Q(version__gte=1), name="pm_time_version_positive"),
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), condition=Q(idempotency_key__isnull=False), name="pm_time_idempotency_uniq"),
        ]
        indexes = [models.Index(fields=("tenant_id", "employee_id", "entry_date"), name="pm_time_employee_idx"), models.Index(fields=("tenant_id", "project", "entry_date"), name="pm_time_project_idx"), models.Index(fields=("tenant_id", "task", "entry_date"), name="pm_time_task_idx")]

    def clean(self):
        errors = {}
        if self.project_id and self.project.tenant_id != self.tenant_id: errors["project"] = "Project must belong to this tenant."
        if self.task_id and (self.task.tenant_id != self.tenant_id or self.task.project_id != self.project_id): errors["task"] = "Task must belong to the same tenant and project."
        if len(self.description) > 4000: errors["description"] = "Description cannot exceed 4000 characters."
        if errors: raise ValidationError(errors)

    def save(self, *args, **kwargs): self.full_clean(); return super().save(*args, **kwargs)
    def __str__(self): return f"{self.entry_date} - {self.hours_worked} hours"


@tenancy_scope(TENANT_SCOPED)
class ProjectMilestone(MutableTenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="milestones")
    milestone_name = models.CharField(max_length=255)
    target_date = models.DateField()
    achieved_date = models.DateField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True, default="")
    version = models.PositiveBigIntegerField(default=1)

    class Meta:
        db_table = "project_milestones"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "project", "milestone_name"), condition=Q(archived_at__isnull=True), name="pm_milestone_active_uniq"),
            models.CheckConstraint(condition=Q(achieved_date__isnull=True) | Q(cancelled_at__isnull=True), name="pm_milestone_one_outcome"),
            models.CheckConstraint(condition=Q(version__gte=1), name="pm_milestone_version_positive"),
        ]
        indexes = [models.Index(fields=("tenant_id", "project", "target_date"), name="pm_milestone_project_idx"), models.Index(fields=("tenant_id", "achieved_date"), name="pm_milestone_achieved_idx"), models.Index(fields=("tenant_id", "cancelled_at"), name="pm_milestone_cancelled_idx")]

    def clean(self):
        self.milestone_name = self.milestone_name.strip()
        errors = {}
        if not self.milestone_name: errors["milestone_name"] = "Milestone name is required."
        if self.project_id and self.project.tenant_id != self.tenant_id: errors["project"] = "Project must belong to this tenant."
        if self.achieved_date and self.cancelled_at: errors["achieved_date"] = "A milestone cannot be achieved and cancelled."
        if len(self.description) > 10_000: errors["description"] = "Description cannot exceed 10000 characters."
        if errors: raise ValidationError(errors)

    def save(self, *args, **kwargs): self.full_clean(); return super().save(*args, **kwargs)
    def __str__(self): return f"{self.project.project_code} - {self.milestone_name}"


@tenancy_scope(TENANT_SCOPED)
class ProjectManagementConfiguration(TenantScopedModel, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.CharField(max_length=20, choices=ConfigurationEnvironment.choices)
    active_version = models.ForeignKey("ProjectManagementConfigurationVersion", on_delete=models.PROTECT, related_name="active_for", null=True, blank=True)

    class Meta:
        db_table = "project_management_configurations"
        constraints = [models.UniqueConstraint(fields=("tenant_id", "environment"), name="pm_config_environment_uniq"), models.UniqueConstraint(fields=("tenant_id", "id"), name="pm_config_tenant_id_uniq")]


class ImmutableQuerySet(TenantQuerySet):
    def update(self, **kwargs): raise ValidationError("Immutable history cannot be updated.", code="immutable_history")
    def delete(self): raise ValidationError("Immutable history cannot be deleted.", code="immutable_history")
    def _service_update(self, **kwargs): return super().update(**kwargs)


@tenancy_scope(TENANT_SCOPED)
class ProjectManagementConfigurationVersion(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(ProjectManagementConfiguration, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    state = models.CharField(max_length=12, choices=ConfigurationState.choices, default=ConfigurationState.DRAFT)
    default_currency = models.CharField(max_length=3, default="USD")
    project_code_pattern = models.CharField(max_length=255, default=r"^[A-Z][A-Z0-9-]{0,49}$")
    task_code_pattern = models.CharField(max_length=255, default=r"^[A-Z][A-Z0-9-]{0,49}$")
    max_daily_hours = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("12.00"))
    max_allocation_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("100.00"))
    enforce_project_date_bounds = models.BooleanField(default=True)
    allow_future_time_entries = models.BooleanField(default=False)
    require_time_description = models.BooleanField(default=True)
    default_billable = models.BooleanField(default=False)
    enabled_views = models.JSONField(default=list)
    paid_extension_rollout = models.JSONField(default=dict)
    change_summary = models.CharField(max_length=500)
    created_by_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableQuerySet.as_manager()

    class Meta:
        db_table = "project_management_configuration_versions"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "configuration", "version"), name="pm_config_version_uniq"),
            models.UniqueConstraint(fields=("tenant_id", "id"), name="pm_configver_tenant_id_uniq"),
            models.UniqueConstraint(fields=("tenant_id", "configuration"), condition=Q(state=ConfigurationState.ACTIVE), name="pm_config_one_active_uniq"),
            models.CheckConstraint(condition=Q(version__gte=1), name="pm_config_version_positive"),
            models.CheckConstraint(condition=Q(max_daily_hours__gt=0, max_daily_hours__lte=24), name="pm_config_hours_range"),
            models.CheckConstraint(condition=Q(max_allocation_percentage__gt=0, max_allocation_percentage__lte=100), name="pm_config_allocation_range"),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self)._base_manager.filter(pk=self.pk).exists(): raise ValidationError("Configuration versions are immutable.", code="immutable_history")
        return super().save(*args, **kwargs)
    def delete(self, *args, **kwargs): raise ValidationError("Configuration versions are immutable.", code="immutable_history")


@tenancy_scope(TENANT_SCOPED)
class ProjectActivity(TenantScopedModel):
    ENTITY_TYPES = (("project", "Project"), ("task", "Task"), ("member", "Member"), ("time_entry", "Time entry"), ("milestone", "Milestone"), ("configuration", "Configuration"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="activities", null=True, blank=True)
    entity_type = models.CharField(max_length=32, choices=ENTITY_TYPES)
    entity_id = models.UUIDField()
    action = models.CharField(max_length=64)
    actor_id = models.UUIDField()
    correlation_id = models.CharField(max_length=64)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableQuerySet.as_manager()

    class Meta:
        db_table = "project_activities"
        indexes = [models.Index(fields=("tenant_id", "project", "created_at"), name="pm_activity_project_idx"), models.Index(fields=("tenant_id", "entity_type", "entity_id"), name="pm_activity_entity_idx"), models.Index(fields=("tenant_id", "correlation_id"), name="pm_activity_correlation_idx")]

    def save(self, *args, **kwargs):
        if self.pk and type(self)._base_manager.filter(pk=self.pk).exists(): raise ValidationError("Activity history is immutable.", code="immutable_history")
        return super().save(*args, **kwargs)
    def delete(self, *args, **kwargs): raise ValidationError("Activity history is immutable.", code="immutable_history")
