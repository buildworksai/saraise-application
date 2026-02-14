"""
IntegrationPlatform Models.

Defines data models for IntegrationPlatform module.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
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
        app_label = "integration_platform"
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class Integration(TenantBaseModel):
    """Integration model for external system connections."""

    INTEGRATION_TYPE_CHOICES = [
        ("api", "API"),
        ("webhook", "Webhook"),
        ("database", "Database"),
        ("file", "File"),
        ("message_queue", "Message Queue"),
    ]

    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("error", "Error"),
        ("testing", "Testing"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255, db_index=True)
    integration_type = models.CharField(
        max_length=50,
        choices=INTEGRATION_TYPE_CHOICES,
        db_index=True,
    )
    config = models.JSONField(
        default=dict,
        help_text="Integration-specific configuration",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="inactive",
        db_index=True,
    )
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_integrations"
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "integration_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.integration_type})"


class IntegrationCredential(models.Model):
    """Integration credential model for storing encrypted credentials."""

    CREDENTIAL_TYPE_CHOICES = [
        ("api_key", "API Key"),
        ("oauth_token", "OAuth Token"),
        ("username_password", "Username/Password"),
        ("certificate", "Certificate"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    integration = models.ForeignKey(
        Integration,
        on_delete=models.CASCADE,
        related_name="credentials",
    )
    credential_type = models.CharField(
        max_length=50,
        choices=CREDENTIAL_TYPE_CHOICES,
    )
    encrypted_value = models.TextField(
        help_text="Encrypted credential value (encrypted at rest)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_credentials"
        indexes = [
            models.Index(fields=["integration"]),
        ]

    def __str__(self) -> str:
        return f"{self.integration.name} - {self.credential_type}"


class Webhook(TenantBaseModel):
    """Webhook model for outgoing webhook deliveries."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255, db_index=True)
    url = models.URLField(max_length=2000, help_text="Webhook URL")
    events = models.JSONField(
        default=list,
        help_text="List of events to trigger webhook",
    )
    secret = models.CharField(
        max_length=128,
        help_text="Secret for HMAC-SHA256 signature",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_webhooks"
        indexes = [
            models.Index(fields=["tenant_id", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} - {self.url}"


class WebhookDelivery(models.Model):
    """Webhook delivery model for tracking webhook deliveries."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("delivered", "Delivered"),
        ("failed", "Failed"),
        ("retrying", "Retrying"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    webhook = models.ForeignKey(
        Webhook,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    event = models.CharField(max_length=255, help_text="Event name")
    payload = models.JSONField(default=dict, help_text="Webhook payload")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    response_code = models.IntegerField(null=True, blank=True, help_text="HTTP response code")
    response_body = models.TextField(blank=True, help_text="Response body (truncated)")
    error_message = models.TextField(blank=True, help_text="Error message if failed")
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_webhook_deliveries"
        indexes = [
            models.Index(fields=["webhook", "status"]),
            models.Index(fields=["webhook", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.webhook.name} - {self.event} - {self.status}"


class Connector(models.Model):
    """Connector model for available integration connectors (platform-level)."""

    CONNECTOR_TYPE_CHOICES = [
        ("api", "API"),
        ("database", "Database"),
        ("file", "File"),
        ("message_queue", "Message Queue"),
    ]

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    connector_type = models.CharField(
        max_length=50,
        choices=CONNECTOR_TYPE_CHOICES,
        db_index=True,
    )
    schema = models.JSONField(
        default=dict,
        help_text="Connector schema definition",
    )
    config = models.JSONField(
        default=dict,
        help_text="Connector configuration template",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_connectors"
        indexes = [
            models.Index(fields=["connector_type", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.connector_type})"


class DataMapping(TenantBaseModel):
    """Data mapping model for field transformations."""

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    integration = models.ForeignKey(
        Integration,
        on_delete=models.CASCADE,
        related_name="mappings",
    )
    source_field = models.CharField(
        max_length=255,
        help_text="Source field name",
    )
    target_field = models.CharField(
        max_length=255,
        help_text="Target field name",
    )
    transform = models.JSONField(
        default=dict,
        help_text="Transformation rules",
    )

    class Meta:
        app_label = "integration_platform"
        db_table = "integration_platform_data_mappings"
        indexes = [
            models.Index(fields=["tenant_id", "integration"]),
        ]
        unique_together = [["integration", "source_field", "target_field"]]

    def __str__(self) -> str:
        return f"{self.integration.name}: {self.source_field} -> {self.target_field}"
