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

    def test_calculate_proration_returns_zero_when_no_end_date(
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
            start_date=today,
            end_date=None,
        )

        amount = service._calculate_proration(subscription, yearly_plan)

        assert amount == Decimal("0.00")

    def test_calculate_proration_returns_zero_when_cycle_length_not_positive(
        self,
        service: SubscriptionService,
        tenant_id: str,
        monthly_plan: SubscriptionPlan,
        yearly_plan: SubscriptionPlan,
    ) -> None:
        today = timezone.now().date()
        # start_date == end_date produces a zero-length billing cycle.
        subscription = Subscription.objects.create(
            tenant_id=tenant_id,
            plan=monthly_plan,
            status="active",
            start_date=today,
            end_date=today,
        )

        amount = service._calculate_proration(subscription, yearly_plan)

        assert amount == Decimal("0.00")

    def test_calculate_proration_uses_exact_ratio_not_rounded(
        self,
        service: SubscriptionService,
        tenant_id: str,
        monthly_plan: SubscriptionPlan,
    ) -> None:
        """Boundary check: ratio must be days_remaining / days_in_cycle, not swapped or off-by-one."""
        today = timezone.now().date()
        plan = SubscriptionPlan.objects.create(
            name="Odd Price Plan",
            description="Non power-of-two price to defeat coincidental bitwise mutants",
            price=Decimal("101.00"),
            billing_cycle="monthly",
            features=[],
            limits={},
        )
        subscription = Subscription.objects.create(
            tenant_id=tenant_id,
            plan=monthly_plan,
            status="active",
            start_date=today - timedelta(days=3),
            end_date=today + timedelta(days=7),
        )
        # days_in_cycle = 10, days_remaining = 7 -> ratio 0.7
        amount = service._calculate_proration(subscription, plan)

        assert amount == Decimal("70.700")

    def test_calculate_proration_returns_zero_for_negative_cycle_length(
        self,
        service: SubscriptionService,
        tenant_id: str,
        monthly_plan: SubscriptionPlan,
        yearly_plan: SubscriptionPlan,
    ) -> None:
        """Boundary check: a negative days_in_cycle (end_date before start_date, a data
        anomaly) must still yield zero, not a division result -- this defeats a
        `days_in_cycle > 0` -> `days_in_cycle != 0` mutant, which would let negative
        values fall through into the division branch.
        """
        today = timezone.now().date()
        subscription = Subscription.objects.create(
            tenant_id=tenant_id,
            plan=monthly_plan,
            status="active",
            start_date=today,
            end_date=today - timedelta(days=5),
        )

        amount = service._calculate_proration(subscription, yearly_plan)

        assert amount == Decimal("0.00")

    def test_calculate_proration_computes_ratio_at_single_day_cycle_boundary(
        self,
        service: SubscriptionService,
        tenant_id: str,
        monthly_plan: SubscriptionPlan,
    ) -> None:
        """Boundary check: a 1-day billing cycle (days_in_cycle == 1) must still enter
        the division branch and compute the full price -- this defeats a
        `days_in_cycle > 0` -> `days_in_cycle > 1` mutant, which would wrongly return
        zero at this exact boundary.
        """
        today = timezone.now().date()
        plan = SubscriptionPlan.objects.create(
            name="Single Day Cycle Plan",
            description="Plan used purely to prove the 1-day cycle boundary",
            price=Decimal("50.00"),
            billing_cycle="monthly",
            features=[],
            limits={},
        )
        subscription = Subscription.objects.create(
            tenant_id=tenant_id,
            plan=monthly_plan,
            status="active",
            start_date=today,
            end_date=today + timedelta(days=1),
        )

        amount = service._calculate_proration(subscription, plan)

        assert amount == Decimal("50.00")

    def test_upgrade_subscription_rejects_inactive_new_plan(
        self,
        service: SubscriptionService,
        tenant_id: str,
        monthly_plan: SubscriptionPlan,
        yearly_plan: SubscriptionPlan,
    ) -> None:
        service.create_subscription(tenant_id=tenant_id, plan_id=monthly_plan.id)
        yearly_plan.is_active = False
        yearly_plan.save(update_fields=["is_active"])

        with pytest.raises(ValueError, match="not found or inactive"):
            service.upgrade_subscription(tenant_id=tenant_id, new_plan_id=yearly_plan.id)

    def test_upgrade_subscription_keeps_active_status_when_not_on_trial(
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
            start_date=today,
        )

        upgraded = service.upgrade_subscription(tenant_id=tenant_id, new_plan_id=yearly_plan.id)

        assert upgraded.id == subscription.id
        assert upgraded.status == "active"

    def test_cancel_subscription_rejects_missing_active_subscription(
        self,
        service: SubscriptionService,
        tenant_id: str,
    ) -> None:
        with pytest.raises(ValueError, match="No active subscription found"):
            service.cancel_subscription(tenant_id=tenant_id, reason="no subscription exists")

    def test_create_subscription_rejects_unknown_plan_id(
        self,
        service: SubscriptionService,
        tenant_id: str,
    ) -> None:
        with pytest.raises(ValueError, match="not found or inactive"):
            service.create_subscription(tenant_id=tenant_id, plan_id=str(uuid4()))

    def test_create_subscription_no_trial_for_billing_cycle_lexically_before_monthly(
        self,
        service: SubscriptionService,
        tenant_id: str,
    ) -> None:
        """Boundary check: the trial gate is an exact string equality against "monthly",
        not a lexical ordering. A billing_cycle that sorts before "monthly" (e.g. "annual")
        must NOT start a trial -- this defeats a `==` -> `<=` mutant on that comparison.
        """
        plan = SubscriptionPlan.objects.create(
            name="Annual Odd Cycle Plan",
            description="Non-standard billing_cycle value sorting before 'monthly'",
            price=Decimal("42.00"),
            billing_cycle="annual",
            features=[],
            limits={},
        )

        subscription = service.create_subscription(tenant_id=tenant_id, plan_id=plan.id)

        assert subscription.status == "active"
        assert subscription.trial_start_date is None
        assert subscription.trial_end_date is None

    def test_upgrade_subscription_requires_exact_trial_match_not_lexical_order(
        self,
        monkeypatch: pytest.MonkeyPatch,
        service: SubscriptionService,
        tenant_id: str,
        yearly_plan: SubscriptionPlan,
    ) -> None:
        """Boundary check: the trial-clearing branch in upgrade_subscription compares
        subscription.status == "trial" by exact equality. Values that sort lexically
        above or below "trial" (but are not equal to it) must leave status untouched --
        this defeats `==` -> `>=`, `==` -> `<=`, and `==` -> `is not` mutants.
        """
        import types

        for probe_status, expect_touched in (
            ("trial2", False),  # "trial2" > "trial": would wrongly satisfy `>=` and `is not`
            ("aaaa", False),  # "aaaa" < "trial": would wrongly satisfy `<=`
        ):
            fake_subscription = types.SimpleNamespace(
                id="fake-subscription-id",
                status=probe_status,
                plan=None,
                end_date=None,
                save=lambda: None,
            )
            fake_queryset = types.SimpleNamespace(first=lambda: fake_subscription)
            monkeypatch.setattr(
                "src.modules.billing_subscriptions.services.Subscription.objects.filter",
                lambda *_args, **_kwargs: fake_queryset,
            )

            result = service.upgrade_subscription(tenant_id=tenant_id, new_plan_id=yearly_plan.id)

            assert result is fake_subscription
            if expect_touched:
                assert fake_subscription.status == "active"
            else:
                # Status must remain exactly as fetched -- proves the branch requires
                # true equality to "trial", not a lexical ordering or identity check.
                assert fake_subscription.status == probe_status


