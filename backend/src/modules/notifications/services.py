"""
Business logic services for Notifications module.
"""

from typing import Optional
from django.utils import timezone

from .models import Notification


class NotificationService:
    """Service for notification operations."""

    @staticmethod
    def create_notification(
        tenant_id: str,
        user_id: str,
        title: str,
        message: str,
        notification_type: str = "info",
        **kwargs
    ) -> Notification:
        """Create a new notification."""
        return Notification.objects.create(
            tenant_id=tenant_id,
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            **kwargs,
        )

    @staticmethod
    def mark_as_read(notification: Notification) -> Notification:
        """Mark a notification as read."""
        notification.status = "read"
        notification.read_at = timezone.now()
        notification.save()
        return notification
