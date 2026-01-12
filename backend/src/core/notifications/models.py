"""
Notification Models.

SPDX-License-Identifier: Apache-2.0
"""

import uuid

from django.db import models
from django.utils import timezone


class TenantBaseModel(models.Model):
    """Base model for tenant-scoped models."""

    tenant_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class Notification(TenantBaseModel):
    """In-app notification model."""

    NOTIFICATION_TYPE_CHOICES = [
        ("info", "Information"),
        ("success", "Success"),
        ("warning", "Warning"),
        ("error", "Error"),
        ("workflow", "Workflow"),
        ("approval", "Approval"),
        ("system", "System"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(db_index=True, help_text="User who receives the notification")
    type = models.CharField(max_length=20, choices=NOTIFICATION_TYPE_CHOICES, default="info")
    title = models.CharField(max_length=255)
    message = models.TextField()
    read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    action_url = models.URLField(blank=True, help_text="Optional URL for action button")
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional metadata")

    class Meta:
        db_table = "notifications"
        indexes = [
            models.Index(fields=["tenant_id", "user_id", "read"]),
            models.Index(fields=["tenant_id", "user_id", "created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({'read' if self.read else 'unread'})"

    def mark_as_read(self):
        """Mark notification as read."""
        self.read = True
        self.read_at = timezone.now()
        self.save(update_fields=["read", "read_at"])


class NotificationPreference(TenantBaseModel):
    """User notification preferences."""

    CHANNEL_CHOICES = [
        ("in_app", "In-App"),
        ("email", "Email"),
        ("sms", "SMS"),
        ("push", "Push Notification"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(db_index=True, unique=True, help_text="User ID")
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)
    push_enabled = models.BooleanField(default=True)
    in_app_enabled = models.BooleanField(default=True)

    # Per-type preferences
    workflow_notifications = models.BooleanField(default=True)
    approval_notifications = models.BooleanField(default=True)
    system_notifications = models.BooleanField(default=True)

    class Meta:
        db_table = "notification_preferences"
        indexes = [
            models.Index(fields=["tenant_id", "user_id"]),
        ]

    def __str__(self):
        return f"Preferences for user {self.user_id}"


class PushNotificationToken(TenantBaseModel):
    """FCM push notification token storage."""

    DEVICE_TYPE_CHOICES = [
        ("web", "Web Browser"),
        ("android", "Android"),
        ("ios", "iOS"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(db_index=True, help_text="User ID")
    token = models.TextField(help_text="FCM registration token")
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPE_CHOICES, default="web")
    device_id = models.CharField(max_length=255, blank=True, help_text="Device identifier")
    is_active = models.BooleanField(default=True, db_index=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "push_notification_tokens"
        unique_together = [["tenant_id", "user_id", "token"]]
        indexes = [
            models.Index(fields=["tenant_id", "user_id", "is_active"]),
            models.Index(fields=["tenant_id", "token"]),
        ]

    def __str__(self):
        return f"Push token for user {self.user_id} ({self.device_type})"
