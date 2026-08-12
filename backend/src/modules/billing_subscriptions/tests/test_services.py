"""
Service unit tests for the Billing Subscriptions module.

These tests cover the current subscription service contract. The legacy
BillingSubscriptionsService resource scaffold was removed from the module model
set, so service tests must target the concrete subscription lifecycle.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.utils import timezone

from src.modules.billing_subscriptions.models import Subscription, SubscriptionPlan
from src.modules.billing_subscriptions.services import SubscriptionService


@pytest.fixture
def tenant_id() -> str:
    return str(uuid4())


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> SubscriptionService:
    subscription_service = SubscriptionService()
    monkeypatch.setattr(subscription_service, "_update_tenant_quotas", lambda _tenant_id, _plan: None)
    return subscription_service


@pytest.fixture
def monthly_plan() -> SubscriptionPlan:
    return SubscriptionPlan.objects.create(
        name="Monthly Growth",
        description="Monthly plan with trial",
        price=Decimal("99.00"),
        billing_cycle="monthly",
        features=["billing"],
        limits={"max_users": 10},
    )


@pytest.fixture
def yearly_plan() -> SubscriptionPlan:
    return SubscriptionPlan.objects.create(
        name="Yearly Scale",
        description="Annual plan without trial",
        price=Decimal("999.00"),
        billing_cycle="yearly",
        features=["billing", "automation"],
        limits={"max_users": 50},
    )


@pytest.mark.django_db
class TestSubscriptionService:
    """Test subscription lifecycle business logic."""

    def test_create_monthly_subscription_starts_trial(
        self,
        service: SubscriptionService,
        tenant_id: str,
        monthly_plan: SubscriptionPlan,
    ) -> None:
        subscription = service.create_subscription(tenant_id=tenant_id, plan_id=monthly_plan.id)

        today = timezone.now().date()
        assert subscription.id is not None
        assert str(subscription.tenant_id) == tenant_id
        assert subscription.plan == monthly_plan
        assert subscription.status == "trial"
        assert subscription.start_date == today
        assert subscription.trial_start_date == today
        assert subscription.trial_end_date == today + timedelta(days=14)

    def test_create_yearly_subscription_starts_active_without_trial(
        self,
        service: SubscriptionService,
        tenant_id: str,
        yearly_plan: SubscriptionPlan,
    ) -> None:
        subscription = service.create_subscription(tenant_id=tenant_id, plan_id=yearly_plan.id)

        assert subscription.status == "active"
        assert subscription.trial_start_date is None
        assert subscription.trial_end_date is None

    def test_create_subscription_rejects_inactive_plan(
        self,
        service: SubscriptionService,
        tenant_id: str,
        monthly_plan: SubscriptionPlan,
    ) -> None:
        monthly_plan.is_active = False
        monthly_plan.save(update_fields=["is_active"])

        with pytest.raises(ValueError, match="not found or inactive"):
            service.create_subscription(tenant_id=tenant_id, plan_id=monthly_plan.id)

    def test_upgrade_subscription_changes_plan_and_ends_trial(
        self,
        service: SubscriptionService,
        tenant_id: str,
        monthly_plan: SubscriptionPlan,
        yearly_plan: SubscriptionPlan,
    ) -> None:
        subscription = service.create_subscription(tenant_id=tenant_id, plan_id=monthly_plan.id)

        upgraded = service.upgrade_subscription(tenant_id=tenant_id, new_plan_id=yearly_plan.id)

        assert upgraded.id == subscription.id
        assert upgraded.plan == yearly_plan
        assert upgraded.status == "active"

    def test_upgrade_subscription_rejects_missing_active_subscription(
        self,
        service: SubscriptionService,
        tenant_id: str,
        yearly_plan: SubscriptionPlan,
    ) -> None:
        with pytest.raises(ValueError, match="No active subscription found"):
            service.upgrade_subscription(tenant_id=tenant_id, new_plan_id=yearly_plan.id)

    def test_cancel_subscription_records_reason(
        self,
        service: SubscriptionService,
        tenant_id: str,
        monthly_plan: SubscriptionPlan,
    ) -> None:
        service.create_subscription(tenant_id=tenant_id, plan_id=monthly_plan.id)

        cancelled = service.cancel_subscription(tenant_id=tenant_id, reason="tenant requested downgrade")

        assert cancelled.status == "cancelled"
        assert cancelled.cancelled_at is not None
        assert cancelled.cancellation_reason == "tenant requested downgrade"

    def test_calculate_proration_returns_remaining_cycle_value(
        self,
        service: SubscriptionService,
        tenant_id: str,
        monthly_plan: SubscriptionPlan,
        yearly_plan: SubscriptionPlan,
    ) -> None:
        today = timezone.now().date()
        subscription = Subscription.objects.create(
            tenant_id=tenant_id,
            plan=monthly_plan,
            status="active",
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=20),
        )

        amount = service._calculate_proration(subscription, yearly_plan)

        assert amount == Decimal("666.00")
