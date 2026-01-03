# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Subscription Plan Service
# backend/src/modules/billing/services/plan_service.py
# Reference: docs/architecture/policy-engine-spec.md (Platform Operations)
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import List, Optional, Dict, Any
from decimal import Decimal
import secrets
from src.modules.billing.models import SubscriptionPlan

class PlanService:
    """Subscription plan management (platform-level service).
    
    CRITICAL: Only platform_billing_manager can create/update plans.
    Plans are platform-wide and shared across all tenants.
    Authorization is evaluated by Policy Engine at request time.
    See docs/architecture/policy-engine-spec.md § 4.
    """
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use SubscriptionPlan.objects directly for all operations
        pass

    def create_plan(
        self,
        name: str,
        tier: str,
        price: Decimal,
        features: Dict[str, Any],
        billing_cycle_days: int = 30
    ) -> SubscriptionPlan:
        """Create subscription plan.
        
        Requires platform_billing_manager authorization (Policy Engine evaluated per-request).
        """
        # ✅ CORRECT: Django ORM - use Model.objects.create() instead of db.add()/commit()
        plan = SubscriptionPlan.objects.create(
            id=f"plan_{secrets.token_urlsafe(16)}",
            name=name,
            tier=tier,
            price=price,
            features=features,
            billing_cycle_days=billing_cycle_days,
            max_users=features.get("max_users", 10),
            max_storage_gb=features.get("max_storage_gb", 10),
            max_api_calls_per_month=features.get("max_api_calls_per_month", 10000)
        )
        return plan

    def get_plan(self, plan_id: str) -> Optional[SubscriptionPlan]:
        """Get plan by ID"""
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        return SubscriptionPlan.objects.filter(id=plan_id).first()

    def list_plans(self, include_inactive: bool = False) -> List[SubscriptionPlan]:
        """List all plans"""
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        queryset = SubscriptionPlan.objects.all()

        if not include_inactive:
            queryset = queryset.filter(is_active=True)

        queryset = queryset.order_by('price')
        return list(queryset)

    @transaction.atomic
    def update_plan(self, plan_id: str, updates: Dict[str, Any]) -> SubscriptionPlan:
        """Update plan"""
        plan = self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")

        for key, value in updates.items():
            if hasattr(plan, key):
                setattr(plan, key, value)

        plan.save()
        return plan

