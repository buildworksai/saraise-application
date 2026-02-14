"""
Communication Hub Models.

Defines data models for channels, messages, and conversations.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from django.db import models


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class TenantBaseModel(models.Model):
    """Base model for tenant-scoped models with Row-Level Multitenancy.

    CRITICAL: All tenant-scoped models MUST inherit from this base class
    and include tenant_id. All queries MUST filter explicitly by tenant_id.
    """

    tenant_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class Channel(TenantBaseModel):
    """Channel model - Communication channel."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    channel_code = models.CharField(max_length=50, db_index=True)
    channel_name = models.CharField(max_length=255)
    channel_type = models.CharField(max_length=50, db_index=True)  # email, sms, chat, etc.
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "communication_channels"
        indexes = [
            models.Index(fields=["tenant_id", "channel_code"]),
            models.Index(fields=["tenant_id", "channel_type"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "channel_code"], name="unique_channel_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.channel_code} - {self.channel_name}"


class Message(TenantBaseModel):
    """Message model - Individual message in a channel."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="messages")
    sender_id = models.UUIDField(db_index=True, help_text="FK to user")
    recipient_id = models.UUIDField(null=True, blank=True, db_index=True, help_text="FK to user")
    subject = models.CharField(max_length=500, blank=True)
    body = models.TextField()
    message_type = models.CharField(max_length=50, default="text")  # text, email, sms
    status = models.CharField(max_length=50, default="sent", db_index=True)  # sent, delivered, read

    class Meta:
        db_table = "communication_messages"
        indexes = [
            models.Index(fields=["tenant_id", "channel"]),
            models.Index(fields=["tenant_id", "sender_id"]),
            models.Index(fields=["tenant_id", "recipient_id"]),
            models.Index(fields=["tenant_id", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.channel.channel_code} - {self.subject}"
