"""
Master Data Management Models.

Defines data models for master data entities.
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


class MasterDataEntity(TenantBaseModel):
    """Master data entity model - Generic master data container."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    entity_type = models.CharField(max_length=50, db_index=True)  # customer, supplier, product, employee
    entity_code = models.CharField(max_length=100, db_index=True)
    entity_name = models.CharField(max_length=255)
    data = models.JSONField(default=dict, help_text="Entity-specific data")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "mdm_entities"
        indexes = [
            models.Index(fields=["tenant_id", "entity_type"]),
            models.Index(fields=["tenant_id", "entity_code"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "entity_type", "entity_code"], name="unique_entity_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.entity_type} - {self.entity_code}"
