"""
API tests for Project Management module.
"""

import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.project_management.models import Project

User = get_user_model()


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def authenticated_user(db):
    """Create authenticated user with tenant."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    return User.objects.get(pk=user.pk)


@pytest.mark.django_db
class TestProjectAPI:
    """Test Project API endpoints."""

    def test_list_projects(self, api_client, authenticated_user):
        """Test listing projects."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)

        Project.objects.create(
            tenant_id=tenant_id,
            project_code="PROJ-001",
            project_name="Test Project",
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v1/project-management/projects/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0

    def test_create_project(self, api_client, authenticated_user):
        """Test creating a project."""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "project_code": "PROJ-002",
            "project_name": "Another Project",
        }

        response = api_client.post("/api/v1/project-management/projects/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["project_code"] == "PROJ-002"
