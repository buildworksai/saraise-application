"""
Tenant Isolation Tests for IntegrationPlatform module.

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

from ..models import DataMapping, Integration, Webhook
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
class TestIntegrationTenantIsolation:
    """Tenant isolation tests for Integration model."""

    def test_user_cannot_list_other_tenant_integrations(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's integrations in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create integration for tenant A
        integration_a = Integration.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Integration",
            integration_type="api",
            status="active",
            created_by=str(tenant_a_user.id),
        )

        # Create integration for tenant B
        integration_b = Integration.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Integration",
            integration_type="api",
            status="active",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/integration-platform/integrations/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        integration_ids = [i["id"] for i in data]

        # User A should see tenant A's integration, but NOT tenant B's integration
        assert integration_a.id in integration_ids
        assert integration_b.id not in integration_ids

    def test_user_cannot_get_other_tenant_integration_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's integration by ID (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create integration for tenant B
        integration_b = Integration.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Integration",
            integration_type="api",
            status="active",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's integration
        response = api_client.get(f"/api/v1/integration-platform/integrations/{integration_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestWebhookTenantIsolation:
    """Tenant isolation tests for Webhook model."""

    def test_user_cannot_list_other_tenant_webhooks(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's webhooks in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create webhook for tenant A
        webhook_a = Webhook.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Webhook",
            url="https://example.com/webhook-a",
            secret="secret_a",
            created_by=str(tenant_a_user.id),
        )

        # Create webhook for tenant B
        webhook_b = Webhook.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Webhook",
            url="https://example.com/webhook-b",
            secret="secret_b",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/integration-platform/webhooks/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        webhook_ids = [w["id"] for w in data]

        # User A should see tenant A's webhook, but NOT tenant B's webhook
        assert webhook_a.id in webhook_ids
        assert webhook_b.id not in webhook_ids


@pytest.mark.django_db
class TestDataMappingTenantIsolation:
    """Tenant isolation tests for DataMapping model."""

    def test_user_cannot_list_other_tenant_data_mappings(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's data mappings in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create integrations
        integration_a = Integration.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Integration",
            integration_type="api",
            created_by=str(tenant_a_user.id),
        )

        integration_b = Integration.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Integration",
            integration_type="api",
            created_by=str(tenant_b_user.id),
        )

        # Create mappings
        mapping_a = DataMapping.objects.create(
            tenant_id=tenant_a_id,
            integration=integration_a,
            source_field="field_a",
            target_field="target_a",
        )

        mapping_b = DataMapping.objects.create(
            tenant_id=tenant_b_id,
            integration=integration_b,
            source_field="field_b",
            target_field="target_b",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/integration-platform/data-mappings/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        mapping_ids = [m["id"] for m in data]

        # User A should see tenant A's mapping, but NOT tenant B's mapping
        assert mapping_a.id in mapping_ids
        assert mapping_b.id not in mapping_ids
