"""
API tests for Master Data Management module.
"""

import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.master_data_management.models import MasterDataEntity

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
class TestMasterDataEntityAPI:
    """Test MasterDataEntity API endpoints."""

    def test_list_entities(self, api_client, authenticated_user):
        """Test listing entities."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)

        MasterDataEntity.objects.create(
            tenant_id=tenant_id,
            entity_type="customer",
            entity_code="CUST-001",
            entity_name="Test Customer",
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v1/master-data-management/entities/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0

    def test_create_entity(self, api_client, authenticated_user):
        """Test creating an entity."""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "entity_type": "supplier",
            "entity_code": "SUP-001",
            "entity_name": "Test Supplier",
        }

        response = api_client.post("/api/v1/master-data-management/entities/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["entity_code"] == "SUP-001"
