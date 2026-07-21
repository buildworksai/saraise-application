"""
Regional Models.

Defines data models for Regional module.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models


def generate_uuid() -> str:
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class _TenantBaseModel(models.Model):
    """Base model for tenant-scoped models with Row-Level Multitenancy.

    CRITICAL: All tenant-scoped models MUST inherit from this base class
    and include tenant_id. All queries MUST filter explicitly by tenant_id.
    """

    tenant_id = models.CharField(max_length=36, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Persist only resources with an explicit tenant boundary."""
        if not self.tenant_id:
            raise ValidationError({"tenant_id": "Tenant ID is required."})
        super().save(*args, **kwargs)

    class Meta:
        app_label = "regional"
        abstract = True
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "created_at"]),
        ]


class RegionalResource(_TenantBaseModel):
    """Primary resource model for Regional module.

    TODO: Customize this model with module-specific fields.
    """

    id = models.CharField(
        max_length=36,
        primary_key=True,
        default=generate_uuid,
    )
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    config = models.JSONField(
        default=dict,
        help_text="Module-specific configuration",
    )
    created_by = models.CharField(max_length=36, db_index=True)

    class Meta:
        app_label = "regional"
        db_table = "regional_resources"
        indexes = [
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["tenant_id", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"


# Backward-compatible public name used by the original module contract.
# The abstract implementation base remains private so callers cannot mistake
# an unregistered abstract Django model for the concrete resource manager.
TenantBaseModel = RegionalResource
