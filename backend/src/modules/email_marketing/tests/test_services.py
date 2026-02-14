"""
Service tests for Email Marketing module.
"""

import uuid
import pytest

from src.modules.email_marketing.models import EmailCampaign
from src.modules.email_marketing.services import EmailCampaignService


@pytest.mark.django_db
class TestEmailCampaignService:
    """Test EmailCampaignService."""

    def test_create_campaign(self):
        """Test creating a campaign via service."""
        tenant_id = uuid.uuid4()
        campaign = EmailCampaignService.create_campaign(
            tenant_id=str(tenant_id),
            campaign_code="CAMP-001",
            campaign_name="Test Campaign",
            subject="Test Subject",
        )

        assert campaign.campaign_code == "CAMP-001"
        assert campaign.campaign_name == "Test Campaign"
        assert str(campaign.tenant_id) == str(tenant_id)
