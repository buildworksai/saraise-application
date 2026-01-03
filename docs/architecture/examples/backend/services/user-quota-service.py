# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: User Quota Management Service
# backend/src/modules/tenant/services/user_quota_service.py
# Reference: docs/architecture/application-architecture.md § 2.1
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Optional
from src.modules.tenant_management.models import Tenant

class UserQuotaService:
    """User quota management (tenant-scoped).
    
    CRITICAL: User quotas are tenant-scoped with explicit tenant_id filtering.
    Row-Level Multitenancy ensures per-tenant quota isolation.
    See docs/architecture/application-architecture.md § 2.1.
    """
    
    def __init__(self, tenant_id: str):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Tenant.objects directly for all operations
        self.tenant_id = tenant_id

    def _get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID"""
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM
        return Tenant.objects.filter(id=tenant_id).first()

    def check_user_quota(self) -> tuple[bool, Optional[str]]:
        """Check if this tenant can add more users.
        
        CRITICAL: Quota check is scoped to tenant_id (passed in constructor).
        """
        tenant = self._get_tenant(self.tenant_id)
        if not tenant:
            return False, "Tenant not found"

        if tenant.current_users >= tenant.max_users:
            return False, f"User quota exceeded. Max users: {tenant.max_users}"

        return True, None

    @transaction.atomic
    def increment_user_count(self):
        """Increment this tenant's user count.
        
        CRITICAL: Scoped to tenant_id (passed in constructor).
        """
        tenant = self._get_tenant(self.tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {self.tenant_id} not found")

        tenant.current_users += 1
        tenant.save()

    @transaction.atomic
    def decrement_user_count(self, tenant_id: str):
        """Decrement tenant user count"""
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        if tenant.current_users > 0:
            tenant.current_users -= 1
            tenant.save()

    @transaction.atomic
    def update_user_quota(self, tenant_id: str, max_users: int):
        """Update tenant user quota"""
        tenant = self._get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        tenant.max_users = max_users
        tenant.save()
        return tenant
