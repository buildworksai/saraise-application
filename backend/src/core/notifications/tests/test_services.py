"""
Tests for NotificationService.

SPDX-License-Identifier: Apache-2.0
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError
from cryptography.fernet import Fernet
from django.test import TestCase

from src.core.encryption import EncryptionService
from src.core.notifications.services import (
    PHONE_NUMBER_REGEX,
    NotificationService,
    _convert_tenant_id_to_uuid,
    _convert_user_id_to_uuid,
)
from src.modules.notifications.models import Notification, NotificationEndpoint, NotificationPreference


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
        self.assertEqual(notification.notification_type, "info")
        self.assertEqual(notification.status, "unread")

    def test_create_notification_rejects_invalid_identity(self):
        """Invalid legacy identity values fail before persistence."""
        with self.assertRaises(ValueError):
            NotificationService.create_notification("not-a-tenant", self.user_id, "Bad", "Bad")
        with self.assertRaises(ValueError):
            NotificationService.create_notification(self.tenant_id, "", "Bad", "Bad")

    def test_external_delivery_honors_category_and_channel_preferences(self):
        """Legacy fan-out reads canonical v2 preferences before dispatching."""
        tenant = uuid.UUID(self.tenant_id)
        user = uuid.UUID(self.user_id)
        notification = Notification.objects.create(
            tenant_id=tenant,
            user_id=user,
            title="Preference",
            message="Preference",
            category="workflow",
            metadata={"user_email": "ops@example.test", "phone_number": "+1234567890"},
        )
        NotificationPreference.objects.create(
            tenant_id=tenant,
            user_id=user,
            channel="email",
            category="workflow",
            enabled=False,
        )
        NotificationPreference.objects.create(
            tenant_id=tenant,
            user_id=user,
            channel="sms",
            category="workflow",
            enabled=True,
        )

        with (
            patch.object(NotificationService, "_send_email") as email,
            patch.object(NotificationService, "_send_sms") as sms,
            patch.object(NotificationService, "_send_push") as push,
        ):
            NotificationService._send_external_notifications(notification)

        email.assert_not_called()
        sms.assert_called_once_with(notification)
        push.assert_called_once_with(notification)

        NotificationPreference.objects.filter(tenant_id=tenant, user_id=user, category="workflow").update(enabled=False)
        with patch.object(NotificationService, "_send_sms") as sms:
            NotificationService._send_external_notifications(notification)
        sms.assert_not_called()

    def test_send_email_requires_metadata_email_and_uses_configured_sender(self):
        """Email delivery is explicit about missing recipient metadata."""
        notification = Notification.objects.create(
            tenant_id=uuid.UUID(self.tenant_id),
            user_id=uuid.UUID(self.user_id),
            title="Email",
            message="Email body",
            metadata={"user_email": "ops@example.test"},
        )

        with patch("src.core.notifications.services.send_mail") as send_mail:
            NotificationService._send_email(notification)

        send_mail.assert_called_once()
        assert send_mail.call_args.kwargs["recipient_list"] == ["ops@example.test"]

        notification.metadata = {}
        with patch("src.core.notifications.services.send_mail") as send_mail:
            NotificationService._send_email(notification)
        send_mail.assert_not_called()

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

    def test_send_sms_retries_throttling_and_stops_on_terminal_errors(self):
        """SMS retry behavior is bounded and records only real provider acknowledgements."""
        notification = Notification.objects.create(
            tenant_id=uuid.UUID(self.tenant_id),
            user_id=uuid.UUID(self.user_id),
            title="Retry",
            message="x" * 1700,
            metadata={"phone_number": "+1234567890"},
        )
        throttled = ClientError({"Error": {"Code": "Throttling", "Message": "slow down"}}, "Publish")

        with (
            patch("src.core.notifications.services.time.sleep") as sleep,
            patch("src.core.notifications.services.boto3.client") as mock_boto,
        ):
            mock_sns = MagicMock()
            mock_sns.publish.side_effect = [throttled, {"MessageId": "retry-ok"}]
            mock_boto.return_value = mock_sns

            NotificationService._send_sms(notification)

        sleep.assert_called_once_with(1)
        notification.refresh_from_db()
        assert notification.metadata["sms_message_id"] == "retry-ok"
        assert mock_sns.publish.call_args.kwargs["Message"].endswith("...")

        terminal = ClientError({"Error": {"Code": "InvalidParameter", "Message": "bad phone"}}, "Publish")
        notification.metadata = {"phone_number": "+1234567890"}
        notification.save(update_fields=["metadata"])
        with patch("src.core.notifications.services.boto3.client") as mock_boto:
            mock_sns = MagicMock()
            mock_sns.publish.side_effect = terminal
            mock_boto.return_value = mock_sns
            NotificationService._send_sms(notification)
        notification.refresh_from_db()
        assert "sms_message_id" not in notification.metadata

    def test_send_sms_handles_missing_phone_and_boto_core_failure(self):
        """Missing SMS routing data and provider client errors do not fabricate success."""
        notification = Notification.objects.create(
            tenant_id=uuid.UUID(self.tenant_id),
            user_id=uuid.UUID(self.user_id),
            title="SMS",
            message="SMS",
            metadata={},
        )
        with patch("src.core.notifications.services.boto3.client") as mock_boto:
            NotificationService._send_sms(notification)
        mock_boto.assert_not_called()

        notification.metadata = {"phone_number": "+1234567890"}
        notification.save(update_fields=["metadata"])
        with patch("src.core.notifications.services.boto3.client") as mock_boto:
            mock_sns = MagicMock()
            mock_sns.publish.side_effect = BotoCoreError()
            mock_boto.return_value = mock_sns
            NotificationService._send_sms(notification)
        notification.refresh_from_db()
        assert "sms_message_id" not in notification.metadata

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

        encryption_key = Fernet.generate_key().decode("ascii")
        with (
            self.settings(SARAISE_ENCRYPTION_KEY=encryption_key),
            patch.dict(
                "os.environ",
                {"SARAISE_ENCRYPTION_KEYS": "", "SARAISE_ENCRYPTION_KEY": encryption_key},
            ),
        ):
            EncryptionService._fernet = None
            EncryptionService._cached_keys = None
            NotificationEndpoint.objects.create(
                tenant_id=uuid.UUID(self.tenant_id),
                user_id=uuid.UUID(self.user_id),
                kind="push",
                address_ciphertext=EncryptionService.encrypt("test-fcm-token"),
                fingerprint="test-fingerprint",
                device_type="web",
                display_name="Test browser",
                created_by=uuid.UUID(self.user_id),
            )

            # Inject the lazily imported Firebase modules without replacing Python's
            # process-wide import primitive.
            mock_firebase = MagicMock()
            mock_messaging = MagicMock()
            mock_credentials = MagicMock()
            mock_firebase.messaging = mock_messaging
            mock_firebase.credentials = mock_credentials

            with patch.dict(
                "sys.modules",
                {
                    "firebase_admin": mock_firebase,
                    "firebase_admin.messaging": mock_messaging,
                    "firebase_admin.credentials": mock_credentials,
                },
            ):
                mock_firebase.get_app.side_effect = ValueError("Not initialized")
                mock_firebase.initialize_app.return_value = MagicMock()

                mock_response = MagicMock()
                mock_response.success_count = 1
                mock_response.failure_count = 0
                mock_response.responses = [MagicMock(success=True)]
                mock_messaging.send_multicast.return_value = mock_response

                NotificationService._send_push(notification)

            EncryptionService._fernet = None
            EncryptionService._cached_keys = None

        mock_messaging.Notification.assert_called_once_with(
            title="Test",
            body="Test message",
        )
        mock_messaging.MulticastMessage.assert_called_once_with(
            notification=mock_messaging.Notification.return_value,
            data={"notification_id": str(notification.id), "type": "info"},
            tokens=["test-fcm-token"],
        )
        mock_messaging.send_multicast.assert_called_once_with(mock_messaging.MulticastMessage.return_value)
        notification.refresh_from_db()
        self.assertEqual(notification.metadata["push_success_count"], 1)
        self.assertEqual(notification.metadata["push_failure_count"], 0)
        self.assertIn("push_sent_at", notification.metadata)

    def test_send_push_deactivates_invalid_tokens_and_counts_batch_failures(self):
        """Provider token failures deactivate only the affected endpoint."""
        notification = Notification.objects.create(
            tenant_id=uuid.UUID(self.tenant_id),
            user_id=uuid.UUID(self.user_id),
            title="Push",
            message="Push body",
        )
        encryption_key = Fernet.generate_key().decode("ascii")
        with (
            self.settings(SARAISE_ENCRYPTION_KEY=encryption_key),
            patch.dict(
                "os.environ",
                {"SARAISE_ENCRYPTION_KEYS": "", "SARAISE_ENCRYPTION_KEY": encryption_key},
            ),
        ):
            EncryptionService._fernet = None
            EncryptionService._cached_keys = None
            endpoint = NotificationEndpoint.objects.create(
                tenant_id=uuid.UUID(self.tenant_id),
                user_id=uuid.UUID(self.user_id),
                kind="push",
                address_ciphertext=EncryptionService.encrypt("dead-token"),
                fingerprint="dead-token",
                device_type="web",
                display_name="Dead token",
                created_by=uuid.UUID(self.user_id),
            )
            mock_firebase = MagicMock()
            mock_messaging = MagicMock()
            mock_credentials = MagicMock()
            mock_firebase.messaging = mock_messaging
            mock_firebase.credentials = mock_credentials
            failure = MagicMock(success=False)
            failure.exception.code = "UNREGISTERED"
            response = MagicMock(success_count=0, failure_count=1, responses=[failure])
            mock_messaging.send_multicast.return_value = response

            with patch.dict(
                "sys.modules",
                {
                    "firebase_admin": mock_firebase,
                    "firebase_admin.messaging": mock_messaging,
                    "firebase_admin.credentials": mock_credentials,
                },
            ):
                NotificationService._send_push(notification)

            EncryptionService._fernet = None
            EncryptionService._cached_keys = None

        endpoint.refresh_from_db()
        notification.refresh_from_db()
        assert endpoint.is_active is False
        assert notification.metadata["push_failure_count"] == 1

    def test_legacy_query_and_transition_helpers_fail_closed(self):
        """Legacy list/read adapters keep malformed IDs tenant-safe."""
        tenant = uuid.UUID(self.tenant_id)
        user = uuid.UUID(self.user_id)
        notification = Notification.objects.create(
            tenant_id=tenant,
            user_id=user,
            title="Unread",
            message="Unread",
        )

        assert NotificationService.get_user_notifications(self.tenant_id, self.user_id, unread_only=True) == [
            notification
        ]
        assert NotificationService.get_user_notifications("bad", self.user_id) == []
        assert NotificationService.mark_as_read("not-a-uuid", self.tenant_id, self.user_id) is False
        assert NotificationService.mark_as_read(str(notification.id), self.tenant_id, str(uuid.uuid4())) is False
        assert NotificationService.mark_as_read(str(notification.id), self.tenant_id, self.user_id) is True
        assert NotificationService.mark_all_read("bad", self.user_id) == 0
        assert NotificationService.mark_all_read(self.tenant_id, self.user_id) >= 0

    def test_phone_number_regex_validation(self):
        """Test phone number regex validation."""
        # Valid E.164 format
        self.assertTrue(PHONE_NUMBER_REGEX.match("+1234567890"))
        self.assertTrue(PHONE_NUMBER_REGEX.match("+441234567890"))

        # Invalid formats
        self.assertFalse(PHONE_NUMBER_REGEX.match("1234567890"))  # No +
        self.assertFalse(PHONE_NUMBER_REGEX.match("+01234567890"))  # Starts with 0
        self.assertFalse(PHONE_NUMBER_REGEX.match("invalid"))  # Not a number


def test_identity_converters_accept_uuid_objects_and_reject_empty_values():
    tenant = uuid.uuid4()
    user = uuid.uuid4()

    assert _convert_tenant_id_to_uuid(tenant) == tenant
    assert _convert_user_id_to_uuid(str(user)) == user
    assert _convert_user_id_to_uuid("42") == _convert_user_id_to_uuid("42")
    with pytest.raises(ValueError, match="cannot be empty"):
        _convert_user_id_to_uuid("")
