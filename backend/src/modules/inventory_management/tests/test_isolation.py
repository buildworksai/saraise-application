"""
Tenant Isolation Tests for Inventory Management module.

CRITICAL: These tests verify that tenants cannot access each other's data.
"""

import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.modules.inventory_management.models import Item, Warehouse

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
class TestWarehouseTenantIsolation:
    """CRITICAL: Tenant isolation tests for Warehouse model."""

    def test_user_cannot_list_other_tenant_warehouses(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's warehouses in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create warehouse for tenant A
        warehouse_a = Warehouse.objects.create(
            tenant_id=tenant_a_id,
            warehouse_code="WH-A",
            warehouse_name="Warehouse A",
        )

        # Create warehouse for tenant B
        warehouse_b = Warehouse.objects.create(
            tenant_id=tenant_b_id,
            warehouse_code="WH-B",
            warehouse_name="Warehouse B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/inventory-management/warehouses/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        warehouse_ids = [w["id"] for w in data]

        # User A should see tenant A's warehouse, but NOT tenant B's warehouse
        assert str(warehouse_a.id) in warehouse_ids
        assert str(warehouse_b.id) not in warehouse_ids

    def test_user_cannot_get_other_tenant_warehouse_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's warehouse by ID (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create warehouse for tenant B
        warehouse_b = Warehouse.objects.create(
            tenant_id=tenant_b_id,
            warehouse_code="WH-B",
            warehouse_name="Warehouse B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's warehouse
        response = api_client.get(f"/api/v1/inventory-management/warehouses/{warehouse_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestItemTenantIsolation:
    """CRITICAL: Tenant isolation tests for Item model."""

    def test_user_cannot_list_other_tenant_items(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's items in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create item for tenant A
        item_a = Item.objects.create(
            tenant_id=tenant_a_id,
            item_code="ITEM-A",
            item_name="Item A",
        )

        # Create item for tenant B
        item_b = Item.objects.create(
            tenant_id=tenant_b_id,
            item_code="ITEM-B",
            item_name="Item B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/inventory-management/items/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        item_ids = [i["id"] for i in data]

        # User A should see tenant A's item, but NOT tenant B's item
        assert str(item_a.id) in item_ids
        assert str(item_b.id) not in item_ids

    def test_user_cannot_get_other_tenant_item_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's item by ID (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create item for tenant B
        item_b = Item.objects.create(
            tenant_id=tenant_b_id,
            item_code="ITEM-B",
            item_name="Item B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's item
        response = api_client.get(f"/api/v1/inventory-management/items/{item_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
