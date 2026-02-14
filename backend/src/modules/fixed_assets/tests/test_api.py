"""
API tests for Fixed Assets module.
"""

import uuid
import pytest
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.fixed_assets.models import FixedAsset

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
class TestFixedAssetAPI:
    """Test FixedAsset API endpoints."""

    def test_list_fixed_assets(self, api_client, authenticated_user):
        """Test listing fixed assets."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)

        FixedAsset.objects.create(
            tenant_id=tenant_id,
            asset_code="FA-001",
            asset_name="Test Fixed Asset",
            asset_category="machinery",
            purchase_date=date(2024, 1, 1),
            purchase_cost=Decimal("50000.00"),
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v1/fixed-assets/assets/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0

    def test_create_fixed_asset(self, api_client, authenticated_user):
        """Test creating a fixed asset."""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "asset_code": "FA-002",
            "asset_name": "Another Fixed Asset",
            "asset_category": "vehicle",
            "purchase_date": "2024-01-01",
            "purchase_cost": "30000.00",
        }

        response = api_client.post("/api/v1/fixed-assets/assets/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["asset_code"] == "FA-002"
