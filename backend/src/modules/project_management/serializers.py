"""
DRF Serializers for Project Management module.
"""

from rest_framework import serializers

from .models import Project, ProjectMember, ProjectMilestone, Task, TimeEntry


class ProjectSerializer(serializers.ModelSerializer):
    """Project serializer."""

    class Meta:
        model = Project
        fields = [
            "id",
            "tenant_id",
            "project_code",
            "project_name",
            "description",
            "start_date",
            "end_date",
            "status",
            "project_manager_id",
            "budget",
            "currency",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class TaskSerializer(serializers.ModelSerializer):
    """Task serializer."""

    project_code = serializers.CharField(source="project.project_code", read_only=True)
    project_name = serializers.CharField(source="project.project_name", read_only=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "tenant_id",
            "project",
            "project_code",
            "project_name",
            "task_code",
            "task_name",
            "description",
            "assigned_to_id",
            "due_date",
            "estimated_hours",
            "actual_hours",
            "status",
            "parent_task_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "actual_hours", "created_at", "updated_at"]


class ProjectMemberSerializer(serializers.ModelSerializer):
    """ProjectMember serializer."""

    project_code = serializers.CharField(source="project.project_code", read_only=True)
    project_name = serializers.CharField(source="project.project_name", read_only=True)

    class Meta:
        model = ProjectMember
        fields = [
            "id",
            "tenant_id",
            "project",
            "project_code",
            "project_name",
            "employee_id",
            "role",
            "allocation_percentage",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class TimeEntrySerializer(serializers.ModelSerializer):
    """TimeEntry serializer."""

    project_code = serializers.CharField(source="project.project_code", read_only=True)
    task_code = serializers.CharField(source="task.task_code", read_only=True, allow_null=True)

    class Meta:
        model = TimeEntry
        fields = [
            "id",
            "tenant_id",
            "project",
            "project_code",
            "task",
            "task_code",
            "employee_id",
            "entry_date",
            "hours_worked",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class ProjectMilestoneSerializer(serializers.ModelSerializer):
    """ProjectMilestone serializer."""

    project_code = serializers.CharField(source="project.project_code", read_only=True)

    class Meta:
        model = ProjectMilestone
        fields = [
            "id",
            "tenant_id",
            "project",
            "project_code",
            "milestone_name",
            "target_date",
            "achieved_date",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]
