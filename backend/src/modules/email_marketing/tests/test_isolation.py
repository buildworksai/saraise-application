"""
Tenant Isolation Tests for Email Marketing module.
"""

import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.modules.email_marketing.models import EmailCampaign

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
def tenant_a_user(db):
    """Create user for tenant A."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_a",
        email="usera@example.com",
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


@pytest.fixture
def tenant_b_user(db):
    """Create user for tenant B."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_b",
        email="userb@example.com",
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
class TestEmailCampaignTenantIsolation:
    """CRITICAL: Tenant isolation tests for EmailCampaign model."""

    def test_user_cannot_list_other_tenant_campaigns(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's campaigns in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create campaign for tenant A
        campaign_a = EmailCampaign.objects.create(
            tenant_id=tenant_a_id,
            campaign_code="CAMP-A",
            campaign_name="Campaign A",
            subject="Test Subject A",
        )

        # Create campaign for tenant B
        campaign_b = EmailCampaign.objects.create(
            tenant_id=tenant_b_id,
            campaign_code="CAMP-B",
            campaign_name="Campaign B",
            subject="Test Subject B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/email-marketing/campaigns/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        campaign_ids = [c["id"] for c in data]

        # User A should see tenant A's campaign, but NOT tenant B's campaign
        assert str(campaign_a.id) in campaign_ids
        assert str(campaign_b.id) not in campaign_ids

    def test_user_cannot_get_other_tenant_campaign_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's campaign by ID (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create campaign for tenant B
        campaign_b = EmailCampaign.objects.create(
            tenant_id=tenant_b_id,
            campaign_code="CAMP-B",
            campaign_name="Campaign B",
            subject="Test Subject B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's campaign
        response = api_client.get(f"/api/v1/email-marketing/campaigns/{campaign_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
