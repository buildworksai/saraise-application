"""
DRF Serializers for Notifications module.
"""

from rest_framework import serializers

from .models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    """Notification serializer."""

    class Meta:
        model = Notification
        fields = [
            "id",
            "tenant_id",
            "user_id",
            "notification_type",
            "title",
            "message",
            "status",
            "read_at",
            "action_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "user_id", "read_at", "created_at", "updated_at"]


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """NotificationPreference serializer."""

    class Meta:
        model = NotificationPreference
        fields = [
            "id",
            "tenant_id",
            "user_id",
            "channel",
            "notification_type",
            "enabled",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "user_id", "created_at", "updated_at"]
