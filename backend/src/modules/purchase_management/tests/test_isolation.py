"""
Tenant Isolation Tests for Purchase Management module.
"""

import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.modules.purchase_management.models import PurchaseOrder, Supplier

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
class TestSupplierTenantIsolation:
    """CRITICAL: Tenant isolation tests for Supplier model."""

    def test_user_cannot_list_other_tenant_suppliers(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's suppliers in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create supplier for tenant A
        supplier_a = Supplier.objects.create(
            tenant_id=tenant_a_id,
            supplier_code="SUP-A",
            supplier_name="Supplier A",
        )

        # Create supplier for tenant B
        supplier_b = Supplier.objects.create(
            tenant_id=tenant_b_id,
            supplier_code="SUP-B",
            supplier_name="Supplier B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/purchase-management/suppliers/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        supplier_ids = [s["id"] for s in data]

        # User A should see tenant A's supplier, but NOT tenant B's supplier
        assert str(supplier_a.id) in supplier_ids
        assert str(supplier_b.id) not in supplier_ids

    def test_user_cannot_get_other_tenant_supplier_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's supplier by ID (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create supplier for tenant B
        supplier_b = Supplier.objects.create(
            tenant_id=tenant_b_id,
            supplier_code="SUP-B",
            supplier_name="Supplier B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's supplier
        response = api_client.get(f"/api/v1/purchase-management/suppliers/{supplier_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestPurchaseOrderTenantIsolation:
    """CRITICAL: Tenant isolation tests for PurchaseOrder model."""

    def test_user_cannot_list_other_tenant_purchase_orders(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's purchase orders in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        from datetime import date

        # Create supplier and PO for tenant A
        supplier_a = Supplier.objects.create(
            tenant_id=tenant_a_id,
            supplier_code="SUP-A",
            supplier_name="Supplier A",
        )
        po_a = PurchaseOrder.objects.create(
            tenant_id=tenant_a_id,
            po_number="PO-001",
            po_date=date(2024, 1, 1),
            supplier=supplier_a,
        )

        # Create supplier and PO for tenant B
        supplier_b = Supplier.objects.create(
            tenant_id=tenant_b_id,
            supplier_code="SUP-B",
            supplier_name="Supplier B",
        )
        po_b = PurchaseOrder.objects.create(
            tenant_id=tenant_b_id,
            po_number="PO-001",
            po_date=date(2024, 1, 1),
            supplier=supplier_b,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/purchase-management/purchase-orders/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        po_ids = [p["id"] for p in data]

        # User A should see tenant A's PO, but NOT tenant B's PO
        assert str(po_a.id) in po_ids
        assert str(po_b.id) not in po_ids
