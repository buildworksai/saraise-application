# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Module Service Integration Pattern
# backend/src/modules/module_name/services.py
# Reference: docs/architecture/module-framework.md § 4 (Module Services)
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from src.modules.billing.services import BillingService
from src.modules.subscriptions.services import SubscriptionService
from src.core.errors import ValidationError
from typing import Dict, Any

class ModuleService:
    """Cross-module service integration with tenant isolation.
    
    CRITICAL: Injected services MUST be initialized with tenant_id.
    All operations are tenant-scoped and explicitly filtered.
    See docs/architecture/module-framework.md § 4.
    """
    
    def __init__(self, tenant_id: str):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        self.tenant_id = tenant_id
        self.billing_service = BillingService(tenant_id)
        self.subscription_service = SubscriptionService()

    def create_item_with_billing(self, item_data: Dict[str, Any]):
        """Create item with billing integration"""
        # Check subscription
        subscription = self.subscription_service.get_tenant_subscription(self.tenant_id)
        if not subscription or not subscription.is_active:
            raise ValidationError("Active subscription required")

        # Create item
        item = self.create_item(item_data)

        # Record usage
        self.billing_service.record_usage(
            tenant_id=self.tenant_id,
            resource="module_name.items",
            quantity=1
        )

        return item

    def create_item(self, item_data: Dict[str, Any]):
        """Create item (placeholder)"""
        # Implementation would create item in database
        pass

