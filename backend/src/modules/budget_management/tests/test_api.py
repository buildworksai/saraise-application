"""
API tests for Budget Management module.
"""

import uuid
import pytest
from datetime import date
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.budget_management.models import Budget

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
class TestBudgetAPI:
    """Test Budget API endpoints."""

    def test_list_budgets(self, api_client, authenticated_user):
        """Test listing budgets."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)

        Budget.objects.create(
            tenant_id=tenant_id,
            budget_code="BUD-001",
            budget_name="Test Budget",
            fiscal_year=2024,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v1/budget-management/budgets/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0

    def test_create_budget(self, api_client, authenticated_user):
        """Test creating a budget."""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "budget_code": "BUD-002",
            "budget_name": "Another Budget",
            "fiscal_year": 2024,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }

        response = api_client.post("/api/v1/budget-management/budgets/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["budget_code"] == "BUD-002"
