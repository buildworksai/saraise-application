"""Tests for Entitlement Service.

Task: 503.1 - Subscription Entitlements & Runtime Gating
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from ..entitlement_models import EntitlementCheck, PlanEntitlement, SubscriptionPlan, TenantSubscription
from ..entitlement_service import EntitlementError, EntitlementService


@pytest.mark.django_db
class TestEntitlementService:
    """Test EntitlementService."""

    def test_get_tenant_subscription(self) -> None:
        """Test getting tenant subscription."""
        service = EntitlementService()

        # Create plan
        plan = SubscriptionPlan.objects.create(
            name="basic",
            description="Basic Plan",
            plan_type="basic",
            is_active=True,
        )

        # Create subscription
        tenant_id = "tenant-1"
        TenantSubscription.objects.create(
            tenant_id=tenant_id,
            plan=plan,
            status="active",
            started_at=timezone.now(),
        )

        result = service.get_tenant_subscription(tenant_id)

        assert result is not None
        assert result.tenant_id == tenant_id
        assert result.plan == plan

    def test_get_tenant_subscription_not_found(self) -> None:
        """Test getting non-existent subscription returns None."""
        service = EntitlementService()

        result = service.get_tenant_subscription("non-existent")
        assert result is None

    def test_check_module_access(self) -> None:
        """Test checking module access."""
        service = EntitlementService()

        # Create plan with module entitlement
        plan = SubscriptionPlan.objects.create(
            name="basic",
            description="Basic Plan",
            plan_type="basic",
            is_active=True,
        )

        PlanEntitlement.objects.create(
            plan=plan,
            entitlement_type="module_access",
            resource_name="test-module",
            limit_value=1,
        )

        tenant_id = "tenant-1"
        TenantSubscription.objects.create(
            tenant_id=tenant_id,
            plan=plan,
            status="active",
            started_at=timezone.now(),
        )

        has_access = service.check_module_access(tenant_id, "test-module")
        assert has_access is True

    def test_check_module_access_no_entitlement(self) -> None:
        """Test checking module access without entitlement."""
        service = EntitlementService()

        plan = SubscriptionPlan.objects.create(
            name="basic",
            description="Basic Plan",
            plan_type="basic",
            is_active=True,
        )

        tenant_id = "tenant-1"
        TenantSubscription.objects.create(
            tenant_id=tenant_id,
            plan=plan,
            status="active",
            started_at=timezone.now(),
        )

        has_access = service.check_module_access(tenant_id, "premium-module")
        assert has_access is False

    def test_check_feature_access(self) -> None:
        """Test checking feature access."""
        service = EntitlementService()

        plan = SubscriptionPlan.objects.create(
            name="basic",
            description="Basic Plan",
            plan_type="basic",
            is_active=True,
        )

        PlanEntitlement.objects.create(
            plan=plan,
            entitlement_type="feature_access",
            resource_name="advanced-reports",
            limit_value=1,
        )

        tenant_id = "tenant-1"
        TenantSubscription.objects.create(
            tenant_id=tenant_id,
            plan=plan,
            status="active",
            started_at=timezone.now(),
        )

        has_access = service.check_feature_access(tenant_id, "advanced-reports")
        assert has_access is True

    def test_check_resource_limit(self) -> None:
        """Test checking resource limit."""
        service = EntitlementService()

        plan = SubscriptionPlan.objects.create(
            name="basic",
            description="Basic Plan",
            plan_type="basic",
            is_active=True,
        )

        PlanEntitlement.objects.create(
            plan=plan,
            entitlement_type="resource_limit",
            resource_name="api_calls_per_month",
            limit_value=10000,
        )

        tenant_id = "tenant-1"
        TenantSubscription.objects.create(
            tenant_id=tenant_id,
            plan=plan,
            status="active",
            started_at=timezone.now(),
        )

        within_limit = service.check_resource_limit(tenant_id, "api_calls_per_month", 5000)
        assert within_limit is True

        exceeds_limit = service.check_resource_limit(tenant_id, "api_calls_per_month", 15000)
        assert exceeds_limit is False

    def test_create_subscription(self) -> None:
        """Test creating a subscription."""
        service = EntitlementService()

        plan = SubscriptionPlan.objects.create(
            name="basic",
            description="Basic Plan",
            plan_type="basic",
            is_active=True,
        )

        tenant_id = "tenant-1"
        subscription = service.create_subscription(
            tenant_id=tenant_id,
            plan_id=plan.id,
        )

        assert subscription is not None
        assert subscription.tenant_id == tenant_id
        assert subscription.plan == plan
        assert subscription.status == "active"

    def test_create_subscription_invalid_plan(self) -> None:
        """Test creating subscription with invalid plan fails."""
        service = EntitlementService()

        with pytest.raises(EntitlementError, match="not found"):
            service.create_subscription(
                tenant_id="tenant-1",
                plan_id="non-existent-plan-id",
            )

    def test_log_entitlement_check(self) -> None:
        """Test logging entitlement check."""
        service = EntitlementService()

        tenant_id = "tenant-1"
        service.log_entitlement_check(
            tenant_id=tenant_id,
            entitlement_type="module",
            resource_name="test-module",
            granted=True,
            reason="Plan includes module",
        )

        check = EntitlementCheck.objects.filter(tenant_id=tenant_id, entitlement_type="module").first()

        assert check is not None
        assert check.resource_name == "test-module"
        assert check.granted is True
