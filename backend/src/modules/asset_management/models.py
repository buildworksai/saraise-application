"""
Asset Management Models.

Defines data models for assets, depreciation, and asset tracking.
All models include tenant_id for Row-Level Multitenancy.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from django.core.validators import MinValueValidator
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


class AssetCategory(models.TextChoices):
    """Asset category choices."""

    FIXED = "fixed", "Fixed Asset"
    INTANGIBLE = "intangible", "Intangible Asset"
    CURRENT = "current", "Current Asset"


class Asset(TenantBaseModel):
    """Asset model - Fixed or intangible asset."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    asset_code = models.CharField(max_length=50, db_index=True)
    asset_name = models.CharField(max_length=255)
    category = models.CharField(max_length=50, choices=AssetCategory.choices, default=AssetCategory.FIXED)
    purchase_date = models.DateField(db_index=True)
    purchase_cost = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    current_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    depreciation_method = models.CharField(max_length=50, default="straight_line")  # straight_line, declining_balance
    useful_life_years = models.IntegerField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "asset_assets"
        indexes = [
            models.Index(fields=["tenant_id", "asset_code"]),
            models.Index(fields=["tenant_id", "category"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "asset_code"], name="unique_asset_code_per_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.asset_code} - {self.asset_name}"


class DepreciationEntry(TenantBaseModel):
    """Depreciation entry model - Monthly/Annual depreciation record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="depreciation_entries")
    entry_date = models.DateField(db_index=True)
    depreciation_amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    accumulated_depreciation = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    book_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        db_table = "asset_depreciation_entries"
        indexes = [
            models.Index(fields=["tenant_id", "asset"]),
            models.Index(fields=["tenant_id", "entry_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.asset.asset_code} - {self.entry_date} - {self.depreciation_amount}"
