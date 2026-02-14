"""
Model tests for Project Management module.
"""

import uuid
import pytest
from datetime import date

from src.modules.project_management.models import Project, Task


@pytest.mark.django_db
class TestProjectModel:
    """Test Project model."""

    def test_create_project(self):
        """Test creating a project."""
        tenant_id = uuid.uuid4()
        project = Project.objects.create(
            tenant_id=tenant_id,
            project_code="PROJ-001",
            project_name="Test Project",
        )
        assert project.project_code == "PROJ-001"
        assert project.project_name == "Test Project"
        assert project.status == "planning"


@pytest.mark.django_db
class TestTaskModel:
    """Test Task model."""

    def test_create_task(self):
        """Test creating a task."""
        tenant_id = uuid.uuid4()
        project = Project.objects.create(
            tenant_id=tenant_id,
            project_code="PROJ-001",
            project_name="Test Project",
        )

        task = Task.objects.create(
            tenant_id=tenant_id,
            project=project,
            task_code="TASK-001",
            task_name="Test Task",
        )

        assert task.task_code == "TASK-001"
        assert task.project == project
        assert task.status == "todo"
