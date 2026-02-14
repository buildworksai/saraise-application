"""
Service tests for Asset Management module.
"""

import uuid
import pytest
from datetime import date
from decimal import Decimal

from src.modules.asset_management.models import Asset
from src.modules.asset_management.services import AssetService


@pytest.mark.django_db
class TestAssetService:
    """Test AssetService."""

    def test_create_asset(self):
        """Test creating an asset via service."""
        tenant_id = uuid.uuid4()
        asset = AssetService.create_asset(
            tenant_id=str(tenant_id),
            asset_code="AST-001",
            asset_name="Test Asset",
            purchase_date=date(2024, 1, 1),
            purchase_cost=Decimal("10000.00"),
        )

        assert asset.asset_code == "AST-001"
        assert asset.purchase_cost == Decimal("10000.00")
        assert str(asset.tenant_id) == str(tenant_id)
