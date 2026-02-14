"""
Service tests for Communication Hub module.
"""

import uuid
import pytest

from src.modules.communication_hub.models import Channel
from src.modules.communication_hub.services import ChannelService


@pytest.mark.django_db
class TestChannelService:
    """Test ChannelService."""

    def test_create_channel(self):
        """Test creating a channel via service."""
        tenant_id = uuid.uuid4()
        channel = ChannelService.create_channel(
            tenant_id=str(tenant_id),
            channel_code="CH-001",
            channel_name="Test Channel",
            channel_type="email",
        )

        assert channel.channel_code == "CH-001"
        assert channel.channel_type == "email"
        assert str(channel.tenant_id) == str(tenant_id)
