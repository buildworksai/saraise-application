# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Plan Change Service with Proration
# backend/src/modules/billing/services/plan_change_service.py
# Reference: docs/architecture/policy-engine-spec.md § 4
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Optional
from decimal import Decimal
from datetime import datetime
from src.modules.billing.services.subscription_service import SubscriptionService
from src.modules.billing.services.invoice_service import InvoiceService
from src.modules.billing.services.usage_tracking_service import UsageTrackingService
from src.modules.billing.models import Subscription, SubscriptionPlan
from src.core.errors import ValidationError

class PlanChangeService:
    """Plan change service with proration support.
    
    CRITICAL: Plan changes require tenant_admin authorization (Policy Engine).
    Proration calculates partial month charges/credits.
    See docs/architecture/policy-engine-spec.md § 4 (Runtime Evaluation).
    """
    
    def __init__(self, tenant_id: str):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        self.tenant_id = tenant_id
        self.subscription_service = SubscriptionService()
        self.invoice_service = InvoiceService(tenant_id=tenant_id)

    def upgrade_plan(
        self,
        subscription_id: str,
        new_plan_id: str,
        prorate: bool = True
    ) -> Subscription:
        """Upgrade subscription plan.
        
        Requires Policy Engine authorization (tenant_admin or platform_billing_manager).
        Calculates proration if enabled.
        """
        subscription = self.subscription_service.get_subscription(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")

        old_plan = subscription.plan
        new_plan = self._get_plan(new_plan_id)
        if not new_plan:
            raise ValueError(f"Plan {new_plan_id} not found")

        # Calculate prorated amount if needed
        if prorate:
            prorated_amount = self._calculate_prorated_amount(
                subscription,
                old_plan,
                new_plan
            )

            if prorated_amount > 0:
                # Create invoice for prorated amount
                self.invoice_service.create_invoice(
                    subscription_id=subscription_id,
                    tenant_id=subscription.tenant_id,
                    amount=prorated_amount,
                    description=f"Plan upgrade proration: {old_plan.name} → {new_plan.name}"
                )

        # Update subscription
        subscription = self.subscription_service.update_subscription(
            subscription_id,
            new_plan_id
        )

        return subscription

    def downgrade_plan(
        self,
        subscription_id: str,
        new_plan_id: str
    ) -> Subscription:
        """Downgrade subscription plan"""
        subscription = self.subscription_service.get_subscription(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")

        # Check if downgrade is allowed
        if not self._can_downgrade(subscription, new_plan_id):
            raise ValidationError("Downgrade not allowed - current usage exceeds new plan limits")

        # Update subscription (downgrade takes effect at period end)
        subscription = self.subscription_service.update_subscription(
            subscription_id,
            new_plan_id
        )

        return subscription

    def _calculate_prorated_amount(
        self,
        subscription: Subscription,
        old_plan: SubscriptionPlan,
        new_plan: SubscriptionPlan
    ) -> Decimal:
        """Calculate prorated amount for plan change"""
        # Calculate remaining days in current period
        remaining_days = (subscription.current_period_end - datetime.utcnow()).days

        # Calculate daily rates
        old_daily_rate = old_plan.price / old_plan.billing_cycle_days
        new_daily_rate = new_plan.price / new_plan.billing_cycle_days

        # Calculate prorated amount
        old_remaining = old_daily_rate * remaining_days
        new_remaining = new_daily_rate * remaining_days

        prorated_amount = new_remaining - old_remaining

        return max(prorated_amount, Decimal(0))

    def _can_downgrade(self, subscription: Subscription, new_plan_id: str) -> bool:
        """Check if downgrade is allowed"""
        new_plan = self._get_plan(new_plan_id)
        if not new_plan:
            return False

        # Get tenant usage
        # ✅ CORRECT: Django ORM - no database session needed
        usage_service = UsageTrackingService(subscription.tenant_id)
        usage = usage_service.get_current_usage(subscription.tenant_id)

        # Check if usage exceeds new plan limits
        if usage.get("users", 0) > new_plan.max_users:
            return False

        if usage.get("storage_gb", 0) > new_plan.max_storage_gb:
            return False

        return True

    def _get_plan(self, plan_id: str) -> Optional[SubscriptionPlan]:
        """Helper to get plan"""
        from src.modules.billing.services.plan_service import PlanService
        # ✅ CORRECT: Django ORM - no database session needed
        service = PlanService()
        return service.get_plan(plan_id)

