"""
Tenant Isolation Tests for MetadataModeling module.

CRITICAL: These tests verify that tenants cannot access each other's data.
This is the PRIMARY security mechanism for multi-tenant isolation.

Reference: saraise-documentation/rules/compliance-enforcement.md
Rule: ALL tenant-scoped queries MUST filter by tenant_id
"""
import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from ..models import EntityDefinition, DynamicResource
from src.core.auth_utils import get_user_tenant_id

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
class TestMetadataModelingTenantIsolation:
    """
    CRITICAL: Tenant isolation tests for MetadataModeling module.
    These tests verify that tenants cannot access each other's EntityDefinition and DynamicResource data.
    """

    def test_user_cannot_list_other_tenant_entity_definitions(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's entity definitions in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create entity definition for tenant A
        entity_a = EntityDefinition.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Entity",
            code="tenant_a_entity",
            description="Entity for tenant A",
        )

        # Create entity definition for tenant B
        entity_b = EntityDefinition.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Entity",
            code="tenant_b_entity",
            description="Entity for tenant B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/metadata-modeling/entity-definitions/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        entity_ids = [str(e["id"]) for e in data]

        # User A should see tenant A's entity, but NOT tenant B's entity
        assert str(entity_a.id) in entity_ids
        assert str(entity_b.id) not in entity_ids

    def test_user_cannot_get_other_tenant_entity_definition(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's entity definition by ID (returns 404)."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create entity definition for tenant B
        entity_b = EntityDefinition.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Entity",
            code="tenant_b_entity",
            description="Entity for tenant B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's entity definition
        response = api_client.get(f"/api/v1/metadata-modeling/entity-definitions/{entity_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_entity_definition(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot UPDATE other tenant's entity definition (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create entity definition for tenant B
        entity_b = EntityDefinition.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Entity",
            code="tenant_b_entity",
            description="Entity for tenant B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to update tenant B's entity definition
        data = {"name": "Hacked Name", "code": "hacked_code"}
        response = api_client.put(
            f"/api/v1/metadata-modeling/entity-definitions/{entity_b.id}/",
            data,
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify entity definition was not modified
        entity_b.refresh_from_db()
        assert entity_b.name == "Tenant B Entity"
        assert entity_b.code == "tenant_b_entity"

    def test_user_cannot_delete_other_tenant_entity_definition(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot DELETE other tenant's entity definition (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create entity definition for tenant B
        entity_b = EntityDefinition.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Entity",
            code="tenant_b_entity",
            description="Entity for tenant B",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to delete tenant B's entity definition
        response = api_client.delete(f"/api/v1/metadata-modeling/entity-definitions/{entity_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify entity definition still exists
        assert EntityDefinition.objects.filter(id=entity_b.id).exists()

    def test_user_cannot_list_other_tenant_resources(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's dynamic resources in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create entity definitions for both tenants
        entity_a = EntityDefinition.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Entity",
            code="tenant_a_entity",
            description="Entity for tenant A",
        )

        entity_b = EntityDefinition.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Entity",
            code="tenant_b_entity",
            description="Entity for tenant B",
        )

        # Create dynamic resource for tenant A
        resource_a = DynamicResource.objects.create(
            tenant_id=tenant_a_id,
            entity_definition=entity_a,
            data={"field1": "value1"},
            created_by=tenant_a_user,
        )

        # Create dynamic resource for tenant B
        resource_b = DynamicResource.objects.create(
            tenant_id=tenant_b_id,
            entity_definition=entity_b,
            data={"field1": "value2"},
            created_by=tenant_b_user,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/metadata-modeling/resources/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        resource_ids = [str(r["id"]) for r in data]

        # User A should see tenant A's resource, but NOT tenant B's resource
        assert str(resource_a.id) in resource_ids
        assert str(resource_b.id) not in resource_ids

    def test_user_cannot_get_other_tenant_resource(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's dynamic resource by ID (returns 404)."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create entity definition for tenant B
        entity_b = EntityDefinition.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Entity",
            code="tenant_b_entity",
            description="Entity for tenant B",
        )

        # Create dynamic resource for tenant B
        resource_b = DynamicResource.objects.create(
            tenant_id=tenant_b_id,
            entity_definition=entity_b,
            data={"field1": "value1"},
            created_by=tenant_b_user,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's resource
        response = api_client.get(f"/api/v1/metadata-modeling/resources/{resource_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_resource(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot UPDATE other tenant's dynamic resource (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create entity definition for tenant B
        entity_b = EntityDefinition.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Entity",
            code="tenant_b_entity",
            description="Entity for tenant B",
        )

        # Create dynamic resource for tenant B
        resource_b = DynamicResource.objects.create(
            tenant_id=tenant_b_id,
            entity_definition=entity_b,
            data={"field1": "original_value"},
            created_by=tenant_b_user,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to update tenant B's resource
        data = {"data": {"field1": "hacked_value"}}
        response = api_client.put(
            f"/api/v1/metadata-modeling/resources/{resource_b.id}/",
            data,
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify resource was not modified
        resource_b.refresh_from_db()
        assert resource_b.data == {"field1": "original_value"}

    def test_user_cannot_delete_other_tenant_resource(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot DELETE other tenant's dynamic resource (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create entity definition for tenant B
        entity_b = EntityDefinition.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Entity",
            code="tenant_b_entity",
            description="Entity for tenant B",
        )

        # Create dynamic resource for tenant B
        resource_b = DynamicResource.objects.create(
            tenant_id=tenant_b_id,
            entity_definition=entity_b,
            data={"field1": "value1"},
            created_by=tenant_b_user,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to delete tenant B's resource
        response = api_client.delete(f"/api/v1/metadata-modeling/resources/{resource_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify resource still exists
        assert DynamicResource.objects.filter(id=resource_b.id).exists()
