# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Subscription Management Service
# backend/src/modules/billing/services/subscription_service.py
# Reference: docs/architecture/policy-engine-spec.md
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Optional
from src.modules.billing.models import Subscription, SubscriptionStatus
from datetime import datetime, timedelta
import secrets

class SubscriptionService:
    """Subscription management (platform-level service).
    
    CRITICAL: Subscriptions are platform-level data with tenant_id for isolation.
    See docs/architecture/application-architecture.md § 2.1 (Row-Level Multitenancy).
    """
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Subscription.objects directly for all operations
        pass

    def create_subscription(
        self,
        tenant_id: str,
        plan_id: str,
        start_date: Optional[datetime] = None
    ) -> Subscription:
        """Create subscription for tenant"""
        # Get plan
        plan = self._get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")

        # Calculate period dates
        start = start_date or datetime.utcnow()
        end = start + timedelta(days=plan.billing_cycle_days)

        # Create subscription
        subscription = Subscription(
            id=f"sub_{secrets.token_urlsafe(16)}",
            tenant_id=tenant_id,
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE,
            start_date=start,
            current_period_start=start,
            current_period_end=end
        )

        # ✅ CORRECT: Django ORM - use instance.save()
        subscription.save()

        return subscription

    def update_subscription(
        self,
        subscription_id: str,
        plan_id: str
    ) -> Subscription:
        """Update subscription plan"""
        subscription = self.get_subscription(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")

        # Get new plan
        plan = self._get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")

        # Update subscription
        subscription.plan_id = plan_id
        subscription.current_period_end = subscription.current_period_start + timedelta(days=plan.billing_cycle_days)

        # ✅ CORRECT: Django ORM - use instance.save()
        subscription.save()

        return subscription

    def cancel_subscription(
        self,
        subscription_id: str,
        cancel_at_period_end: bool = True
    ) -> Subscription:
        """Cancel subscription"""
        subscription = self.get_subscription(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")

        if cancel_at_period_end:
            subscription.cancel_at_period_end = True
        else:
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.end_date = datetime.utcnow()

        # ✅ CORRECT: Django ORM - use instance.save()
        subscription.save()

        return subscription

    def get_subscription(self, subscription_id: str) -> Optional[Subscription]:
        """Get subscription by ID"""
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        return Subscription.objects.filter(id=subscription_id).first()

    def get_tenant_subscription(self, tenant_id: str) -> Optional[Subscription]:
        """Get tenant subscription (platform-level query)

        NOTE: Subscriptions are platform-level data, so tenant_id filtering is appropriate here.
        This is different from business data which uses schema-per-tenant isolation.
        """
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        return Subscription.objects.filter(
            tenant_id=tenant_id,
            status=SubscriptionStatus.ACTIVE
        ).order_by('-created_at').first()

    def _get_plan(self, plan_id: str):
        """Helper to get plan"""
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        from src.modules.billing.models import SubscriptionPlan
        return SubscriptionPlan.objects.filter(id=plan_id).first()

