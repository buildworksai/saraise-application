"""
DRF Serializers for Communication Hub module.
"""

from rest_framework import serializers

from .models import Channel, Message


class ChannelSerializer(serializers.ModelSerializer):
    """Channel serializer."""

    class Meta:
        model = Channel
        fields = [
            "id",
            "tenant_id",
            "channel_code",
            "channel_name",
            "channel_type",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class MessageSerializer(serializers.ModelSerializer):
    """Message serializer."""

    channel_code = serializers.CharField(source="channel.channel_code", read_only=True)
    channel_name = serializers.CharField(source="channel.channel_name", read_only=True)

    class Meta:
        model = Message
        fields = [
            "id",
            "tenant_id",
            "channel",
            "channel_code",
            "channel_name",
            "sender_id",
            "recipient_id",
            "subject",
            "body",
            "message_type",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]
