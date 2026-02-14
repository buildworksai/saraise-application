"""
API tests for Multi-Company module.
"""

import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.multi_company.models import Company

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
class TestCompanyAPI:
    """Test Company API endpoints."""

    def test_list_companies(self, api_client, authenticated_user):
        """Test listing companies."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)

        Company.objects.create(
            tenant_id=tenant_id,
            company_code="COMP-001",
            company_name="Test Company",
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v1/multi-company/companies/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0

    def test_create_company(self, api_client, authenticated_user):
        """Test creating a company."""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "company_code": "COMP-002",
            "company_name": "Another Company",
        }

        response = api_client.post("/api/v1/multi-company/companies/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["company_code"] == "COMP-002"
