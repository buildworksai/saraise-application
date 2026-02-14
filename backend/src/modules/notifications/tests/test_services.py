"""
Service tests for Notifications module.
"""

import uuid
import pytest

from src.modules.notifications.models import Notification
from src.modules.notifications.services import NotificationService


@pytest.mark.django_db
class TestNotificationService:
    """Test NotificationService."""

    def test_create_notification(self):
        """Test creating a notification via service."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        notification = NotificationService.create_notification(
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            title="Test Notification",
            message="Test message",
        )

        assert notification.title == "Test Notification"
        assert notification.tenant_id == tenant_id
        assert notification.user_id == user_id
