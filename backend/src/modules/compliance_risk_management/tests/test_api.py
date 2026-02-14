"""
API tests for Compliance Risk Management module.
"""

import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.compliance_risk_management.models import ComplianceRisk

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
class TestComplianceRiskAPI:
    """Test ComplianceRisk API endpoints."""

    def test_list_risks(self, api_client, authenticated_user):
        """Test listing risks."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)

        ComplianceRisk.objects.create(
            tenant_id=tenant_id,
            risk_code="RISK-001",
            risk_name="Test Risk",
            risk_level="high",
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v1/compliance-risk-management/risks/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0

    def test_create_risk(self, api_client, authenticated_user):
        """Test creating a risk."""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "risk_code": "RISK-002",
            "risk_name": "Another Risk",
            "risk_level": "medium",
        }

        response = api_client.post("/api/v1/compliance-risk-management/risks/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["risk_code"] == "RISK-002"
