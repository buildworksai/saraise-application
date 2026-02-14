"""
Model tests for Asset Management module.
"""

import uuid
import pytest
from datetime import date
from decimal import Decimal

from src.modules.asset_management.models import Asset


@pytest.mark.django_db
class TestAssetModel:
    """Test Asset model."""

    def test_create_asset(self):
        """Test creating an asset."""
        tenant_id = uuid.uuid4()
        asset = Asset.objects.create(
            tenant_id=tenant_id,
            asset_code="AST-001",
            asset_name="Test Asset",
            purchase_date=date(2024, 1, 1),
            purchase_cost=Decimal("10000.00"),
            current_value=Decimal("10000.00"),
        )
        assert asset.asset_code == "AST-001"
        assert asset.purchase_cost == Decimal("10000.00")
        assert asset.current_value == Decimal("10000.00")
        assert asset.is_active is True
