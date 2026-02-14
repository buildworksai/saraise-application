"""
API tests for Compliance Management module.
"""

import uuid
import pytest
from datetime import date
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.compliance_management.models import CompliancePolicy

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
class TestCompliancePolicyAPI:
    """Test CompliancePolicy API endpoints."""

    def test_list_policies(self, api_client, authenticated_user):
        """Test listing policies."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)

        CompliancePolicy.objects.create(
            tenant_id=tenant_id,
            policy_code="POL-001",
            policy_name="Test Policy",
            regulation_type="GDPR",
            effective_date=date(2024, 1, 1),
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v1/compliance-management/policies/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0

    def test_create_policy(self, api_client, authenticated_user):
        """Test creating a policy."""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "policy_code": "POL-002",
            "policy_name": "Another Policy",
            "regulation_type": "SOX",
            "effective_date": "2024-01-01",
        }

        response = api_client.post("/api/v1/compliance-management/policies/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["policy_code"] == "POL-002"
