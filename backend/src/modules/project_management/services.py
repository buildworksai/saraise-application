"""
Business logic services for Project Management module.
"""

from typing import Optional

from django.db import models, transaction

from .models import Project, Task, TimeEntry


class ProjectService:
    """Service for project operations."""

    @staticmethod
    def create_project(tenant_id: str, project_code: str, project_name: str, **kwargs) -> Project:
        """Create a new project."""
        return Project.objects.create(
            tenant_id=tenant_id,
            project_code=project_code,
            project_name=project_name,
            **kwargs,
        )


class TaskService:
    """Service for task operations."""

    @staticmethod
    @transaction.atomic
    def update_task_hours(task: Task) -> Task:
        """Update task actual hours from time entries."""
        total_hours = TimeEntry.objects.filter(task=task).aggregate(total=models.Sum("hours_worked"))["total"] or 0
        task.actual_hours = total_hours
        task.save()
        return task


class TimeEntryService:
    """Service for time entry operations."""

    @staticmethod
    @transaction.atomic
    def create_time_entry(
        tenant_id: str, project_id: str, employee_id: str, entry_date: str, hours_worked: float, **kwargs
    ) -> TimeEntry:
        """Create a new time entry and update task hours."""
        time_entry = TimeEntry.objects.create(
            tenant_id=tenant_id,
            project_id=project_id,
            employee_id=employee_id,
            entry_date=entry_date,
            hours_worked=hours_worked,
            **kwargs,
        )

        # Update task actual hours if task is specified
        if time_entry.task:
            from .services import TaskService

            TaskService.update_task_hours(time_entry.task)

        return time_entry
