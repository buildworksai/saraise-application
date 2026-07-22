"""Explicit read, write, lifecycle, audit, and configuration contracts."""

from rest_framework import serializers

from .models import (
    Project, ProjectActivity, ProjectManagementConfigurationVersion,
    ProjectMember, ProjectMilestone, Task, TimeEntry,
)


class StrictSerializer(serializers.Serializer):
    """DRF already rejects undeclared fields; this base documents that contract."""


class AllowedActionsMixin:
    allowed_actions = serializers.SerializerMethodField()
    def get_allowed_actions(self, obj):
        if getattr(obj, "archived_at", None): return ["restore"]
        return list(getattr(self.Meta, "allowed_actions", ("update", "archive")))


class ProjectListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project; fields = ("id", "project_code", "project_name", "status", "start_date", "end_date", "project_manager_id", "budget", "currency", "version", "archived_at", "updated_at")


class ProjectDetailSerializer(AllowedActionsMixin, serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()
    class Meta:
        model = Project; fields = ("id", "project_code", "project_name", "description", "start_date", "end_date", "status", "project_manager_id", "budget", "currency", "transition_history", "version", "archived_at", "created_at", "updated_at", "allowed_actions"); allowed_actions = ("update", "transition", "archive", "duplicate")


class ProjectCreateSerializer(StrictSerializer):
    project_code = serializers.CharField(max_length=50); project_name = serializers.CharField(max_length=255); description = serializers.CharField(max_length=20000, required=False, allow_blank=True); start_date = serializers.DateField(required=False, allow_null=True); end_date = serializers.DateField(required=False, allow_null=True); project_manager_id = serializers.UUIDField(required=False, allow_null=True); budget = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, allow_null=True, min_value=0); currency = serializers.CharField(max_length=3, required=False)
    def validate(self, attrs):
        if attrs.get("start_date") and attrs.get("end_date") and attrs["start_date"] > attrs["end_date"]: raise serializers.ValidationError({"end_date": "End date cannot precede start date."})
        return attrs


class ProjectUpdateSerializer(ProjectCreateSerializer):
    project_code = serializers.CharField(max_length=50, required=False); project_name = serializers.CharField(max_length=255, required=False); version = serializers.IntegerField(min_value=1); idempotency_key = serializers.CharField(max_length=255)


class TaskListSerializer(serializers.ModelSerializer):
    project_code = serializers.CharField(source="project.project_code", read_only=True)
    class Meta: model = Task; fields = ("id", "project", "project_code", "task_code", "task_name", "assigned_to_id", "due_date", "priority", "actual_hours", "percent_complete", "status", "position", "version", "archived_at", "updated_at")


class TaskDetailSerializer(AllowedActionsMixin, serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()
    project_code = serializers.CharField(source="project.project_code", read_only=True)
    class Meta: model = Task; fields = ("id", "project", "project_code", "task_code", "task_name", "description", "assigned_to_id", "parent_task", "start_date", "due_date", "priority", "estimated_hours", "actual_hours", "percent_complete", "status", "position", "transition_history", "version", "archived_at", "created_at", "updated_at", "allowed_actions"); allowed_actions = ("update", "transition", "reorder", "archive")


class TaskCreateSerializer(StrictSerializer):
    project = serializers.UUIDField(); task_code = serializers.CharField(max_length=50); task_name = serializers.CharField(max_length=255); description = serializers.CharField(max_length=20000, required=False, allow_blank=True); assigned_to_id = serializers.UUIDField(required=False, allow_null=True); parent_task = serializers.UUIDField(required=False, allow_null=True); start_date = serializers.DateField(required=False, allow_null=True); due_date = serializers.DateField(required=False, allow_null=True); priority = serializers.ChoiceField(choices=("critical", "high", "medium", "low"), required=False); estimated_hours = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, allow_null=True, min_value=0); position = serializers.IntegerField(min_value=1, required=False)


