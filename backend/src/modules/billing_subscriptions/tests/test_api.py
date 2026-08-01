"""
API Integration Tests for BillingSubscriptions module.

Tests all DRF ViewSet endpoints:
- CRUD operations
- Authentication/authorization
- Tenant isolation
- Custom actions
"""

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.modules.billing_subscriptions.models import Subscription, SubscriptionPlan, UsageRecord

User = get_user_model()


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def tenant_user(db):
    """Create a test user with tenant."""

    from src.core.licensing.models import Organization
    from src.core.user_models import UserProfile

    # Create a valid Organization for the tenant
    org = Organization.objects.create(name="Test Organization")
    tenant_id = str(org.id)

    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    profile = UserProfile.objects.get(user=user)
    profile.tenant_id = tenant_id
    profile.tenant_role = "tenant_admin"
    profile.save()

    return User.objects.get(pk=user.pk)


@pytest.fixture
def authenticated_client(api_client, tenant_user):
    """Create authenticated API client."""
    api_client.force_authenticate(user=tenant_user)
    return api_client


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.mark.django_db
class TestBillingSubscriptionsAPI:
    """Test registered BillingSubscriptions API endpoints."""

    def test_list_plans_requires_authentication(self, api_client):
        """Test that billing endpoints require authentication."""
        response = api_client.get("/api/v1/billing-subscriptions/plans/")
        assert response.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}

    def test_list_plans_returns_only_active_platform_plans(self, authenticated_client):
        """Test listing active platform-level subscription plans."""
        active = SubscriptionPlan.objects.create(
            name="Growth",
            description="Growth tier",
            price="99.00",
            billing_cycle="monthly",
            features=["crm"],
            limits={"users": 25},
            is_active=True,
        )
        SubscriptionPlan.objects.create(
            name="Retired",
            description="Retired tier",
            price="19.00",
            billing_cycle="monthly",
            is_active=False,
        )

        response = authenticated_client.get("/api/v1/billing-subscriptions/plans/")

        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert [item["id"] for item in data] == [active.id]

    def test_list_subscriptions_filters_to_authenticated_tenant(self, authenticated_client, tenant_user):
        """Test subscription listing does not expose another tenant's records."""
        tenant_id = get_user_tenant_id(tenant_user)
        other_tenant_id = "11111111-1111-4111-8111-111111111111"
        plan = SubscriptionPlan.objects.create(
            name="Tenant Plan",
            description="Tenant tier",
            price="49.00",
            billing_cycle="monthly",
            is_active=True,
        )
        own = Subscription.objects.create(
            tenant_id=tenant_id,
            plan=plan,
            status="active",
            start_date=timezone.now().date(),
        )
        Subscription.objects.create(
            tenant_id=other_tenant_id,
            plan=plan,
            status="active",
            start_date=timezone.now().date(),
        )

        response = authenticated_client.get("/api/v1/billing-subscriptions/subscriptions/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert [item["id"] for item in data] == [own.id]

    def test_create_usage_record_sets_authenticated_tenant(self, authenticated_client, tenant_user):
        """Test usage-record create derives tenant from the session identity."""
        tenant_id = get_user_tenant_id(tenant_user)

        data = {
            "resource_type": "api_calls",
            "quantity": "42.0000",
        }

        response = authenticated_client.post("/api/v1/billing-subscriptions/usage-records/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["tenant_id"] == tenant_id
        assert str(UsageRecord.objects.get(id=response.data["id"]).tenant_id) == tenant_id

    def test_quota_list_does_not_require_platform_tenant_row(self, authenticated_client):
        """Quota UI can render for authenticated tenants before tenant-management sync exists."""

        response = authenticated_client.get("/api/v1/billing-subscriptions/quotas/")

        assert response.status_code == status.HTTP_200_OK
        assert set(response.data) == {"users", "storage", "api_calls"}
        assert response.data["users"] == {"used": 0, "limit": 0}
        assert response.data["storage"] == {"used": 0.0, "limit": 0}
