"""
Business logic services for Asset Management module.
"""

from typing import Optional
from decimal import Decimal
from datetime import date
from django.db import transaction

from .models import Asset, DepreciationEntry


class AssetService:
    """Service for asset operations."""

    @staticmethod
    def create_asset(tenant_id: str, asset_code: str, asset_name: str, purchase_date: str, purchase_cost: Decimal, **kwargs) -> Asset:
        """Create a new asset."""
        asset = Asset.objects.create(
            tenant_id=tenant_id,
            asset_code=asset_code,
            asset_name=asset_name,
            purchase_date=purchase_date,
            purchase_cost=purchase_cost,
            current_value=purchase_cost,
            **kwargs,
        )
        return asset


class DepreciationService:
    """Service for depreciation operations."""

    @staticmethod
    @transaction.atomic
    def calculate_depreciation(asset: Asset, entry_date: date) -> DepreciationEntry:
        """Calculate and record depreciation for an asset."""
        if asset.depreciation_method == "straight_line" and asset.useful_life_years:
            monthly_depreciation = asset.purchase_cost / (asset.useful_life_years * 12)
        else:
            monthly_depreciation = Decimal("0.00")

        # Get accumulated depreciation
        previous_entries = DepreciationEntry.objects.filter(asset=asset).order_by("-entry_date")
        accumulated = previous_entries.first().accumulated_depreciation if previous_entries.exists() else Decimal("0.00")
        accumulated += monthly_depreciation

        entry = DepreciationEntry.objects.create(
            tenant_id=asset.tenant_id,
            asset=asset,
            entry_date=entry_date,
            depreciation_amount=monthly_depreciation,
            accumulated_depreciation=accumulated,
            book_value=asset.purchase_cost - accumulated,
        )

        # Update asset current value
        asset.current_value = entry.book_value
        asset.save()

        return entry
