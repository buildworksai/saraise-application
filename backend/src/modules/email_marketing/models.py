"""
Email Marketing Models.

Defines data models for campaigns, templates, and email analytics.
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


class EmailCampaign(TenantBaseModel):
    """Email campaign model - Marketing email campaign."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    campaign_code = models.CharField(max_length=50, db_index=True)
    campaign_name = models.CharField(max_length=255)
    subject = models.CharField(max_length=500)
    template_id = models.UUIDField(null=True, blank=True, help_text="FK to email template")
    status = models.CharField(max_length=50, default="draft", db_index=True)  # draft, scheduled, sent, completed
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    recipient_count = models.IntegerField(default=0)
    opened_count = models.IntegerField(default=0)
    clicked_count = models.IntegerField(default=0)

    class Meta:
        db_table = "email_campaigns"
        indexes = [
            models.Index(fields=["tenant_id", "campaign_code"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "scheduled_at"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "campaign_code"], name="unique_campaign_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.campaign_code} - {self.campaign_name}"


class EmailTemplate(TenantBaseModel):
    """Email template model - Reusable email template."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    template_code = models.CharField(max_length=50, db_index=True)
    template_name = models.CharField(max_length=255)
    subject = models.CharField(max_length=500)
    body_html = models.TextField()
    body_text = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "email_templates"
        indexes = [
            models.Index(fields=["tenant_id", "template_code"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "template_code"], name="unique_template_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.template_code} - {self.template_name}"
