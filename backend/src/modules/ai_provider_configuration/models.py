"""
AiProviderConfiguration Models.

Defines data models for AiProviderConfiguration module.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class TenantBaseModel(models.Model):
    """Base model for tenant-scoped models with Row-Level Multitenancy.

    CRITICAL: All tenant-scoped models MUST inherit from this base class
    and include tenant_id. All queries MUST filter explicitly by tenant_id.
    """

    tenant_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "ai_provider_configuration"
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class AIProvider(models.Model):
    """AI Provider model (platform-level, no tenant_id)."""

    PROVIDER_TYPE_CHOICES = [
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("google", "Google Gemini"),
        ("groq", "Groq"),
        ("huggingface", "HuggingFace"),
        ("azure", "Azure OpenAI"),
        ("custom", "Custom"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    provider_type = models.CharField(
        max_length=50,
        choices=PROVIDER_TYPE_CHOICES,
        db_index=True,
    )
    base_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Base URL for API (optional, uses default if empty)",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "ai_provider_configuration"
        db_table = "ai_provider_configuration_providers"
        indexes = [
            models.Index(fields=["provider_type", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.provider_type})"


class AIProviderCredential(TenantBaseModel):
    """AI Provider credential model for storing encrypted API keys."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    provider = models.ForeignKey(
        AIProvider,
        on_delete=models.CASCADE,
        related_name="credentials",
    )
    api_key_encrypted = models.TextField(
        help_text="Encrypted API key (encrypted at rest)",
    )

    class Meta:
        app_label = "ai_provider_configuration"
        db_table = "ai_provider_configuration_credentials"
        indexes = [
            models.Index(fields=["tenant_id", "provider"]),
        ]
        unique_together = [["tenant_id", "provider"]]

    def __str__(self) -> str:
        return f"{self.provider.name} credentials for tenant {self.tenant_id}"


class AIModel(models.Model):
    """AI Model model (platform-level, no tenant_id)."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    provider = models.ForeignKey(
        AIProvider,
        on_delete=models.CASCADE,
        related_name="models",
    )
    model_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Model identifier (e.g., 'gpt-4', 'claude-3-opus')",
    )
    display_name = models.CharField(max_length=255)
    capabilities = models.JSONField(
        default=list,
        help_text="List of capabilities (text, vision, function_calling, etc.)",
    )
    pricing = models.JSONField(
        default=dict,
        help_text="Pricing information (input_cost_per_token, output_cost_per_token)",
    )
    max_tokens = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum tokens supported",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "ai_provider_configuration"
        db_table = "ai_provider_configuration_models"
        indexes = [
            models.Index(fields=["provider", "is_active"]),
        ]
        unique_together = [["provider", "model_id"]]

    def __str__(self) -> str:
        return f"{self.provider.name} - {self.display_name}"


class AIModelDeployment(TenantBaseModel):
    """AI Model deployment model for tenant-specific model configurations."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("error", "Error"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    model = models.ForeignKey(
        AIModel,
        on_delete=models.PROTECT,
        related_name="deployments",
    )
    config = models.JSONField(
        default=dict,
        help_text="Deployment configuration (temperature, max_tokens, etc.)",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
        db_index=True,
    )
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        app_label = "ai_provider_configuration"
        db_table = "ai_provider_configuration_deployments"
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "model"]),
        ]

    def __str__(self) -> str:
        return f"{self.model.display_name} deployment for tenant {self.tenant_id}"


class AIUsageLog(TenantBaseModel):
    """AI usage log model for tracking API usage and costs."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    deployment = models.ForeignKey(
        AIModelDeployment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_logs",
    )
    tokens_used = models.IntegerField(
        default=0,
        help_text="Total tokens used (input + output)",
    )
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    cost = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Cost in USD",
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        app_label = "ai_provider_configuration"
        db_table = "ai_provider_configuration_usage_logs"
        indexes = [
            models.Index(fields=["tenant_id", "deployment", "timestamp"]),
            models.Index(fields=["tenant_id", "timestamp"]),
        ]

    def __str__(self) -> str:
        return f"Usage log: {self.tokens_used} tokens at {self.timestamp}"
