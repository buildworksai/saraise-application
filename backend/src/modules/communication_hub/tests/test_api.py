"""
API tests for Communication Hub module.
"""

import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.communication_hub.models import Channel

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
class TestChannelAPI:
    """Test Channel API endpoints."""

    def test_list_channels(self, api_client, authenticated_user):
        """Test listing channels."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)

        Channel.objects.create(
            tenant_id=tenant_id,
            channel_code="CH-001",
            channel_name="Test Channel",
            channel_type="email",
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v1/communication-hub/channels/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0

    def test_create_channel(self, api_client, authenticated_user):
        """Test creating a channel."""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "channel_code": "CH-002",
            "channel_name": "Another Channel",
            "channel_type": "sms",
        }

        response = api_client.post("/api/v1/communication-hub/channels/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["channel_code"] == "CH-002"
