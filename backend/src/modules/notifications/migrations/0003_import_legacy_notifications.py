"""Non-destructively import legacy notification data with provenance."""

import hashlib
import hmac
import uuid

from django.conf import settings
from django.db import migrations

PROVENANCE = {"migration": "notifications.0003", "source": "core"}


def _actor(tenant_id):
    return uuid.uuid5(tenant_id, "saraise-system:legacy-notification-import")


def _encrypt(value):
    from src.core.encryption import EncryptionService
    return EncryptionService.encrypt(value)


def import_legacy(apps, schema_editor):
    LegacyNotification = apps.get_model("core", "Notification")
    LegacyPreference = apps.get_model("core", "NotificationPreference")
    LegacyToken = apps.get_model("core", "PushNotificationToken")
    Notification = apps.get_model("notifications", "Notification")
    Preference = apps.get_model("notifications", "NotificationPreference")
    Endpoint = apps.get_model("notifications", "NotificationEndpoint")
    if schema_editor.connection.vendor == "postgresql":
        # The deployment migration role must have BYPASSRLS. Failing here is
        # safer than silently importing only one active tenant.
        schema_editor.execute("SET LOCAL row_security = off")

    for legacy in LegacyNotification.objects.all().iterator():
        metadata = dict(legacy.metadata) if isinstance(legacy.metadata, dict) else {}
        metadata["migration_provenance"] = {**PROVENANCE, "source_id": str(legacy.pk)}
        action_url = legacy.action_url if isinstance(legacy.action_url, str) and legacy.action_url.startswith("/") and not legacy.action_url.startswith("//") else ""
        if legacy.action_url and not action_url:
            metadata["migration_provenance"]["action_url_quarantined"] = True
        if len(str(metadata).encode()) > 65536:
            metadata = {"migration_provenance": {**PROVENANCE, "source_id": str(legacy.pk), "metadata_quarantined": True}}
        Notification.objects.update_or_create(
            id=legacy.id,
            defaults={
                "tenant_id": legacy.tenant_id, "user_id": legacy.user_id,
                "notification_type": legacy.type if legacy.type in {"info", "success", "warning", "error", "workflow", "approval", "system"} else "info",
                "category": f"legacy.{legacy.type}"[:100], "title": legacy.title,
                "message": legacy.message, "status": "read" if legacy.read else "unread",
                "read_at": legacy.read_at if legacy.read else None, "action_url": action_url,
                "metadata": metadata, "created_at": legacy.created_at, "updated_at": legacy.updated_at,
            },
        )

    channel_fields = {"email": "email_enabled", "sms": "sms_enabled", "push": "push_enabled", "in_app": "in_app_enabled"}
    category_fields = {"workflow": "workflow_notifications", "approval": "approval_notifications", "system": "system_notifications"}
    for legacy in LegacyPreference.objects.all().iterator():
        for channel, channel_field in channel_fields.items():
            for category, category_field in category_fields.items():
                Preference.objects.update_or_create(
                    tenant_id=legacy.tenant_id, user_id=legacy.user_id, channel=channel, category=category,
                    defaults={"enabled": bool(getattr(legacy, channel_field) and getattr(legacy, category_field)), "digest_mode": "immediate", "timezone": "UTC", "migration_provenance": {**PROVENANCE, "source_id": str(legacy.pk)}},
                )

    key = str(settings.SECRET_KEY).encode()
    for legacy in LegacyToken.objects.all().iterator():
        fingerprint = hmac.new(key, legacy.tenant_id.bytes + legacy.token.encode(), hashlib.sha256).hexdigest()
        Endpoint.objects.update_or_create(
            tenant_id=legacy.tenant_id, kind="push", fingerprint=fingerprint,
            defaults={"user_id": legacy.user_id, "device_type": legacy.device_type, "address_ciphertext": _encrypt(legacy.token), "display_name": legacy.device_id or f"Imported {legacy.device_type} device", "secret_ref": "", "is_active": legacy.is_active, "last_used_at": legacy.last_used_at, "created_by": _actor(legacy.tenant_id), "migration_provenance": {**PROVENANCE, "source_id": str(legacy.pk)}},
        )


def reverse_import(apps, schema_editor):
    Notification = apps.get_model("notifications", "Notification")
    Preference = apps.get_model("notifications", "NotificationPreference")
    Endpoint = apps.get_model("notifications", "NotificationEndpoint")
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET LOCAL row_security = off")
    Notification.objects.filter(metadata__migration_provenance__migration="notifications.0003").delete()
    Preference.objects.filter(migration_provenance__migration="notifications.0003").delete()
    Endpoint.objects.filter(migration_provenance__migration="notifications.0003").delete()


class Migration(migrations.Migration):
    dependencies = [("notifications", "0002_notifications_rls")]
    operations = [migrations.RunPython(import_legacy, reverse_import)]