class TaskUpdateSerializer(TaskCreateSerializer):
    project = serializers.UUIDField(required=False); task_code = serializers.CharField(max_length=50, required=False); task_name = serializers.CharField(max_length=255, required=False); version = serializers.IntegerField(min_value=1); idempotency_key = serializers.CharField(max_length=255)


class ProjectMemberListSerializer(serializers.ModelSerializer):
    project_code = serializers.CharField(source="project.project_code", read_only=True)
    class Meta: model = ProjectMember; fields = ("id", "project", "project_code", "employee_id", "role", "allocation_percentage", "joined_at", "left_at", "archived_at", "updated_at")


class ProjectMemberDetailSerializer(AllowedActionsMixin, ProjectMemberListSerializer):
    allowed_actions = serializers.SerializerMethodField()
    class Meta(ProjectMemberListSerializer.Meta): fields = ProjectMemberListSerializer.Meta.fields + ("created_at", "allowed_actions")


class ProjectMemberCreateSerializer(StrictSerializer):
    project = serializers.UUIDField(); employee_id = serializers.UUIDField(); role = serializers.ChoiceField(choices=("project_manager", "team_lead", "member", "stakeholder"), required=False); allocation_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0.01, max_value=100, required=False); joined_at = serializers.DateField(required=False); left_at = serializers.DateField(required=False, allow_null=True)


class ProjectMemberUpdateSerializer(StrictSerializer):
    role = serializers.ChoiceField(choices=("project_manager", "team_lead", "member", "stakeholder"), required=False); allocation_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0.01, max_value=100, required=False); joined_at = serializers.DateField(required=False); left_at = serializers.DateField(required=False, allow_null=True); idempotency_key = serializers.CharField(max_length=255)


class TimeEntryListSerializer(serializers.ModelSerializer):
    project_code = serializers.CharField(source="project.project_code", read_only=True); task_code = serializers.CharField(source="task.task_code", read_only=True, allow_null=True)
    class Meta: model = TimeEntry; fields = ("id", "project", "project_code", "task", "task_code", "employee_id", "entry_date", "hours_worked", "billable", "version", "archived_at", "created_at")


class TimeEntryDetailSerializer(AllowedActionsMixin, TimeEntryListSerializer):
    allowed_actions = serializers.SerializerMethodField()
    class Meta(TimeEntryListSerializer.Meta): fields = TimeEntryListSerializer.Meta.fields + ("description", "updated_at", "allowed_actions")


class TimeEntryCreateSerializer(StrictSerializer):
    project = serializers.UUIDField(); task = serializers.UUIDField(required=False, allow_null=True); employee_id = serializers.UUIDField(); entry_date = serializers.DateField(); hours_worked = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0.01, max_value=24); description = serializers.CharField(max_length=4000, required=False, allow_blank=True); billable = serializers.BooleanField(required=False)


class TimeEntryUpdateSerializer(TimeEntryCreateSerializer):
    project = serializers.UUIDField(required=False); employee_id = serializers.UUIDField(required=False); entry_date = serializers.DateField(required=False); hours_worked = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0.01, max_value=24, required=False); version = serializers.IntegerField(min_value=1); idempotency_key = serializers.CharField(max_length=255)


class ProjectMilestoneListSerializer(serializers.ModelSerializer):
    project_code = serializers.CharField(source="project.project_code", read_only=True)
    class Meta: model = ProjectMilestone; fields = ("id", "project", "project_code", "milestone_name", "target_date", "achieved_date", "cancelled_at", "version", "archived_at", "updated_at")


class ProjectMilestoneDetailSerializer(AllowedActionsMixin, ProjectMilestoneListSerializer):
    allowed_actions = serializers.SerializerMethodField()
    class Meta(ProjectMilestoneListSerializer.Meta): fields = ProjectMilestoneListSerializer.Meta.fields + ("description", "created_at", "allowed_actions")


class ProjectMilestoneCreateSerializer(StrictSerializer):
    project = serializers.UUIDField(); milestone_name = serializers.CharField(max_length=255); target_date = serializers.DateField(); description = serializers.CharField(max_length=10000, required=False, allow_blank=True)


