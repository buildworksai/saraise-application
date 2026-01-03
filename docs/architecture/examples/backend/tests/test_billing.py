# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Billing Testing with Policy Engine
# backend/tests/modules/billing/test_billing.py
# Reference: docs/architecture/policy-engine-spec.md § 4

import pytest
from django.db import transaction
from src.modules.billing.services.subscription_service import SubscriptionService
from src.modules.billing.services.subscription_lifecycle_service import SubscriptionLifecycleService
from src.modules.billing.models import SubscriptionStatus
from src.core.policy_engine import PolicyEngine

@pytest.mark.django_db
def test_create_subscription(
    tenant_fixture,
    policy_engine: PolicyEngine
):
    # ✅ CORRECT: Django ORM - use Model.objects directly, no Session parameter needed
    """Test subscription creation via Policy Engine authorization.
    
    Only tenant admins can create subscriptions (Platform controls plans).
    """
    # Check authorization via Policy Engine
    decision = policy_engine.evaluate(
        user_id="tenant-admin-id",
        tenant_id=tenant_fixture.id,
        resource="billing.subscriptions",
        action="create",
        context={"plan_id": "plan-123"}
    )
    assert decision.allowed, "Tenant admin should be authorized"

    service = SubscriptionService(tenant_id=tenant_fixture.id)

    subscription = service.create_subscription(
        plan_id="plan-123"
    )

    assert subscription.id is not None
    assert subscription.tenant_id == tenant_fixture.id
    assert subscription.status == SubscriptionStatus.ACTIVE

@pytest.mark.django_db
def test_subscription_renewal(
    tenant_fixture
):
    # ✅ CORRECT: Django ORM - use Model.objects directly, no Session parameter needed
    """Test subscription renewal with explicit tenant_id filtering.
    
    Renewals are scoped to tenant (Row-Level Multitenancy).
    """
    lifecycle_service = SubscriptionLifecycleService(tenant_id=tenant_fixture.id)

    # Process renewal for this tenant only
    lifecycle_service.process_subscription_renewals()

    # Verify subscription renewed
    service = SubscriptionService()
    subscription = service.get_subscription(test_subscription.id)
    assert subscription.current_period_end > test_subscription.current_period_end

