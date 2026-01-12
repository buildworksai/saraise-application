"""Egress Allowlisting Models.

Database models for egress allowlisting and secret isolation.
Task: 402.1 - Egress Allowlisting & Secret Isolation
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from django.db import models
from django.utils import timezone

from .models import TenantBaseModel


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class EgressRule(TenantBaseModel):
    """Egress allowlist rule model.

    Defines allowed egress destinations for AI agents.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    destination_type = models.CharField(
        max_length=50,
        choices=[
            ("domain", "Domain"),
            ("ip", "IP Address"),
            ("cidr", "CIDR Block"),
            ("url_pattern", "URL Pattern"),
        ],
        db_index=True,
        help_text="Type of destination",
    )
    destination = models.CharField(
        max_length=500,
        db_index=True,
        help_text="Destination (domain, IP, CIDR, or URL pattern)",
    )
    port = models.IntegerField(
        null=True,
        blank=True,
        help_text="Port number (null for all ports)",
    )
    protocol = models.CharField(
        max_length=10,
        choices=[
            ("http", "HTTP"),
            ("https", "HTTPS"),
            ("tcp", "TCP"),
            ("udp", "UDP"),
            ("all", "All"),
        ],
        default="https",
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.CharField(max_length=36, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_egress_rules"
        indexes = [
            models.Index(fields=["tenant_id", "destination_type"]),
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["tenant_id", "destination"]),
        ]

    def __str__(self) -> str:
        return f"Egress Rule: {self.destination} ({self.destination_type})"


class EgressRequest(TenantBaseModel):
    """Egress request tracking model.

    Tracks egress requests for audit and monitoring.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    agent_execution = models.ForeignKey(
        "AgentExecution",
        on_delete=models.CASCADE,
        related_name="egress_requests",
        db_index=True,
    )
    destination = models.CharField(max_length=500, db_index=True, help_text="Requested destination")
    port = models.IntegerField(null=True, blank=True)
    protocol = models.CharField(max_length=10, db_index=True)
    allowed = models.BooleanField(db_index=True, help_text="Whether request was allowed")
    matched_rule = models.ForeignKey(
        EgressRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matched_requests",
        db_index=True,
    )
    requested_at = models.DateTimeField(auto_now_add=True, db_index=True)
    metadata = models.JSONField(default=dict, help_text="Request metadata")

    class Meta:
        db_table = "ai_egress_requests"
        indexes = [
            models.Index(fields=["tenant_id", "agent_execution_id"]),
            models.Index(fields=["tenant_id", "allowed"]),
            models.Index(fields=["tenant_id", "requested_at"]),
        ]

    def __str__(self) -> str:
        return f"Egress Request {self.id} to {self.destination} ({'allowed' if self.allowed else 'blocked'})"


class Secret(TenantBaseModel):
    """Secret storage model.

    Stores secrets for AI agents with per-tenant isolation.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    secret_type = models.CharField(
        max_length=50,
        choices=[
            ("api_key", "API Key"),
            ("password", "Password"),
            ("token", "Token"),
            ("certificate", "Certificate"),
            ("other", "Other"),
        ],
        db_index=True,
    )
    encrypted_value = models.TextField(help_text="Encrypted secret value (base64 encoded)")
    encryption_key_id = models.CharField(
        max_length=100,
        help_text="Key ID used for encryption",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True, help_text="Secret expiration time")
    last_rotated_at = models.DateTimeField(null=True, blank=True, help_text="When secret was last rotated")
    rotation_interval_days = models.IntegerField(
        null=True,
        blank=True,
        help_text="Rotation interval in days",
    )
    created_by = models.CharField(max_length=36, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_secrets"
        indexes = [
            models.Index(fields=["tenant_id", "name"]),
            models.Index(fields=["tenant_id", "secret_type"]),
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["tenant_id", "expires_at"]),
        ]
        unique_together = [["tenant_id", "name"]]

    def __str__(self) -> str:
        return f"Secret {self.name} ({self.secret_type})"


class SecretAccess(TenantBaseModel):
    """Secret access tracking model.

    Tracks secret access for audit and monitoring.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    secret = models.ForeignKey(
        Secret,
        on_delete=models.CASCADE,
        related_name="access_logs",
        db_index=True,
    )
    agent_execution = models.ForeignKey(
        "AgentExecution",
        on_delete=models.CASCADE,
        related_name="secret_accesses",
        null=True,
        blank=True,
        db_index=True,
    )
    accessed_by = models.CharField(max_length=36, db_index=True, help_text="User/agent who accessed secret")
    accessed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    metadata = models.JSONField(default=dict, help_text="Access metadata")

    class Meta:
        db_table = "ai_secret_accesses"
        indexes = [
            models.Index(fields=["tenant_id", "secret_id"]),
            models.Index(fields=["tenant_id", "agent_execution_id"]),
            models.Index(fields=["tenant_id", "accessed_by"]),
            models.Index(fields=["tenant_id", "accessed_at"]),
        ]

    def __str__(self) -> str:
        return f"Secret Access {self.id} for {self.secret.name}"
