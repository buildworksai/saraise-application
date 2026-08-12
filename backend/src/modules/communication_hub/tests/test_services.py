"""
Service tests for Communication Hub module.
"""

import uuid

import pytest

from src.modules.communication_hub.services import ChannelService, MessageService


@pytest.mark.django_db
class TestChannelService:
    """Test ChannelService."""

    def test_create_channel(self) -> None:
        """Test creating a channel via service."""
        tenant_id = uuid.uuid4()
        channel = ChannelService.create_channel(
            tenant_id=str(tenant_id),
            channel_code="CH-001",
            channel_name="Test Channel",
            channel_type="email",
        )

        assert channel.channel_code == "CH-001"
        assert channel.channel_name == "Test Channel"
        assert channel.channel_type == "email"
        assert str(channel.tenant_id) == str(tenant_id)

    def test_create_channel_supports_instance_service_call(self) -> None:
        """Test static service contract remains valid when the service is instantiated."""
        tenant_id = uuid.uuid4()

        channel = ChannelService().create_channel(
            tenant_id=str(tenant_id),
            channel_code="CH-004",
            channel_name="Instance Channel",
            channel_type="chat",
        )

        assert channel.channel_code == "CH-004"
        assert channel.channel_name == "Instance Channel"
        assert channel.channel_type == "chat"
        assert str(channel.tenant_id) == str(tenant_id)

    def test_create_channel_persists_optional_fields(self) -> None:
        """Test service keyword passthrough for governed channel fields."""
        tenant_id = uuid.uuid4()

        channel = ChannelService.create_channel(
            tenant_id=str(tenant_id),
            channel_code="CH-002",
            channel_name="Disabled SMS",
            channel_type="sms",
            is_active=False,
        )

        assert channel.channel_code == "CH-002"
        assert channel.channel_name == "Disabled SMS"
        assert channel.channel_type == "sms"
        assert channel.is_active is False
        assert str(channel.tenant_id) == str(tenant_id)

    def test_create_message_persists_required_and_optional_fields(self) -> None:
        """Test creating a tenant-scoped message via service."""
        tenant_id = uuid.uuid4()
        sender_id = uuid.uuid4()
        recipient_id = uuid.uuid4()
        channel = ChannelService.create_channel(
            tenant_id=str(tenant_id),
            channel_code="CH-003",
            channel_name="Support Email",
            channel_type="email",
        )

        message = MessageService.create_message(
            tenant_id=str(tenant_id),
            channel_id=str(channel.id),
            sender_id=str(sender_id),
            body="Escalation accepted",
            recipient_id=str(recipient_id),
            subject="Case update",
            message_type="email",
            status="delivered",
        )

        assert str(message.tenant_id) == str(tenant_id)
        assert str(message.channel_id) == str(channel.id)
        assert str(message.sender_id) == str(sender_id)
        assert str(message.recipient_id) == str(recipient_id)
        assert message.subject == "Case update"
        assert message.body == "Escalation accepted"
        assert message.message_type == "email"
        assert message.status == "delivered"

    def test_create_message_supports_instance_service_call(self) -> None:
        """Test static message service contract remains valid when instantiated."""
        tenant_id = uuid.uuid4()
        sender_id = uuid.uuid4()
        channel = ChannelService.create_channel(
            tenant_id=str(tenant_id),
            channel_code="CH-005",
            channel_name="Instance Message Channel",
            channel_type="chat",
        )

        message = MessageService().create_message(
            tenant_id=str(tenant_id),
            channel_id=str(channel.id),
            sender_id=str(sender_id),
            body="Instance dispatch",
        )

        assert str(message.tenant_id) == str(tenant_id)
        assert str(message.channel_id) == str(channel.id)
        assert str(message.sender_id) == str(sender_id)
        assert message.body == "Instance dispatch"
        assert message.message_type == "text"
        assert message.status == "sent"
