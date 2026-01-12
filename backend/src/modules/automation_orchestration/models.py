"""
AutomationOrchestration Models.

Defines data models for AutomationOrchestration module.
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

    tenant_id = models.CharField(max_length=36, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "automation_orchestration"
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class AutomationOrchestrationResource(TenantBaseModel):
    """Primary resource model for AutomationOrchestration module.

    TODO: Customize this model with module-specific fields.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    config = models.JSONField(default=dict, help_text="Module-specific configuration")
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        app_label = "automation_orchestration"
        db_table = "automation_orchestration_resources"
        indexes = [
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["tenant_id", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"
