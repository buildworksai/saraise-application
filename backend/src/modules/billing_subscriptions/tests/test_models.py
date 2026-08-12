"""Model tests for the concrete Billing Subscriptions domain."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import IntegrityError
from django.utils import timezone

from src.modules.billing_subscriptions.models import (
    Invoice,
    InvoiceLineItem,
    Payment,
    Subscription,
    SubscriptionPlan,
    UsageRecord,
)


@pytest.fixture
def tenant_id() -> str:
    return str(uuid4())


@pytest.fixture
def plan() -> SubscriptionPlan:
    return SubscriptionPlan.objects.create(
        name="Growth",
        description="Growth plan",
        price=Decimal("99.00"),
        billing_cycle="monthly",
        features=["billing", "usage"],
        limits={"max_users": 25},
    )


@pytest.fixture
def subscription(tenant_id: str, plan: SubscriptionPlan) -> Subscription:
    today = timezone.now().date()
    return Subscription.objects.create(
        tenant_id=tenant_id,
        plan=plan,
        status="active",
        start_date=today,
        end_date=today + timedelta(days=30),
    )


@pytest.mark.django_db
class TestBillingSubscriptionModels:
    """Test concrete model behavior instead of the abstract tenant base."""

    def test_subscription_plan_string_uses_name_and_billing_cycle(self, plan: SubscriptionPlan) -> None:
        assert str(plan) == "Growth (monthly)"
        assert plan.features == ["billing", "usage"]
        assert plan.limits == {"max_users": 25}

    def test_subscription_trial_and_active_state(self, tenant_id: str, plan: SubscriptionPlan) -> None:
        today = timezone.now().date()
        trial = Subscription.objects.create(
            tenant_id=tenant_id,
            plan=plan,
            status="trial",
            start_date=today,
            trial_start_date=today,
            trial_end_date=today + timedelta(days=14),
        )
        expired = Subscription.objects.create(
            tenant_id=uuid4(),
            plan=plan,
            status="active",
            start_date=today - timedelta(days=60),
            end_date=today - timedelta(days=1),
        )

        assert trial.is_trial is True
        assert trial.is_active is False
        assert expired.is_active is False

    def test_invoice_line_item_calculates_total_and_inherits_tenant(
        self,
        tenant_id: str,
        subscription: Subscription,
    ) -> None:
        invoice = Invoice.objects.create(
            tenant_id=tenant_id,
            subscription=subscription,
            invoice_number="INV-0001",
            amount=Decimal("100.00"),
            tax_amount=Decimal("10.00"),
            total_amount=Decimal("110.00"),
            due_date=timezone.now().date() + timedelta(days=15),
        )

        line_item = InvoiceLineItem.objects.create(
            invoice=invoice,
            description="Seat licenses",
            quantity=Decimal("2.00"),
            unit_price=Decimal("40.00"),
        )

        assert line_item.tenant_id == invoice.tenant_id
        assert line_item.total_price == Decimal("80.00")
        assert str(line_item) == "INV-0001 - Seat licenses"

    def test_payment_and_usage_record_are_tenant_scoped(
        self,
        tenant_id: str,
        subscription: Subscription,
    ) -> None:
        invoice = Invoice.objects.create(
            tenant_id=tenant_id,
            subscription=subscription,
            invoice_number="INV-0002",
            amount=Decimal("50.00"),
            tax_amount=Decimal("5.00"),
            total_amount=Decimal("55.00"),
            due_date=timezone.now().date() + timedelta(days=15),
        )
        payment = Payment.objects.create(
            tenant_id=tenant_id,
            invoice=invoice,
            amount=Decimal("55.00"),
            payment_method="stripe",
            status="completed",
        )
        usage = UsageRecord.objects.create(
            tenant_id=tenant_id,
            resource_type="api_calls",
            quantity=Decimal("125.0000"),
        )

        assert str(payment) == "Payment 55.00 - completed"
        assert payment.tenant_id == invoice.tenant_id
        assert usage.tenant_id == invoice.tenant_id
        assert str(usage).startswith("api_calls: 125.0000 at ")

    def test_tenant_scoped_model_rejects_missing_tenant(self, plan: SubscriptionPlan) -> None:
        with pytest.raises(IntegrityError):
            Subscription.objects.create(
                plan=plan,
                status="active",
                start_date=timezone.now().date(),
            )
