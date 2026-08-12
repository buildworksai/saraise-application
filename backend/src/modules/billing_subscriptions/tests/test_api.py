"""
API Integration Tests for BillingSubscriptions module.

Tests all DRF ViewSet endpoints:
- CRUD operations
- Authentication/authorization
- Tenant isolation
- Custom actions
"""

from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.modules.billing_subscriptions import api
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


class RecordingQuerySet:
    def __init__(self):
        self.calls = []

    def filter(self, **kwargs):
        self.calls.append(("filter", kwargs))
        return self

    def order_by(self, *fields):
        self.calls.append(("order_by", fields))
        return self


class RecordingManager:
    def __init__(self):
        self.queryset = RecordingQuerySet()
        self.none_called = False

    def filter(self, **kwargs):
        return self.queryset.filter(**kwargs)

    def none(self):
        self.none_called = True
        return self.queryset


def _view(view_cls, query_params=None, data=None):
    view = view_cls()
    view.request = SimpleNamespace(
        user=SimpleNamespace(),
        query_params=query_params or {},
        data=data or {},
    )
    return view


def test_subscription_plan_queryset_filters_active_plans_by_billing_cycle(monkeypatch):
    manager = RecordingManager()
    monkeypatch.setattr(api.SubscriptionPlan, "objects", manager)
    view = _view(api.SubscriptionPlanViewSet, {"billing_cycle": "yearly"})

    assert view.get_queryset() is manager.queryset
    assert manager.queryset.calls == [
        ("filter", {"is_active": True}),
        ("filter", {"billing_cycle": "yearly"}),
        ("order_by", ("price",)),
    ]


def test_tenant_scoped_viewsets_fail_closed_without_tenant_and_apply_allowed_filters(monkeypatch):
    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: None)

    subscription_manager = RecordingManager()
    monkeypatch.setattr(api.Subscription, "objects", subscription_manager)
    assert _view(api.SubscriptionViewSet).get_queryset() is subscription_manager.queryset
    assert subscription_manager.none_called is True

    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: "tenant-1")
    subscription_view = _view(api.SubscriptionViewSet, {"status": "active"})
    subscription_view.get_queryset()
    assert subscription_manager.queryset.calls[-3:] == [
        ("filter", {"tenant_id": "tenant-1"}),
        ("filter", {"status": "active"}),
        ("order_by", ("-created_at",)),
    ]

    invoice_manager = RecordingManager()
    monkeypatch.setattr(api.Invoice, "objects", invoice_manager)
    invoice_view = _view(api.InvoiceViewSet, {"subscription_id": "sub-1", "status": "paid"})
    invoice_view.get_queryset()
    assert invoice_manager.queryset.calls == [
        ("filter", {"tenant_id": "tenant-1"}),
        ("filter", {"subscription_id": "sub-1"}),
        ("filter", {"status": "paid"}),
        ("order_by", ("-created_at",)),
    ]

    payment_manager = RecordingManager()
    monkeypatch.setattr(api.Payment, "objects", payment_manager)
    payment_view = _view(api.PaymentViewSet, {"invoice_id": "inv-1", "status": "succeeded"})
    payment_view.get_queryset()
    assert payment_manager.queryset.calls == [
        ("filter", {"tenant_id": "tenant-1"}),
        ("filter", {"invoice_id": "inv-1"}),
        ("filter", {"status": "succeeded"}),
        ("order_by", ("-created_at",)),
    ]

    usage_manager = RecordingManager()
    monkeypatch.setattr(api.UsageRecord, "objects", usage_manager)
    usage_view = _view(api.UsageRecordViewSet, {"resource_type": "api_calls"})
    usage_view.get_queryset()
    assert usage_manager.queryset.calls == [
        ("filter", {"tenant_id": "tenant-1"}),
        ("filter", {"resource_type": "api_calls"}),
        ("order_by", ("-recorded_at",)),
    ]


