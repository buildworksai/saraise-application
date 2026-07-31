"""
Notification Service Implementation.

SPDX-License-Identifier: Apache-2.0
"""

import logging
import re
import time
import uuid
from typing import List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from src.core.encryption import EncryptionService
from src.modules.notifications.models import Notification, NotificationEndpoint, NotificationPreference
from src.modules.notifications.services import NotificationInboxService

logger = logging.getLogger(__name__)

# E.164 phone number regex (international format)
PHONE_NUMBER_REGEX = re.compile(r"^\+[1-9]\d{1,14}$")


def _convert_user_id_to_uuid(user_id_str: str) -> uuid.UUID:
    """
    Convert Django user ID (integer as string) to UUID.

    Uses uuid5 with a fixed namespace to generate deterministic UUIDs
    from user IDs. This allows Notification.user_id (UUIDField) to work
    with Django's integer-based user IDs.
    """
    if not user_id_str:
        raise ValueError("user_id_str cannot be empty")

    # Use a fixed namespace UUID for user ID conversion
    NAMESPACE_USER_ID = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

    try:
        # Try to parse as UUID first (in case it's already a UUID string)
        return uuid.UUID(user_id_str)
    except ValueError:
        # If not a UUID, generate one from the user ID using uuid5
        return uuid.uuid5(NAMESPACE_USER_ID, user_id_str)


def _convert_tenant_id_to_uuid(tenant_id: str | uuid.UUID) -> uuid.UUID:
    """Accept both legacy string tenant IDs and canonical UUID objects."""
    return tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))