@pytest.mark.django_db
class TestUpdateTenantQuotas:
    """Test _update_tenant_quotas business logic in isolation from create/upgrade flows."""

    def test_updates_all_limits_and_plan_reference_when_present(self, tenant_id: str) -> None:
        from src.modules.tenant_management.models import Tenant

        tenant = Tenant.objects.create(
            name="Quota Tenant",
            slug=f"quota-tenant-{uuid4().hex[:8]}",
            max_users=1,
            max_storage_gb=1,
            max_api_calls_per_day=1,
        )
        # Use the real Tenant id as our billing tenant_id for this call.
        plan = SubscriptionPlan.objects.create(
            name="Full Limits Plan",
            description="Plan specifying every quota limit",
            price=Decimal("50.00"),
            billing_cycle="monthly",
            features=[],
            limits={"max_users": 25, "max_storage_gb": 100, "max_api_calls_per_day": 5000},
        )

        service = SubscriptionService()
        service._update_tenant_quotas(str(tenant.id), plan)

        tenant.refresh_from_db()
        assert tenant.max_users == 25
        assert tenant.max_storage_gb == 100
        assert tenant.max_api_calls_per_day == 5000
        assert tenant.subscription_plan_id == plan.id

    def test_leaves_limits_untouched_when_plan_limits_key_absent(self, tenant_id: str) -> None:
        from src.modules.tenant_management.models import Tenant

        tenant = Tenant.objects.create(
            name="Partial Quota Tenant",
            slug=f"partial-quota-tenant-{uuid4().hex[:8]}",
            max_users=7,
            max_storage_gb=8,
            max_api_calls_per_day=9,
        )
        plan = SubscriptionPlan.objects.create(
            name="No Limits Plan",
            description="Plan without any limits configured",
            price=Decimal("10.00"),
            billing_cycle="monthly",
            features=[],
            limits={},
        )

        service = SubscriptionService()
        service._update_tenant_quotas(str(tenant.id), plan)

        tenant.refresh_from_db()
        # Untouched fields must retain their original values exactly.
        assert tenant.max_users == 7
        assert tenant.max_storage_gb == 8
        assert tenant.max_api_calls_per_day == 9
        assert tenant.subscription_plan_id == plan.id

    def test_updates_only_specified_limit_keys(self, tenant_id: str) -> None:
        from src.modules.tenant_management.models import Tenant

        tenant = Tenant.objects.create(
            name="Single Limit Tenant",
            slug=f"single-limit-tenant-{uuid4().hex[:8]}",
            max_users=2,
            max_storage_gb=3,
            max_api_calls_per_day=4,
        )
        plan = SubscriptionPlan.objects.create(
            name="Storage Only Plan",
            description="Plan that only overrides storage",
            price=Decimal("15.00"),
            billing_cycle="monthly",
            features=[],
            limits={"max_storage_gb": 42},
        )

        service = SubscriptionService()
        service._update_tenant_quotas(str(tenant.id), plan)

        tenant.refresh_from_db()
        assert tenant.max_users == 2
        assert tenant.max_storage_gb == 42
        assert tenant.max_api_calls_per_day == 4

    def test_handles_none_limits_gracefully(self, tenant_id: str) -> None:
        from src.modules.tenant_management.models import Tenant

        tenant = Tenant.objects.create(
            name="None Limits Tenant",
            slug=f"none-limits-tenant-{uuid4().hex[:8]}",
        )
        plan = SubscriptionPlan.objects.create(
            name="Null Limits Plan",
            description="Plan with limits explicitly None",
            price=Decimal("5.00"),
            billing_cycle="monthly",
            features=[],
            limits={},
        )
        # The DB column is NOT NULL, but the service defends against an in-memory
        # None value (`plan.limits or {}`) -- exercise that branch directly.
        plan.limits = None

        service = SubscriptionService()
        # Must not raise despite limits being None.
        service._update_tenant_quotas(str(tenant.id), plan)

        tenant.refresh_from_db()
        assert tenant.subscription_plan_id == plan.id

    def test_logs_error_and_does_not_raise_when_tenant_missing(
        self, tenant_id: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        plan = SubscriptionPlan.objects.create(
            name="Orphan Plan",
            description="Plan applied to a nonexistent tenant",
            price=Decimal("20.00"),
            billing_cycle="monthly",
            features=[],
            limits={"max_users": 5},
        )

        service = SubscriptionService()
        missing_tenant_id = str(uuid4())

        with caplog.at_level("ERROR"):
            # Must not raise -- DoesNotExist is caught and logged.
            service._update_tenant_quotas(missing_tenant_id, plan)

        assert any(missing_tenant_id in record.message and "not found" in record.message for record in caplog.records)

    def test_logs_error_and_does_not_raise_on_unexpected_save_failure(
        self,
        tenant_id: str,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from src.modules.tenant_management.models import Tenant

        tenant = Tenant.objects.create(
            name="Failing Save Tenant",
            slug=f"failing-save-tenant-{uuid4().hex[:8]}",
        )
        plan = SubscriptionPlan.objects.create(
            name="Failure Plan",
            description="Plan whose quota update save fails unexpectedly",
            price=Decimal("30.00"),
            billing_cycle="monthly",
            features=[],
            limits={"max_users": 3},
        )

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(Tenant, "save", _boom)

        service = SubscriptionService()
        with caplog.at_level("ERROR"):
            # Must not raise -- generic Exception is caught and logged.
            service._update_tenant_quotas(str(tenant.id), plan)

        assert any("Failed to update tenant quotas" in record.message for record in caplog.records)

    def test_create_subscription_integration_propagates_quotas_to_real_tenant(
        self,
        tenant_id: str,
        monthly_plan: SubscriptionPlan,
    ) -> None:
        """End-to-end: create_subscription (unmocked _update_tenant_quotas) updates the real tenant."""
        from src.modules.tenant_management.models import Tenant

        tenant = Tenant.objects.create(
            name="Integration Tenant",
            slug=f"integration-tenant-{uuid4().hex[:8]}",
            max_users=1,
        )
        monthly_plan.limits = {"max_users": 99}
        monthly_plan.save(update_fields=["limits"])

        service = SubscriptionService()
        service.create_subscription(tenant_id=str(tenant.id), plan_id=monthly_plan.id)

        tenant.refresh_from_db()
        assert tenant.max_users == 99
        assert tenant.subscription_plan_id == monthly_plan.id
