"""
Tenant Isolation Tests for Master Data Management module.
"""

import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.modules.master_data_management.models import MasterDataEntity

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
class TestMasterDataEntityTenantIsolation:
    """CRITICAL: Tenant isolation tests for MasterDataEntity model."""

    def test_user_cannot_list_other_tenant_entities(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's entities in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create entity for tenant A
        entity_a = MasterDataEntity.objects.create(
            tenant_id=tenant_a_id,
            entity_type="customer",
            entity_code="CUST-A",
            entity_name="Customer A",
        )

        # Create entity for tenant B
        entity_b = MasterDataEntity.objects.create(
            tenant_id=tenant_b_id,
            entity_type="customer",
            entity_code="CUST-B",
            entity_name="Customer B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/master-data-management/entities/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        entity_ids = [e["id"] for e in data]

        # User A should see tenant A's entity, but NOT tenant B's entity
        assert str(entity_a.id) in entity_ids
        assert str(entity_b.id) not in entity_ids

    def test_user_cannot_get_other_tenant_entity_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's entity by ID (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create entity for tenant B
        entity_b = MasterDataEntity.objects.create(
            tenant_id=tenant_b_id,
            entity_type="supplier",
            entity_code="SUP-B",
            entity_name="Supplier B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's entity
        response = api_client.get(f"/api/v1/master-data-management/entities/{entity_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
