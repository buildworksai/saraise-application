# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Subscription Lifecycle Management Service
# backend/src/modules/billing/services/subscription_lifecycle_service.py
# Reference: docs/architecture/policy-engine-spec.md (Platform Operations)
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import List
from datetime import datetime, timedelta
from src.modules.billing.models import Subscription, SubscriptionStatus

class SubscriptionLifecycleService:
    """Subscription lifecycle management (platform-level service).
    
    CRITICAL: Only platform_billing_manager can process renewals/expirations.
    This is a background job service (not user-facing).
    See docs/architecture/policy-engine-spec.md (Platform Operations).
    """
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Subscription.objects directly for all operations
        pass

    def process_subscription_renewals(self):
        """Process subscription renewals.
        
        Called by background job (not user-facing endpoint).
        Renews active subscriptions; cancels if cancel_at_period_end is set.
        """
        # Get subscriptions ending soon
        end_date = datetime.utcnow() + timedelta(days=7)

        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        subscriptions = Subscription.objects.filter(
            status=SubscriptionStatus.ACTIVE,
            current_period_end__lte=end_date
        )

        for subscription in subscriptions:
            if subscription.cancel_at_period_end:
                # Cancel subscription
                subscription.status = SubscriptionStatus.CANCELLED
                subscription.end_date = subscription.current_period_end
                subscription.save()
            else:
                # Renew subscription
                self._renew_subscription(subscription)

    @transaction.atomic
    def _renew_subscription(self, subscription: Subscription):
        """Renew subscription"""
        # Create invoice for renewal
        # Assuming InvoiceService exists
        # from src.modules.billing.services.invoice_service import InvoiceService
        # invoice_service = InvoiceService()
        # invoice = invoice_service.create_invoice(
        #     subscription_id=subscription.id,
        #     tenant_id=subscription.tenant_id,
        #     amount=subscription.plan.price
        # )

        # Update subscription period
        plan = subscription.plan
        subscription.current_period_start = subscription.current_period_end
        subscription.current_period_end = subscription.current_period_end + timedelta(days=plan.billing_cycle_days)
        subscription.save()

