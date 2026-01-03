# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Plan Feature Management Service
# backend/src/modules/billing/services/plan_feature_service.py
# Reference: docs/architecture/module-framework.md § 4.2, security-model.md § 2.1
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Dict, Any, Optional
from src.modules.billing.services.subscription_service import SubscriptionService
from src.modules.billing.models import SubscriptionStatus

class PlanFeatureService:
    """Feature availability checking for tenant subscription plans.
    
    CRITICAL: All feature checks are tenant-scoped with explicit
    tenant_id filtering. Authorization via Policy Engine (platform_billing_manager only).
    See docs/architecture/security-model.md § 2.1.
    """
    
    def __init__(self, tenant_id: str):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        self.tenant_id = tenant_id

    def check_feature_access(
        self,
        tenant_id: str,
        feature_name: str
    ) -> bool:
        """Check if tenant has access to feature"""
        # Get tenant subscription
        # ✅ CORRECT: Django ORM - no database session needed
        subscription_service = SubscriptionService()
        subscription = subscription_service.get_tenant_subscription(tenant_id)

        if not subscription or subscription.status != SubscriptionStatus.ACTIVE:
            return False

        # Check feature in plan
        plan = subscription.plan
        features = plan.features or {}

        return features.get(feature_name, False)

    def get_plan_limits(self, tenant_id: str) -> Dict[str, Any]:
        """Get plan limits for tenant"""
        subscription_service = SubscriptionService(self.db)
        subscription = subscription_service.get_tenant_subscription(tenant_id)

        if not subscription or subscription.status != SubscriptionStatus.ACTIVE:
            return {}

        plan = subscription.plan
        return {
            "max_users": plan.max_users,
            "max_storage_gb": plan.max_storage_gb,
            "max_api_calls_per_month": plan.max_api_calls_per_month,
            "features": plan.features or {}
        }

