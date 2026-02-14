"""
Tenant Isolation Tests for Fixed Assets module.
"""

import uuid
import pytest
from datetime import date
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.modules.fixed_assets.models import FixedAsset

User = get_user_model()


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def tenant_a_user(db):
    """Create user for tenant A."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_a",
        email="usera@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    return User.objects.get(pk=user.pk)


@pytest.fixture
def tenant_b_user(db):
    """Create user for tenant B."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_b",
        email="userb@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    return User.objects.get(pk=user.pk)


@pytest.mark.django_db
class TestFixedAssetTenantIsolation:
    """CRITICAL: Tenant isolation tests for FixedAsset model."""

    def test_user_cannot_list_other_tenant_fixed_assets(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's fixed assets in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        from decimal import Decimal

        # Create fixed asset for tenant A
        asset_a = FixedAsset.objects.create(
            tenant_id=tenant_a_id,
            asset_code="FA-A",
            asset_name="Fixed Asset A",
            asset_category="machinery",
            purchase_date=date(2024, 1, 1),
            purchase_cost=Decimal("50000.00"),
        )

        # Create fixed asset for tenant B
        asset_b = FixedAsset.objects.create(
            tenant_id=tenant_b_id,
            asset_code="FA-B",
            asset_name="Fixed Asset B",
            asset_category="vehicle",
            purchase_date=date(2024, 1, 1),
            purchase_cost=Decimal("30000.00"),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/fixed-assets/assets/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        asset_ids = [a["id"] for a in data]

        # User A should see tenant A's asset, but NOT tenant B's asset
        assert str(asset_a.id) in asset_ids
        assert str(asset_b.id) not in asset_ids

    def test_user_cannot_get_other_tenant_fixed_asset_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's fixed asset by ID (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        from decimal import Decimal

        # Create fixed asset for tenant B
        asset_b = FixedAsset.objects.create(
            tenant_id=tenant_b_id,
            asset_code="FA-B",
            asset_name="Fixed Asset B",
            asset_category="vehicle",
            purchase_date=date(2024, 1, 1),
            purchase_cost=Decimal("30000.00"),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's fixed asset
        response = api_client.get(f"/api/v1/fixed-assets/assets/{asset_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
