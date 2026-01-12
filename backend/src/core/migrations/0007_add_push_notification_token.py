# Generated manually for Phase 7 - Push Notification Token support

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_notification_notificationpreference"),
    ]

    operations = [
        migrations.CreateModel(
            name="PushNotificationToken",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("user_id", models.UUIDField(db_index=True, help_text="User ID")),
                ("token", models.TextField(help_text="FCM registration token")),
                (
                    "device_type",
                    models.CharField(
                        choices=[("web", "Web Browser"), ("android", "Android"), ("ios", "iOS")],
                        default="web",
                        max_length=20,
                    ),
                ),
                ("device_id", models.CharField(blank=True, help_text="Device identifier", max_length=255)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "push_notification_tokens",
                "indexes": [
                    models.Index(fields=["tenant_id", "user_id", "is_active"], name="push_token_tenant_user_active_idx"),
                    models.Index(fields=["tenant_id", "token"], name="push_token_tenant_token_idx"),
                ],
                "unique_together": {("tenant_id", "user_id", "token")},
            },
        ),
    ]
