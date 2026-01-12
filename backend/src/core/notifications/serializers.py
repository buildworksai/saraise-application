"""
Notification Serializers.

SPDX-License-Identifier: Apache-2.0
"""

from rest_framework import serializers

from .models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for Notification model."""

    class Meta:
        model = Notification
        fields = [
            "id",
            "tenant_id",
            "user_id",
            "type",
            "title",
            "message",
            "read",
            "read_at",
            "action_url",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "user_id", "created_at", "updated_at", "read_at"]


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for NotificationPreference model."""

    class Meta:
        model = NotificationPreference
        fields = [
            "id",
            "tenant_id",
            "user_id",
            "email_enabled",
            "sms_enabled",
            "push_enabled",
            "in_app_enabled",
            "workflow_notifications",
            "approval_notifications",
            "system_notifications",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "user_id", "created_at", "updated_at"]
