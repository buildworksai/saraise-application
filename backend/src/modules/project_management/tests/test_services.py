"""
Service tests for Project Management module.
"""

import uuid
import pytest

from src.modules.project_management.models import Project
from src.modules.project_management.services import ProjectService


@pytest.mark.django_db
class TestProjectService:
    """Test ProjectService."""

    def test_create_project(self):
        """Test creating a project via service."""
        tenant_id = uuid.uuid4()
        project = ProjectService.create_project(
            tenant_id=str(tenant_id),
            project_code="PROJ-001",
            project_name="Test Project",
        )

        assert project.project_code == "PROJ-001"
        assert project.project_name == "Test Project"
        assert str(project.tenant_id) == str(tenant_id)
