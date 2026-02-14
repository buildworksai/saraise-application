"""
Notifications Models.

Defines data models for notifications and user preferences.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from django.db import models


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class TenantBaseModel(models.Model):
    """Base model for tenant-scoped models with Row-Level Multitenancy.

    CRITICAL: All tenant-scoped models MUST inherit from this base class
    and include tenant_id. All queries MUST filter explicitly by tenant_id.
    """

    tenant_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class NotificationType(models.TextChoices):
    """Notification type choices."""

    INFO = "info", "Information"
    WARNING = "warning", "Warning"
    ERROR = "error", "Error"
    SUCCESS = "success", "Success"


class NotificationStatus(models.TextChoices):
    """Notification status choices."""

    UNREAD = "unread", "Unread"
    READ = "read", "Read"
    ARCHIVED = "archived", "Archived"


class Notification(TenantBaseModel):
    """Notification model - User notification."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    user_id = models.UUIDField(db_index=True, help_text="FK to user")
    notification_type = models.CharField(max_length=20, choices=NotificationType.choices, default=NotificationType.INFO)
    title = models.CharField(max_length=255)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=NotificationStatus.choices, default=NotificationStatus.UNREAD, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    action_url = models.URLField(max_length=500, blank=True)

    class Meta:
        db_table = "notifications_notifications"
        indexes = [
            models.Index(fields=["tenant_id", "user_id"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "user_id", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} - {self.user_id}"


class NotificationPreference(TenantBaseModel):
    """Notification preference model - User notification preferences."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    user_id = models.UUIDField(db_index=True, help_text="FK to user")
    channel = models.CharField(max_length=50, db_index=True)  # email, sms, push, in_app
    notification_type = models.CharField(max_length=50, db_index=True)  # system, task, approval, etc.
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "notifications_preferences"
        indexes = [
            models.Index(fields=["tenant_id", "user_id"]),
            models.Index(fields=["tenant_id", "channel"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "user_id", "channel", "notification_type"], name="unique_preference_per_user"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} - {self.channel} - {self.notification_type}"
