# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ REQUIRED: Plan testing
# backend/src/modules/billing/tests/test_plans.py
import pytest
from src.modules.billing.services.plan_service import PlanService
from src.modules.billing.services.plan_change_service import PlanChangeService
from decimal import Decimal

@pytest.mark.django_db
def test_create_plan(platform_billing_manager):
    """Test plan creation"""
    # ✅ CORRECT: Django ORM - use Model.objects directly, no Session parameter needed
    service = PlanService()

    plan = service.create_plan(
        name="Professional Plan",
        tier="professional",
        price=Decimal("99.00"),
        features={
            "max_users": 50,
            "max_storage_gb": 100,
            "max_api_calls_per_month": 100000
        }
    )

    assert plan.id is not None
    assert plan.name == "Professional Plan"
    assert plan.price == Decimal("99.00")
    assert plan.max_users == 50

@pytest.mark.django_db
def test_plan_upgrade(test_subscription):
    """Test plan upgrade"""
    # ✅ CORRECT: Django ORM - use Model.objects directly, no Session parameter needed
    change_service = PlanChangeService()

    # Upgrade plan
    subscription = change_service.upgrade_plan(
        subscription_id=test_subscription.id,
        new_plan_id="professional_plan_id",
        prorate=True
    )

    assert subscription.plan_id == "professional_plan_id"

