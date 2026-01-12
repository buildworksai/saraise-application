# Generated migration for Integration Platform models

import src.modules.integration_platform.models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("integration_platform", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Integration",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.integration_platform.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(db_index=True, max_length=255)),
                (
                    "integration_type",
                    models.CharField(
                        choices=[
                            ("api", "API"),
                            ("webhook", "Webhook"),
                            ("database", "Database"),
                            ("file", "File"),
                            ("message_queue", "Message Queue"),
                        ],
                        db_index=True,
                        max_length=50,
                    ),
                ),
                ("config", models.JSONField(default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("inactive", "Inactive"),
                            ("error", "Error"),
                            ("testing", "Testing"),
                        ],
                        db_index=True,
                        default="inactive",
                        max_length=20,
                    ),
                ),
                ("created_by", models.CharField(db_index=True, max_length=36)),
            ],
            options={
                "db_table": "integration_platform_integrations",
                "indexes": [
                    models.Index(fields=["tenant_id", "status"], name="integration_tenant__status_idx"),
                    models.Index(fields=["tenant_id", "integration_type"], name="integration_tenant__type_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="IntegrationCredential",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=src.modules.integration_platform.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "credential_type",
                    models.CharField(
                        choices=[
                            ("api_key", "API Key"),
                            ("oauth_token", "OAuth Token"),
                            ("username_password", "Username/Password"),
                            ("certificate", "Certificate"),
                        ],
                        max_length=50,
                    ),
                ),
                ("encrypted_value", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "integration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="credentials",
                        to="integration_platform.integration",
                    ),
                ),
            ],
            options={
                "db_table": "integration_platform_credentials",
                "indexes": [
                    models.Index(fields=["integration"], name="integration_cred_integration_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Webhook",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.integration_platform.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(db_index=True, max_length=255)),
                ("url", models.URLField(max_length=2000)),
                ("events", models.JSONField(default=list)),
                ("secret", models.CharField(max_length=128)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_by", models.CharField(db_index=True, max_length=36)),
            ],
            options={
                "db_table": "integration_platform_webhooks",
                "indexes": [
                    models.Index(fields=["tenant_id", "is_active"], name="integration_webhook_tenant__active_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="WebhookDelivery",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=src.modules.integration_platform.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("event", models.CharField(max_length=255)),
                ("payload", models.JSONField(default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("delivered", "Delivered"),
                            ("failed", "Failed"),
                            ("retrying", "Retrying"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("response_code", models.IntegerField(blank=True, null=True)),
                ("response_body", models.TextField(blank=True)),
                ("error_message", models.TextField(blank=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "webhook",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="integration_platform.webhook",
                    ),
                ),
            ],
            options={
                "db_table": "integration_platform_webhook_deliveries",
                "indexes": [
                    models.Index(fields=["webhook", "status"], name="integration_webhook_webhook__status_idx"),
                    models.Index(fields=["webhook", "created_at"], name="integration_webhook_webhook__created_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Connector",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=src.modules.integration_platform.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(db_index=True, max_length=255, unique=True)),
                (
                    "connector_type",
                    models.CharField(
                        choices=[
                            ("api", "API"),
                            ("database", "Database"),
                            ("file", "File"),
                            ("message_queue", "Message Queue"),
                        ],
                        db_index=True,
                        max_length=50,
                    ),
                ),
                ("schema", models.JSONField(default=dict)),
                ("config", models.JSONField(default=dict)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "integration_platform_connectors",
                "indexes": [
                    models.Index(fields=["connector_type", "is_active"], name="integration_connector_type__active_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="DataMapping",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.integration_platform.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("source_field", models.CharField(max_length=255)),
                ("target_field", models.CharField(max_length=255)),
                ("transform", models.JSONField(default=dict)),
                (
                    "integration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mappings",
                        to="integration_platform.integration",
                    ),
                ),
            ],
            options={
                "db_table": "integration_platform_data_mappings",
                "indexes": [
                    models.Index(fields=["tenant_id", "integration"], name="integration_mapping_tenant__integration_idx"),
                ],
                "unique_together": {("integration", "source_field", "target_field")},
            },
        ),
    ]
