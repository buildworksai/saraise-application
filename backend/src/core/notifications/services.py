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

from .models import Notification, NotificationPreference

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
            tenant_id_uuid = uuid.UUID(tenant_id)
            user_id_uuid = _convert_user_id_to_uuid(user_id)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid tenant_id or user_id format: {e}")
            raise ValueError(f"Invalid tenant_id or user_id format: {e}")

        notification = Notification.objects.create(
            tenant_id=tenant_id_uuid,
            user_id=user_id_uuid,
            title=title,
            message=message,
            type=notification_type,
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
            # notification.tenant_id and notification.user_id are already UUIDs
            preference, _ = NotificationPreference.objects.get_or_create(
                tenant_id=notification.tenant_id,
                user_id=notification.user_id,
                defaults={
                    "email_enabled": True,
                    "sms_enabled": False,
                    "push_enabled": True,
                    "in_app_enabled": True,
                },
            )

            # Check if this notification type is enabled
            if notification.type == "workflow" and not preference.workflow_notifications:
                return
            if notification.type == "approval" and not preference.approval_notifications:
                return
            if notification.type == "system" and not preference.system_notifications:
                return

            # Send email if enabled
            if preference.email_enabled:
                NotificationService._send_email(notification)

            # Send SMS if enabled (TODO: Implement SMS provider integration)
            if preference.sms_enabled:
                NotificationService._send_sms(notification)

            # Send push notification if enabled (TODO: Implement web push)
            if preference.push_enabled:
                NotificationService._send_push(notification)

        except Exception as e:
            logger.error(f"Failed to send external notifications: {e}")

    @staticmethod
    def _send_email(notification: Notification) -> None:
        """Send notification via email.

        Args:
            notification: Notification instance.
        """
        try:
            # Get user email (simplified - in production, fetch from User model)
            # For now, use a placeholder
            user_email = notification.metadata.get("user_email", "user@example.com")

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
                    if error_code in ["Throttling", "ServiceUnavailable", "InternalError"] and attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(
                            f"SMS send attempt {attempt + 1} failed (retryable): {error_code}. "
                            f"Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        # Non-retryable error or max retries reached
                        logger.error(
                            f"SMS send failed for notification {notification.id}: "
                            f"{error_code} - {error_message}"
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

            # Get all active FCM tokens for the user
            from .models import PushNotificationToken

            tokens = PushNotificationToken.objects.filter(
                tenant_id=notification.tenant_id,
                user_id=notification.user_id,
                is_active=True,
            )

            if not tokens.exists():
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
                "type": notification.type,
            }
            if notification.action_url:
                data_payload["action_url"] = notification.action_url

            # Prepare message for batch sending
            token_list = [token.token for token in tokens]
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
                        PushNotificationToken.objects.filter(
                            tenant_id=notification.tenant_id,
                            user_id=notification.user_id,
                            token__in=batch_tokens[: response.success_count],
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
                                        token_obj = PushNotificationToken.objects.get(
                                            tenant_id=notification.tenant_id,
                                            user_id=notification.user_id,
                                            token=batch_tokens[idx],
                                        )
                                        token_obj.is_active = False
                                        token_obj.save(update_fields=["is_active"])
                                        logger.info(
                                            f"Deactivated invalid FCM token for user {notification.user_id}"
                                        )
                                    except PushNotificationToken.DoesNotExist:
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
            logger.error(
                "firebase-admin library not installed. Install with: pip install firebase-admin"
            )
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
            tenant_id_uuid = uuid.UUID(tenant_id)
            user_id_uuid = _convert_user_id_to_uuid(user_id)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid tenant_id or user_id format: {e}")
            return []

        queryset = Notification.objects.filter(tenant_id=tenant_id_uuid, user_id=user_id_uuid)

        if unread_only:
            queryset = queryset.filter(read=False)

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
            tenant_id_uuid = uuid.UUID(tenant_id)
            user_id_uuid = _convert_user_id_to_uuid(user_id)
            notification_id_uuid = uuid.UUID(notification_id)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid ID format: {e}")
            return False

        try:
            notification = Notification.objects.get(
                id=notification_id_uuid, tenant_id=tenant_id_uuid, user_id=user_id_uuid
            )
            notification.mark_as_read()
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
            tenant_id_uuid = uuid.UUID(tenant_id)
            user_id_uuid = _convert_user_id_to_uuid(user_id)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid tenant_id or user_id format: {e}")
            return 0

        count = Notification.objects.filter(
            tenant_id=tenant_id_uuid, user_id=user_id_uuid, read=False
        ).update(read=True, read_at=timezone.now())

        logger.info(f"Marked {count} notifications as read for user {user_id}")
        return count
