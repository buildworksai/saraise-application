"""
Tenant Isolation Tests for BillingSubscriptions module.

CRITICAL: These tests verify that tenants cannot access each other's data.
This is the PRIMARY security mechanism for multi-tenant isolation.

Reference: saraise-documentation/rules/compliance-enforcement.md
Rule: ALL tenant-scoped queries MUST filter by tenant_id
"""
import uuid
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from ..models import Invoice, Payment, Subscription, SubscriptionPlan, UsageRecord
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
class TestSubscriptionTenantIsolation:
    """Tenant isolation tests for Subscription model."""

    def test_user_cannot_list_other_tenant_subscriptions(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's subscriptions in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create plan
        plan = SubscriptionPlan.objects.create(
            name="Test Plan",
            price=100.00,
            billing_cycle="monthly",
        )

        # Create subscription for tenant A
        subscription_a = Subscription.objects.create(
            tenant_id=tenant_a_id,
            plan=plan,
            status="active",
            start_date=timezone.now().date(),
        )

        # Create subscription for tenant B
        subscription_b = Subscription.objects.create(
            tenant_id=tenant_b_id,
            plan=plan,
            status="active",
            start_date=timezone.now().date(),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/billing-subscriptions/subscriptions/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        subscription_ids = [s["id"] for s in data]

        # User A should see tenant A's subscription, but NOT tenant B's subscription
        assert subscription_a.id in subscription_ids
        assert subscription_b.id not in subscription_ids

    def test_user_cannot_get_other_tenant_subscription_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's subscription by ID (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create plan
        plan = SubscriptionPlan.objects.create(
            name="Test Plan",
            price=100.00,
            billing_cycle="monthly",
        )

        # Create subscription for tenant B
        subscription_b = Subscription.objects.create(
            tenant_id=tenant_b_id,
            plan=plan,
            status="active",
            start_date=timezone.now().date(),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's subscription
        response = api_client.get(f"/api/v1/billing-subscriptions/subscriptions/{subscription_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestInvoiceTenantIsolation:
    """Tenant isolation tests for Invoice model."""

    def test_user_cannot_list_other_tenant_invoices(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's invoices in list."""
        from decimal import Decimal

        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create invoices
        invoice_a = Invoice.objects.create(
            tenant_id=tenant_a_id,
            invoice_number="INV-A-001",
            amount=Decimal("100.00"),
            tax_amount=Decimal("10.00"),
            total_amount=Decimal("110.00"),
            due_date=timezone.now().date(),
        )

        invoice_b = Invoice.objects.create(
            tenant_id=tenant_b_id,
            invoice_number="INV-B-001",
            amount=Decimal("200.00"),
            tax_amount=Decimal("20.00"),
            total_amount=Decimal("220.00"),
            due_date=timezone.now().date(),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/billing-subscriptions/invoices/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        invoice_ids = [i["id"] for i in data]

        # User A should see tenant A's invoice, but NOT tenant B's invoice
        assert invoice_a.id in invoice_ids
        assert invoice_b.id not in invoice_ids


@pytest.mark.django_db
class TestPaymentTenantIsolation:
    """Tenant isolation tests for Payment model."""

    def test_user_cannot_list_other_tenant_payments(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's payments in list."""
        from decimal import Decimal

        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create invoices
        invoice_a = Invoice.objects.create(
            tenant_id=tenant_a_id,
            invoice_number="INV-A-001",
            amount=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            due_date=timezone.now().date(),
        )

        invoice_b = Invoice.objects.create(
            tenant_id=tenant_b_id,
            invoice_number="INV-B-001",
            amount=Decimal("200.00"),
            total_amount=Decimal("200.00"),
            due_date=timezone.now().date(),
        )

        # Create payments
        payment_a = Payment.objects.create(
            tenant_id=tenant_a_id,
            invoice=invoice_a,
            amount=Decimal("100.00"),
            payment_method="credit_card",
            status="completed",
        )

        payment_b = Payment.objects.create(
            tenant_id=tenant_b_id,
            invoice=invoice_b,
            amount=Decimal("200.00"),
            payment_method="credit_card",
            status="completed",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/billing-subscriptions/payments/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        payment_ids = [p["id"] for p in data]

        # User A should see tenant A's payment, but NOT tenant B's payment
        assert payment_a.id in payment_ids
        assert payment_b.id not in payment_ids


@pytest.mark.django_db
class TestUsageRecordTenantIsolation:
    """Tenant isolation tests for UsageRecord model."""

    def test_user_cannot_list_other_tenant_usage_records(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's usage records in list."""
        from decimal import Decimal

        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create usage records
        usage_a = UsageRecord.objects.create(
            tenant_id=tenant_a_id,
            resource_type="api_calls",
            quantity=Decimal("1000.00"),
        )

        usage_b = UsageRecord.objects.create(
            tenant_id=tenant_b_id,
            resource_type="api_calls",
            quantity=Decimal("2000.00"),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/billing-subscriptions/usage-records/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        usage_ids = [u["id"] for u in data]

        # User A should see tenant A's usage, but NOT tenant B's usage
        assert usage_a.id in usage_ids
        assert usage_b.id not in usage_ids
