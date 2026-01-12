# Generated migration for AI Provider Configuration models

import src.modules.ai_provider_configuration.models
from django.db import migrations, models
import django.db.models.deletion
from django.core.validators import MinValueValidator
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ("ai_provider_configuration", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AIProvider",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=src.modules.ai_provider_configuration.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(db_index=True, max_length=255, unique=True)),
                (
                    "provider_type",
                    models.CharField(
                        choices=[
                            ("openai", "OpenAI"),
                            ("anthropic", "Anthropic"),
                            ("google", "Google"),
                            ("azure", "Azure OpenAI"),
                            ("custom", "Custom"),
                        ],
                        db_index=True,
                        max_length=50,
                    ),
                ),
                ("base_url", models.URLField(blank=True, max_length=500)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "ai_provider_configuration_providers",
                "indexes": [
                    models.Index(fields=["provider_type", "is_active"], name="ai_provider_provider_type__active_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AIProviderCredential",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.ai_provider_configuration.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("api_key_encrypted", models.TextField()),
                (
                    "provider",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="credentials",
                        to="ai_provider_configuration.aiprovider",
                    ),
                ),
            ],
            options={
                "db_table": "ai_provider_configuration_credentials",
                "indexes": [
                    models.Index(fields=["tenant_id", "provider"], name="ai_provider_tenant__provider_idx"),
                ],
                "unique_together": {("tenant_id", "provider")},
            },
        ),
        migrations.CreateModel(
            name="AIModel",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=src.modules.ai_provider_configuration.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("model_id", models.CharField(db_index=True, max_length=255)),
                ("display_name", models.CharField(max_length=255)),
                ("capabilities", models.JSONField(default=list)),
                ("pricing", models.JSONField(default=dict)),
                ("max_tokens", models.IntegerField(blank=True, null=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "provider",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="models",
                        to="ai_provider_configuration.aiprovider",
                    ),
                ),
            ],
            options={
                "db_table": "ai_provider_configuration_models",
                "indexes": [
                    models.Index(fields=["provider", "is_active"], name="ai_provider_model_provider__active_idx"),
                ],
                "unique_together": {("provider", "model_id")},
            },
        ),
        migrations.CreateModel(
            name="AIModelDeployment",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.ai_provider_configuration.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
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
                        ],
                        db_index=True,
                        default="active",
                        max_length=20,
                    ),
                ),
                ("created_by", models.CharField(db_index=True, max_length=36)),
                (
                    "model",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="deployments",
                        to="ai_provider_configuration.aimodel",
                    ),
                ),
            ],
            options={
                "db_table": "ai_provider_configuration_deployments",
                "indexes": [
                    models.Index(fields=["tenant_id", "status"], name="ai_provider_tenant__status_idx"),
                    models.Index(fields=["tenant_id", "model"], name="ai_provider_tenant__model_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AIUsageLog",
            fields=[
                ("tenant_id", models.CharField(db_index=True, max_length=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.CharField(
                        default=src.modules.ai_provider_configuration.models.generate_uuid,
                        max_length=36,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("tokens_used", models.IntegerField(default=0)),
                ("input_tokens", models.IntegerField(default=0)),
                ("output_tokens", models.IntegerField(default=0)),
                (
                    "cost",
                    models.DecimalField(
                        decimal_places=6,
                        default=Decimal("0.00"),
                        max_digits=10,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                ("timestamp", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "deployment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="usage_logs",
                        to="ai_provider_configuration.aimodeldeployment",
                    ),
                ),
            ],
            options={
                "db_table": "ai_provider_configuration_usage_logs",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "deployment", "timestamp"],
                        name="ai_provider_tenant__deployment__timestamp_idx",
                    ),
                    models.Index(fields=["tenant_id", "timestamp"], name="ai_provider_tenant__timestamp_idx"),
                ],
            },
        ),
    ]
