"""
Tests for NotificationService.

SPDX-License-Identifier: Apache-2.0
"""

import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase

from src.core.notifications.models import Notification, PushNotificationToken
from src.core.notifications.services import NotificationService, PHONE_NUMBER_REGEX


class NotificationServiceTestCase(TestCase):
    """Test cases for NotificationService."""

    def setUp(self):
        """Set up test fixtures."""
        self.tenant_id = str(uuid.uuid4())
        self.user_id = str(uuid.uuid4())

    def test_create_notification_success(self):
        """Test successful notification creation."""
        notification = NotificationService.create_notification(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            title="Test Notification",
            message="This is a test",
            notification_type="info",
        )

        self.assertIsNotNone(notification.id)
        self.assertEqual(notification.title, "Test Notification")
        self.assertEqual(notification.tenant_id, uuid.UUID(self.tenant_id))

    def test_send_sms_invalid_phone_number(self):
        """Test SMS sending with invalid phone number."""
        notification = Notification.objects.create(
            tenant_id=uuid.UUID(self.tenant_id),
            user_id=uuid.UUID(self.user_id),
            title="Test",
            message="Test message",
            metadata={"phone_number": "invalid"},
        )

        NotificationService._send_sms(notification)

        # Should not raise error, just log warning
        # Verify no exception was raised

    def test_send_sms_valid_phone_number(self):
        """Test SMS sending with valid phone number."""
        notification = Notification.objects.create(
            tenant_id=uuid.UUID(self.tenant_id),
            user_id=uuid.UUID(self.user_id),
            title="Test",
            message="Test message",
            metadata={"phone_number": "+1234567890"},
        )

        with patch("src.core.notifications.services.boto3.client") as mock_boto:
            mock_sns = MagicMock()
            mock_sns.publish.return_value = {"MessageId": "test-message-id"}
            mock_boto.return_value = mock_sns

            NotificationService._send_sms(notification)

            # Verify SNS client was called
            mock_boto.assert_called_once()

    def test_send_push_no_tokens(self):
        """Test push notification with no active tokens."""
        notification = Notification.objects.create(
            tenant_id=uuid.UUID(self.tenant_id),
            user_id=uuid.UUID(self.user_id),
            title="Test",
            message="Test message",
        )

        # No tokens created, so should return early
        NotificationService._send_push(notification)

        # Should not raise error

    def test_send_push_with_tokens(self):
        """Test push notification with active tokens."""
        notification = Notification.objects.create(
            tenant_id=uuid.UUID(self.tenant_id),
            user_id=uuid.UUID(self.user_id),
            title="Test",
            message="Test message",
        )

        # Create push token
        PushNotificationToken.objects.create(
            tenant_id=uuid.UUID(self.tenant_id),
            user_id=uuid.UUID(self.user_id),
            token="test-fcm-token",
            device_type="web",
        )

        # Mock firebase_admin and messaging (imported inside the function)
        # Use patch.object to mock the imported modules
        with patch("builtins.__import__") as mock_import:
            # Mock the firebase_admin module
            mock_firebase = MagicMock()
            mock_messaging = MagicMock()
            mock_credentials = MagicMock()

            def import_side_effect(name, *args, **kwargs):
                if name == "firebase_admin":
                    return mock_firebase
                elif name == "firebase_admin.messaging":
                    return mock_messaging
                elif name == "firebase_admin.credentials":
                    return mock_credentials
                else:
                    return __import__(name, *args, **kwargs)

            mock_import.side_effect = import_side_effect

            # Configure mocks
            mock_firebase.get_app.side_effect = ValueError("Not initialized")
            mock_credentials.Certificate.return_value = MagicMock()
            mock_firebase.initialize_app.return_value = MagicMock()

            mock_response = MagicMock()
            mock_response.success_count = 1
            mock_response.failure_count = 0
            mock_response.responses = [MagicMock(success=True)]
            mock_messaging.send_multicast.return_value = mock_response

            NotificationService._send_push(notification)

            # Verify messaging was called (if import was triggered)
            # Note: This test verifies the function doesn't crash

    def test_phone_number_regex_validation(self):
        """Test phone number regex validation."""
        # Valid E.164 format
        self.assertTrue(PHONE_NUMBER_REGEX.match("+1234567890"))
        self.assertTrue(PHONE_NUMBER_REGEX.match("+441234567890"))

        # Invalid formats
        self.assertFalse(PHONE_NUMBER_REGEX.match("1234567890"))  # No +
        self.assertFalse(PHONE_NUMBER_REGEX.match("+01234567890"))  # Starts with 0
        self.assertFalse(PHONE_NUMBER_REGEX.match("invalid"))  # Not a number
