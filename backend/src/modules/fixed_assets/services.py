"""
Business logic services for Fixed Assets module.
"""

from typing import Optional
from decimal import Decimal
from datetime import date

from .models import FixedAsset


class FixedAssetService:
    """Service for fixed asset operations."""

    @staticmethod
    def create_fixed_asset(tenant_id: str, asset_code: str, asset_name: str, purchase_date: date, purchase_cost: Decimal, **kwargs) -> FixedAsset:
        """Create a new fixed asset."""
        asset = FixedAsset.objects.create(
            tenant_id=tenant_id,
            asset_code=asset_code,
            asset_name=asset_name,
            purchase_date=purchase_date,
            purchase_cost=purchase_cost,
            current_value=purchase_cost,
            **kwargs,
        )
        return asset
