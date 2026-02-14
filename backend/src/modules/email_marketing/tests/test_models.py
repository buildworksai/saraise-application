"""
Model tests for Email Marketing module.
"""

import uuid
import pytest

from src.modules.email_marketing.models import EmailCampaign


@pytest.mark.django_db
class TestEmailCampaignModel:
    """Test EmailCampaign model."""

    def test_create_campaign(self):
        """Test creating an email campaign."""
        tenant_id = uuid.uuid4()
        campaign = EmailCampaign.objects.create(
            tenant_id=tenant_id,
            campaign_code="CAMP-001",
            campaign_name="Test Campaign",
            subject="Test Subject",
        )
        assert campaign.campaign_code == "CAMP-001"
        assert campaign.status == "draft"
        assert campaign.recipient_count == 0
