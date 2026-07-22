"""Tenant-safe persistence for the asset lifecycle.

Assets are soft deleted so their financial history remains explainable.
Depreciation entries are an append-only ledger: correcting an error means
creating a compensating business event, never rewriting posted history.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from src.core.tenancy import TENANT_SCOPED, TenantQuerySet, TenantScopedModel, TimestampedModel, tenancy_scope


class AssetCategory(models.TextChoices):
    """Supported accounting classifications."""

    FIXED = "fixed", "Fixed Asset"
    INTANGIBLE = "intangible", "Intangible Asset"
    CURRENT = "current", "Current Asset"


class DepreciationMethod(models.TextChoices):
    """Methods supported by the calculation service."""

    STRAIGHT_LINE = "straight_line", "Straight line"
    DECLINING_BALANCE = "declining_balance", "Declining balance"
    NONE = "none", "Not depreciated"


@tenancy_scope(TENANT_SCOPED)
class Asset(TenantScopedModel, TimestampedModel):
    """A tenant-owned tangible or intangible asset."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset_code = models.CharField(max_length=50)
    asset_name = models.CharField(max_length=255)
    category = models.CharField(max_length=50, choices=AssetCategory.choices, default=AssetCategory.FIXED)
    purchase_date = models.DateField()
    purchase_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    residual_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    current_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    depreciation_method = models.CharField(
        max_length=50,
        choices=DepreciationMethod.choices,
        default=DepreciationMethod.NONE,
    )
    useful_life_years = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )
    declining_balance_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Optional annual percentage; double-declining rate is used when omitted.",
        validators=[MinValueValidator(Decimal("0.0001")), MaxValueValidator(Decimal("100.0000"))],
    )
    location = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False, editable=False)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "asset_assets"
        ordering = ("asset_code",)
        indexes = [
            models.Index(fields=("tenant_id", "asset_code"), name="asset_tenant_code_idx"),
            models.Index(fields=("tenant_id", "category", "is_deleted"), name="asset_tenant_cat_del_idx"),
            models.Index(fields=("tenant_id", "is_active", "is_deleted"), name="asset_tenant_active_idx"),
            models.Index(fields=("tenant_id", "purchase_date"), name="asset_tenant_date_idx"),
            models.Index(fields=("tenant_id", "created_at"), name="asset_tenant_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "asset_code"),
                name="asset_code_tenant_uniq",
            ),
            models.CheckConstraint(condition=Q(purchase_cost__gt=0), name="asset_purchase_cost_pos"),
            models.CheckConstraint(
                condition=Q(residual_value__gte=0) & Q(residual_value__lte=F("purchase_cost")),
                name="asset_residual_valid",
            ),
            models.CheckConstraint(
                condition=(Q(current_value__gte=F("residual_value")) & Q(current_value__lte=F("purchase_cost"))),
                name="asset_current_value_valid",
            ),
            models.CheckConstraint(
                condition=Q(depreciation_method=DepreciationMethod.NONE) | Q(useful_life_years__isnull=False),
                name="asset_useful_life_required",
            ),
            models.CheckConstraint(
                condition=Q(declining_balance_rate__isnull=True)
                | (Q(declining_balance_rate__gt=0) & Q(declining_balance_rate__lte=100)),
                name="asset_declining_rate_valid",
            ),
            models.CheckConstraint(
                condition=(Q(is_deleted=False, deleted_at__isnull=True) | Q(is_deleted=True, deleted_at__isnull=False)),
                name="asset_delete_state_valid",
            ),
        ]

    def clean(self) -> None:
        """Normalize identifiers and enforce cross-field business rules."""

        self.asset_code = self.asset_code.strip().upper()
        self.asset_name = self.asset_name.strip()
        self.location = self.location.strip()
        if not self.asset_code:
            raise ValidationError({"asset_code": "Asset code is required."})
        if not self.asset_name:
            raise ValidationError({"asset_name": "Asset name is required."})
        if self.category == AssetCategory.CURRENT and self.depreciation_method != DepreciationMethod.NONE:
            raise ValidationError({"depreciation_method": "Current assets are not depreciated."})
        if self.depreciation_method != DepreciationMethod.NONE and not self.useful_life_years:
            raise ValidationError({"useful_life_years": "A useful life is required for depreciable assets."})
        if self.depreciation_method != DepreciationMethod.DECLINING_BALANCE and self.declining_balance_rate is not None:
            raise ValidationError(
                {"declining_balance_rate": "A declining-balance rate is only valid with declining balance."}
            )

    def __str__(self) -> str:
        return f"{self.asset_code} - {self.asset_name}"


class AppendOnlyDepreciationQuerySet(TenantQuerySet):
    """Block bulk mutation paths that bypass ``DepreciationEntry.save``."""

    def update(self, **kwargs: object) -> int:
        del kwargs
        raise ValidationError("Depreciation history is immutable.", code="immutable_history")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Depreciation history is immutable.", code="immutable_history")


@tenancy_scope(TENANT_SCOPED)
class DepreciationEntry(TenantScopedModel, TimestampedModel):
    """An immutable depreciation ledger entry for one accounting date."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="depreciation_entries")
    entry_date = models.DateField()
    depreciation_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    accumulated_depreciation = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    book_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    objects = AppendOnlyDepreciationQuerySet.as_manager()

    class Meta:
        db_table = "asset_depreciation_entries"
        ordering = ("-entry_date", "-created_at")
        indexes = [
            models.Index(fields=("tenant_id", "asset", "entry_date"), name="asset_depr_asset_date_idx"),
            models.Index(fields=("tenant_id", "entry_date"), name="asset_depr_date_idx"),
            models.Index(fields=("tenant_id", "created_at"), name="asset_depr_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "asset", "entry_date"),
                name="asset_depr_date_uniq",
            ),
            models.CheckConstraint(condition=Q(depreciation_amount__gte=0), name="asset_depr_amount_valid"),
            models.CheckConstraint(
                condition=Q(accumulated_depreciation__gte=0),
                name="asset_depr_accum_valid",
            ),
            models.CheckConstraint(condition=Q(book_value__gte=0), name="asset_depr_book_valid"),
        ]

    def clean(self) -> None:
        if self.asset_id and self.tenant_id and self.asset.tenant_id != self.tenant_id:
            raise ValidationError({"asset": "Asset was not found for this tenant."}, code="cross_tenant_reference")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk and self.tenant_id and type(self).objects.for_tenant(self.tenant_id).filter(pk=self.pk).exists():
            raise ValidationError("Depreciation history is immutable.", code="immutable_history")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Depreciation history is immutable.", code="immutable_history")

    def __str__(self) -> str:
        return f"{self.asset.asset_code} - {self.entry_date} - {self.depreciation_amount}"
