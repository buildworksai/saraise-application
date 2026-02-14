"""
Service tests for Fixed Assets module.
"""

import uuid
import pytest
from datetime import date
from decimal import Decimal

from src.modules.fixed_assets.models import FixedAsset
from src.modules.fixed_assets.services import FixedAssetService


@pytest.mark.django_db
class TestFixedAssetService:
    """Test FixedAssetService."""

    def test_create_fixed_asset(self):
        """Test creating a fixed asset via service."""
        tenant_id = uuid.uuid4()
        asset = FixedAssetService.create_fixed_asset(
            tenant_id=str(tenant_id),
            asset_code="FA-001",
            asset_name="Test Fixed Asset",
            purchase_date=date(2024, 1, 1),
            purchase_cost=Decimal("50000.00"),
            asset_category="machinery",
        )

        assert asset.asset_code == "FA-001"
        assert asset.purchase_cost == Decimal("50000.00")
        assert str(asset.tenant_id) == str(tenant_id)