class ProjectMilestoneUpdateSerializer(StrictSerializer):
    milestone_name = serializers.CharField(max_length=255, required=False); target_date = serializers.DateField(required=False); description = serializers.CharField(max_length=10000, required=False, allow_blank=True); version = serializers.IntegerField(min_value=1); idempotency_key = serializers.CharField(max_length=255)


class TransitionSerializer(StrictSerializer):
    transition_key = serializers.CharField(max_length=255); reason = serializers.CharField(max_length=1000, required=False, allow_blank=True); target_state = serializers.ChoiceField(choices=("todo", "in_progress"), required=False)
ProjectTransitionSerializer = TransitionSerializer
TaskTransitionSerializer = TransitionSerializer


class ArchiveRestoreSerializer(StrictSerializer):
    idempotency_key = serializers.CharField(max_length=255); version = serializers.IntegerField(min_value=1)


class IdempotencySerializer(StrictSerializer): idempotency_key = serializers.CharField(max_length=255)
class ReorderTaskSerializer(ArchiveRestoreSerializer): position = serializers.IntegerField(min_value=1)
class DuplicateProjectSerializer(IdempotencySerializer): project_code = serializers.CharField(max_length=50); project_name = serializers.CharField(max_length=255)
class MilestoneAchieveSerializer(IdempotencySerializer): achieved_date = serializers.DateField()


class ProjectActivitySerializer(serializers.ModelSerializer):
    class Meta: model = ProjectActivity; fields = ("id", "project", "entity_type", "entity_id", "action", "actor_id", "correlation_id", "before", "after", "metadata", "created_at")


class ConfigurationVersionSerializer(serializers.ModelSerializer):
    environment = serializers.CharField(source="configuration.environment", read_only=True)
    class Meta: model = ProjectManagementConfigurationVersion; fields = ("id", "environment", "version", "state", "default_currency", "project_code_pattern", "task_code_pattern", "max_daily_hours", "max_allocation_percentage", "enforce_project_date_bounds", "allow_future_time_entries", "require_time_description", "default_billable", "enabled_views", "paid_extension_rollout", "change_summary", "created_by_id", "created_at")


class ConfigurationDraftSerializer(StrictSerializer):
    environment = serializers.ChoiceField(choices=("development", "staging", "production")); values = serializers.DictField(); change_summary = serializers.CharField(max_length=500)
class ConfigurationSimulationSerializer(StrictSerializer): pass
class ConfigurationPublishSerializer(IdempotencySerializer): pass
class ConfigurationRollbackSerializer(IdempotencySerializer): target_version = serializers.IntegerField(min_value=1)
class ConfigurationImportSerializer(StrictSerializer): document = serializers.DictField()
class ConfigurationExportSerializer(StrictSerializer): environment = serializers.ChoiceField(choices=("development", "staging", "production"))


class ProjectSummarySerializer(StrictSerializer):
    project_id = serializers.UUIDField(); task_count = serializers.IntegerField(); completed_task_count = serializers.IntegerField(); blocked_task_count = serializers.IntegerField(); progress_percentage = serializers.DecimalField(max_digits=5, decimal_places=2); milestone_count = serializers.IntegerField(); achieved_milestone_count = serializers.IntegerField(); time_hours = serializers.DecimalField(max_digits=12, decimal_places=2); next_due_date = serializers.DateField(allow_null=True)

class PortfolioSummarySerializer(StrictSerializer):
    project_count=serializers.IntegerField();active_project_count=serializers.IntegerField();task_count=serializers.IntegerField();overdue_task_count=serializers.IntegerField();blocked_task_count=serializers.IntegerField();upcoming_milestone_count=serializers.IntegerField();budget_by_currency=serializers.ListField(child=serializers.DictField())

# Compatibility aliases for integrations using the former read serializer names.
ProjectSerializer = ProjectDetailSerializer
TaskSerializer = TaskDetailSerializer
ProjectMemberSerializer = ProjectMemberDetailSerializer
TimeEntrySerializer = TimeEntryDetailSerializer
ProjectMilestoneSerializer = ProjectMilestoneDetailSerializer