class NotificationService:
    """Service for sending notifications via multiple channels."""

    @staticmethod
    def create_notification(
        tenant_id: str,
        user_id: str,
        title: str,
        message: str,
        notification_type: str = "info",
        action_url: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Notification:
        """Create an in-app notification.

        Args:
            tenant_id: Tenant ID (string, will be converted to UUID).
            user_id: User ID to notify (string, will be converted to UUID).
            title: Notification title.
            message: Notification message.
            notification_type: Type of notification (info, success, warning, error, etc.).
            action_url: Optional URL for action button.
            metadata: Optional metadata dictionary.

        Returns:
            Created Notification instance.
        """
        try:
            tenant_id_uuid = _convert_tenant_id_to_uuid(tenant_id)
            user_id_uuid = _convert_user_id_to_uuid(user_id)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid tenant_id or user_id format: {e}")
            raise ValueError(f"Invalid tenant_id or user_id format: {e}")

        notification = Notification.objects.create(
            tenant_id=tenant_id_uuid,
            user_id=user_id_uuid,
            title=title,
            message=message,
            notification_type=notification_type,
            category=str((metadata or {}).get("category", "general")),
            action_url=action_url or "",
            metadata=metadata or {},
        )

        logger.info(f"Created notification {notification.id} for user {user_id}")

        # Send via other channels based on preferences
        NotificationService._send_external_notifications(notification)

        return notification

    @staticmethod
    def _send_external_notifications(notification: Notification) -> None:
        """Send notification via external channels (email, SMS, push) based on preferences.

        Args:
            notification: Notification instance.
        """
        try:
            category = notification.category or notification.notification_type
            if not NotificationService._category_enabled(notification, category):
                return

            # Send email if enabled
            if NotificationService._channel_enabled(notification, "email", category, default=True):
                NotificationService._send_email(notification)

            # Send SMS if enabled (TODO: Implement SMS provider integration)
            if NotificationService._channel_enabled(notification, "sms", category, default=False):
                NotificationService._send_sms(notification)

            # Send push notification if enabled (TODO: Implement web push)
            if NotificationService._channel_enabled(notification, "push", category, default=True):
                NotificationService._send_push(notification)

        except Exception as e:
            logger.error(f"Failed to send external notifications: {e}")

    @staticmethod
    def _channel_enabled(notification: Notification, channel: str, category: str, *, default: bool) -> bool:
        """Read canonical v2 preferences for the legacy core service contract."""
        preference = (
            NotificationPreference.objects.for_tenant(notification.tenant_id)
            .filter(user_id=notification.user_id, channel=channel, category=category)
            .first()
        )
        return default if preference is None else bool(preference.enabled)

    @staticmethod
    def _category_enabled(notification: Notification, category: str) -> bool:
        """Preserve legacy category opt-outs without restoring deleted tables."""
        preferences = NotificationPreference.objects.for_tenant(notification.tenant_id).filter(
            user_id=notification.user_id,
            category=category,
        )
        return not preferences.exists() or preferences.filter(enabled=True).exists()

    @staticmethod
    def _send_email(notification: Notification) -> None:
        """Send notification via email.

        Args:
            notification: Notification instance.
        """
        try:
            user_email = notification.metadata.get("user_email")
            if not user_email:
                raise ValueError("Notification email delivery requires metadata.user_email")

            send_mail(
                subject=notification.title,
                message=notification.message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@saraise.com"),
                recipient_list=[user_email],
                fail_silently=False,
            )

            logger.info(f"Sent email notification {notification.id} to {user_email}")
        except Exception as e:
            logger.error(f"Failed to send email notification {notification.id}: {e}")

    @staticmethod
    def _send_sms(notification: Notification) -> None:
        """Send notification via SMS using AWS SNS.

        Args:
            notification: Notification instance.

        Note:
            Requires AWS SNS configuration:
            - AWS_SNS_REGION environment variable
            - AWS credentials (via environment variables or IAM role)
            - Optional: AWS_SNS_SENDER_ID for branded SMS
        """
        try:
            # Get phone number from notification metadata or user profile
            phone_number = notification.metadata.get("phone_number")
            if not phone_number:
                logger.warning(f"No phone number found for notification {notification.id}")
                return

            # Validate phone number format (E.164)
            if not PHONE_NUMBER_REGEX.match(phone_number):
                logger.error(f"Invalid phone number format: {phone_number}. Must be E.164 format (e.g., +1234567890)")
                return

            # Get AWS SNS region
            region = getattr(settings, "AWS_SNS_REGION", "us-east-1")
            sender_id = getattr(settings, "AWS_SNS_SENDER_ID", None)

            # Initialize SNS client
            sns_client = boto3.client("sns", region_name=region)

            # Prepare message (SMS has 160 char limit, long SMS concatenated automatically)
            message = f"{notification.title}\n{notification.message}"
            if len(message) > 1600:  # AWS SNS limit
                message = message[:1597] + "..."

            # Send SMS with retry logic
            max_retries = 3
            retry_delay = 1  # seconds

            for attempt in range(max_retries):
                try:
                    # Prepare SMS attributes
                    sms_attributes = {}
                    if sender_id:
                        sms_attributes["AWS.SNS.SMS.SenderID"] = {"StringValue": sender_id, "DataType": "String"}

                    # Send SMS
                    response = sns_client.publish(
                        PhoneNumber=phone_number,
                        Message=message,
                        MessageAttributes=sms_attributes if sms_attributes else None,
                    )

                    message_id = response.get("MessageId")
                    logger.info(
                        f"SMS sent successfully: notification {notification.id}, "
                        f"message_id {message_id}, phone {phone_number}"
                    )

                    # Update notification metadata with delivery info
                    notification.metadata["sms_message_id"] = message_id
                    notification.metadata["sms_sent_at"] = timezone.now().isoformat()
                    notification.save(update_fields=["metadata"])

                    return

                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    error_message = e.response.get("Error", {}).get("Message", str(e))

                    # Check if error is retryable
                    retryable_errors = ["Throttling", "ServiceUnavailable", "InternalError"]
                    if error_code in retryable_errors and attempt < max_retries - 1:
                        wait_time = retry_delay * (2**attempt)  # Exponential backoff
                        logger.warning(
                            f"SMS send attempt {attempt + 1} failed (retryable): {error_code}. "
                            f"Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        # Non-retryable error or max retries reached
                        logger.error(
                            f"SMS send failed for notification {notification.id}: " f"{error_code} - {error_message}"
                        )
                        return

                except BotoCoreError as e:
                    logger.error(f"AWS SNS client error for notification {notification.id}: {e}")
                    return

        except Exception as e:
            logger.error(f"Failed to send SMS notification {notification.id}: {e}", exc_info=True)

    @staticmethod
    def _send_push(notification: Notification) -> None:
        """Send push notification via FCM (Firebase Cloud Messaging).

        Args:
            notification: Notification instance.

        Note:
            Requires Firebase Admin SDK configuration:
            - FIREBASE_CREDENTIALS_PATH or GOOGLE_APPLICATION_CREDENTIALS environment variable
            - FCM service account JSON file
        """
        try:
            import firebase_admin
            from firebase_admin import credentials, messaging

            # Initialize Firebase Admin SDK (if not already initialized)
            try:
                firebase_admin.get_app()
            except ValueError:
                # Initialize with credentials
                cred_path = getattr(settings, "FIREBASE_CREDENTIALS_PATH", None)
                if cred_path:
                    cred = credentials.Certificate(cred_path)
                else:
                    # Use default credentials (from GOOGLE_APPLICATION_CREDENTIALS)
                    cred = credentials.ApplicationDefault()

                firebase_admin.initialize_app(cred)

            endpoints = NotificationEndpoint.objects.for_tenant(notification.tenant_id).filter(
                kind="push",
                user_id=notification.user_id,
                is_active=True,
            )

            if not endpoints.exists():
                logger.debug(f"No active FCM tokens found for user {notification.user_id}")
                return

            # Prepare notification payload
            fcm_notification = messaging.Notification(
                title=notification.title,
                body=notification.message,
            )

            # Prepare data payload (for deep linking)
            data_payload = {
                "notification_id": str(notification.id),
                "type": notification.notification_type,
            }
            if notification.action_url:
                data_payload["action_url"] = notification.action_url

            # Prepare message for batch sending
            token_by_endpoint = [
                (endpoint, EncryptionService.decrypt(endpoint.address_ciphertext)) for endpoint in endpoints
            ]
            token_list = [token for _, token in token_by_endpoint]
            if not token_list:
                return

            # Send to multiple tokens (batch)
            # FCM supports up to 500 tokens per batch
            batch_size = 500
            success_count = 0
            failure_count = 0

            for i in range(0, len(token_list), batch_size):
                batch_tokens = token_list[i : i + batch_size]

                try:
                    # Create multicast message
                    message = messaging.MulticastMessage(
                        notification=fcm_notification,
                        data=data_payload,
                        tokens=batch_tokens,
                    )

                    # Send batch
                    response = messaging.send_multicast(message)

                    # Update token usage timestamps for successful sends
                    if response.success_count > 0:
                        success_count += response.success_count
                        # Update last_used_at for successful tokens
                        successful_tokens = set(batch_tokens[: response.success_count])
                        NotificationEndpoint.objects.for_tenant(notification.tenant_id).filter(
                            kind="push",
                            user_id=notification.user_id,
                            address_ciphertext__in=[
                                endpoint.address_ciphertext
                                for endpoint, token in token_by_endpoint
                                if token in successful_tokens
                            ],
                        ).update(last_used_at=timezone.now())

                    # Handle failed tokens (mark as inactive if invalid)
                    if response.failure_count > 0:
                        failure_count += response.failure_count
                        for idx, result in enumerate(response.responses):
                            if not result.success:
                                error_code = result.exception.code if result.exception else "unknown"
                                # Mark token as inactive if it's invalid
                                if error_code in [
                                    "INVALID_ARGUMENT",
                                    "UNREGISTERED",
                                    "NOT_FOUND",
                                ]:
                                    try:
                                        endpoint = next(
                                            candidate
                                            for candidate, token in token_by_endpoint
                                            if token == batch_tokens[idx]
                                        )
                                        endpoint.is_active = False
                                        endpoint.save(update_fields=["is_active", "updated_at"])
                                        logger.info(f"Deactivated invalid FCM token for user {notification.user_id}")
                                    except StopIteration:
                                        pass

                except Exception as e:
                    logger.error(f"FCM batch send failed: {e}", exc_info=True)
                    failure_count += len(batch_tokens)

            logger.info(
                f"Push notification sent: notification {notification.id}, "
                f"success: {success_count}, failures: {failure_count}"
            )

            # Update notification metadata
            notification.metadata["push_sent_at"] = timezone.now().isoformat()
            notification.metadata["push_success_count"] = success_count
            notification.metadata["push_failure_count"] = failure_count
            notification.save(update_fields=["metadata"])

        except ImportError:
            logger.error("firebase-admin library not installed. Install with: pip install firebase-admin")
        except Exception as e:
            logger.error(f"Failed to send push notification {notification.id}: {e}", exc_info=True)

    @staticmethod
    def get_user_notifications(
        tenant_id: str, user_id: str, unread_only: bool = False, limit: int = 50
    ) -> List[Notification]:
        """Get notifications for a user.

        Args:
            tenant_id: Tenant ID (string, will be converted to UUID).
            user_id: User ID (string, will be converted to UUID).
            unread_only: If True, return only unread notifications.
            limit: Maximum number of notifications to return.

        Returns:
            List of Notification instances.
        """
        try:
            tenant_id_uuid = _convert_tenant_id_to_uuid(tenant_id)
            user_id_uuid = _convert_user_id_to_uuid(user_id)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid tenant_id or user_id format: {e}")
            return []

        queryset = Notification.objects.for_tenant(tenant_id_uuid).filter(user_id=user_id_uuid)

        if unread_only:
            queryset = queryset.filter(status="unread")

        return list(queryset[:limit])

    @staticmethod
    def mark_as_read(notification_id: str, tenant_id: str, user_id: str) -> bool:
        """Mark a notification as read.

        Args:
            notification_id: Notification ID (UUID string).
            tenant_id: Tenant ID (string, will be converted to UUID).
            user_id: User ID (string, will be converted to UUID).

        Returns:
            True if marked as read, False if not found or unauthorized.
        """
        try:
            tenant_id_uuid = _convert_tenant_id_to_uuid(tenant_id)
            user_id_uuid = _convert_user_id_to_uuid(user_id)
            notification_id_uuid = uuid.UUID(notification_id)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid ID format: {e}")
            return False

        try:
            NotificationInboxService.mark_read(
                tenant_id_uuid,
                user_id_uuid,
                notification_id_uuid,
                f"legacy-mark-read:{notification_id_uuid}",
            )
            return True
        except Notification.DoesNotExist:
            return False

    @staticmethod
    def mark_all_read(tenant_id: str, user_id: str) -> int:
        """Mark all notifications as read for a user.

        Args:
            tenant_id: Tenant ID (string, will be converted to UUID).
            user_id: User ID (string, will be converted to UUID).

        Returns:
            Number of notifications marked as read.
        """
        try:
            tenant_id_uuid = _convert_tenant_id_to_uuid(tenant_id)
            user_id_uuid = _convert_user_id_to_uuid(user_id)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid tenant_id or user_id format: {e}")
            return 0

        count = NotificationInboxService.mark_all_read(
            tenant_id_uuid,
            user_id_uuid,
            f"legacy-mark-all-read:{uuid.uuid4()}",
        )

        logger.info(f"Marked {count} notifications as read for user {user_id}")
        return count
