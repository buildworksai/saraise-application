"""
Model tests for Fixed Assets module.
"""

import uuid
import pytest
from datetime import date
from decimal import Decimal

from src.modules.fixed_assets.models import FixedAsset


@pytest.mark.django_db
class TestFixedAssetModel:
    """Test FixedAsset model."""

    def test_create_fixed_asset(self):
        """Test creating a fixed asset."""
        tenant_id = uuid.uuid4()
        asset = FixedAsset.objects.create(
            tenant_id=tenant_id,
            asset_code="FA-001",
            asset_name="Test Fixed Asset",
            asset_category="machinery",
            purchase_date=date(2024, 1, 1),
            purchase_cost=Decimal("50000.00"),
            current_value=Decimal("50000.00"),
        )
        assert asset.asset_code == "FA-001"
        assert asset.purchase_cost == Decimal("50000.00")
        assert asset.current_value == Decimal("50000.00")
        assert asset.is_active is True
