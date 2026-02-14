"""
Model tests for Notifications module.
"""

import uuid
import pytest

from src.modules.notifications.models import Notification


@pytest.mark.django_db
class TestNotificationModel:
    """Test Notification model."""

    def test_create_notification(self):
        """Test creating a notification."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        notification = Notification.objects.create(
            tenant_id=tenant_id,
            user_id=user_id,
            title="Test Notification",
            message="Test message",
        )
        assert notification.title == "Test Notification"
        assert notification.status == "unread"
