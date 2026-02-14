"""
Model tests for Communication Hub module.
"""

import uuid
import pytest

from src.modules.communication_hub.models import Channel


@pytest.mark.django_db
class TestChannelModel:
    """Test Channel model."""

    def test_create_channel(self):
        """Test creating a channel."""
        tenant_id = uuid.uuid4()
        channel = Channel.objects.create(
            tenant_id=tenant_id,
            channel_code="CH-001",
            channel_name="Test Channel",
            channel_type="email",
        )
        assert channel.channel_code == "CH-001"
        assert channel.channel_type == "email"
        assert channel.is_active is True
