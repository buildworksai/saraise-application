"""
Business logic services for Communication Hub module.
"""

from .models import Channel, Message


class ChannelService:
    """Service for channel operations."""

    @staticmethod
    def create_channel(tenant_id: str, channel_code: str, channel_name: str, channel_type: str, **kwargs) -> Channel:
        """Create a new channel."""
        return Channel.objects.create(
            tenant_id=tenant_id,
            channel_code=channel_code,
            channel_name=channel_name,
            channel_type=channel_type,
            **kwargs,
        )


class MessageService:
    """Service for message operations."""

    @staticmethod
    def create_message(tenant_id: str, channel_id: str, sender_id: str, body: str, **kwargs) -> Message:
        """Create a new message."""
        return Message.objects.create(
            tenant_id=tenant_id,
            channel_id=channel_id,
            sender_id=sender_id,
            body=body,
            **kwargs,
        )
