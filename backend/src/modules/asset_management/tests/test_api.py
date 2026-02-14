"""
API tests for Asset Management module.
"""

import uuid
import pytest
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.asset_management.models import Asset

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
class TestAssetAPI:
    """Test Asset API endpoints."""

    def test_list_assets(self, api_client, authenticated_user):
        """Test listing assets."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)

        Asset.objects.create(
            tenant_id=tenant_id,
            asset_code="AST-001",
            asset_name="Test Asset",
            purchase_date=date(2024, 1, 1),
            purchase_cost=Decimal("10000.00"),
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v1/asset-management/assets/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0

    def test_create_asset(self, api_client, authenticated_user):
        """Test creating an asset."""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "asset_code": "AST-002",
            "asset_name": "Another Asset",
            "purchase_date": "2024-01-01",
            "purchase_cost": "15000.00",
        }

        response = api_client.post("/api/v1/asset-management/assets/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["asset_code"] == "AST-002"