def test_subscription_and_usage_perform_create_require_authenticated_tenant(monkeypatch):
    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: None)

    with pytest.raises(PermissionDenied):
        _view(api.SubscriptionViewSet).perform_create(SimpleNamespace())
    with pytest.raises(PermissionDenied):
        _view(api.UsageRecordViewSet).perform_create(SimpleNamespace())

    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: "tenant-1")
    saved = {}
    api.UsageRecordViewSet().request = SimpleNamespace(user=SimpleNamespace())
    usage_view = _view(api.UsageRecordViewSet)
    usage_view.perform_create(SimpleNamespace(save=lambda **kwargs: saved.update(kwargs)))
    assert saved == {"tenant_id": "tenant-1"}


def test_subscription_actions_validate_plan_and_delegate_to_service(monkeypatch):
    subscription = SimpleNamespace(tenant_id="tenant-1")
    service_calls = []

    class Service:
        def create_subscription(self, tenant_id, plan_id):
            service_calls.append(("create", tenant_id, plan_id))
            return SimpleNamespace(id="sub-created")

        def cancel_subscription(self, tenant_id, reason):
            service_calls.append(("cancel", tenant_id, reason))
            return SimpleNamespace(id="sub-cancelled")

        def upgrade_subscription(self, tenant_id, plan_id):
            service_calls.append(("upgrade", tenant_id, plan_id))
            return SimpleNamespace(id="sub-upgraded")

    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: "tenant-1")
    monkeypatch.setattr(api, "SubscriptionService", Service)

    serializer = SimpleNamespace(validated_data={"plan": SimpleNamespace(id="plan-1")}, instance=None)
    view = _view(api.SubscriptionViewSet)
    view.perform_create(serializer)
    assert serializer.instance.id == "sub-created"

    view.get_object = lambda: subscription
    view.get_serializer = lambda instance: SimpleNamespace(data={"id": instance.id})

    view.request = SimpleNamespace(data={"reason": "operator request"})
    cancel = view.cancel(view.request)
    assert cancel.status_code == status.HTTP_200_OK
    assert cancel.data == {"id": "sub-cancelled"}

    missing_plan = view.upgrade(SimpleNamespace(data={}))
    assert missing_plan.status_code == status.HTTP_400_BAD_REQUEST
    assert missing_plan.data == {"error": "plan_id is required"}

    upgraded = view.upgrade(SimpleNamespace(data={"plan_id": "plan-2"}))
    assert upgraded.status_code == status.HTTP_200_OK
    assert upgraded.data == {"id": "sub-upgraded"}
    assert service_calls == [
        ("create", "tenant-1", "plan-1"),
        ("cancel", "tenant-1", "operator request"),
        ("upgrade", "tenant-1", "plan-2"),
    ]


def test_quota_list_uses_tenant_usage_and_rate_limit_service(monkeypatch):
    tenant = SimpleNamespace(max_users=25, max_storage_gb=100)
    usage = SimpleNamespace(active_users=7, storage_used_gb="12.50")

    class TenantQuery:
        def first(self):
            return tenant

    class TenantObjects:
        def filter(self, **kwargs):
            assert kwargs == {"id": "tenant-1"}
            return TenantQuery()

    class UsageObjects:
        def get_or_create(self, **kwargs):
            assert kwargs["tenant"] is tenant
            assert "date" in kwargs
            return usage, False

    monkeypatch.setattr(api, "get_user_tenant_id", lambda user: "tenant-1")
    monkeypatch.setattr(api.Tenant, "objects", TenantObjects())
    monkeypatch.setattr(api.TenantResourceUsage, "objects", UsageObjects())
    monkeypatch.setattr(api.RateLimitService, "get_usage", lambda tenant_id, resource: 123)
    monkeypatch.setattr(api.RateLimitService, "get_limit", lambda tenant_id, resource: 1000)

    response = api.QuotaViewSet().list(SimpleNamespace(user=SimpleNamespace()))

    assert response.status_code == status.HTTP_200_OK
    assert response.data == {
        "users": {"used": 7, "limit": 25},
        "storage": {"used": 12.5, "limit": 100},
        "api_calls": {"used": 123, "limit": 1000},
    }
