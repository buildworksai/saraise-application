# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Tenant Subscription Management Service
# backend/src/modules/subscriptions/services/tenant_subscription_service.py
# Reference: docs/architecture/policy-engine-spec.md § 4
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Optional
from src.modules.subscriptions.services.subscription_service import SubscriptionService
from src.modules.tenant_management.models import Tenant

class TenantSubscriptionService:
    """Tenant-scoped subscription management.
    
    CRITICAL: Subscriptions are scoped by tenant_id.
    Authorization checked by Policy Engine (required: tenant_admin or platform_owner).
    """
    
    def __init__(self, tenant_id: str):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        self.tenant_id = tenant_id
        self.subscription_service = SubscriptionService()

    def _get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID"""
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM
        return Tenant.objects.filter(id=tenant_id).first()

    @transaction.atomic
    def update_tenant_subscription(
        self,
        tenant_id: str,
        plan_id: str
    ) -> Tenant:
        """Update tenant subscription"""
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        # Update subscription
        subscription = self.subscription_service.update_subscription(
            subscription_id=tenant.subscription_id,
            plan_id=plan_id
        )

        # Update tenant quota
        tenant.max_users = subscription.plan.max_users
        tenant.save()
        return tenant

