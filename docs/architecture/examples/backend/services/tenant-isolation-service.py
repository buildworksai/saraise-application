# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Tenant Isolation Service (Row-Level Multitenancy)
# backend/src/core/tenant_service.py
# Reference: docs/architecture/application-architecture.md § 2.1
# Reference: docs/architecture/security-model.md § 2
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Optional
from src.models.tenant import Tenant

class TenantIsolationService:
    """
    Tenant isolation enforcement via Row-Level Multitenancy.
    
    CRITICAL PATTERN:
    - All tenant-scoped tables have tenant_id column
    - All queries MUST filter by tenant_id explicitly
    - No schema context / search_path isolation
    - Authorization decisions made by Policy Engine per request
    """
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        pass

    def validate_tenant_active(self, tenant_id: int) -> bool:
        """Validate tenant is active (platform-level check)."""
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM
        tenant = Tenant.objects.filter(id=tenant_id).first()
        
        if not tenant or not tenant.is_active:
            return False
        return True

    def ensure_tenant_context(self, user_id: int) -> Optional[int]:
        """
        Get current user's tenant_id for query filtering.
        
        USAGE:
        tenant_id = tenant_service.ensure_tenant_context(current_user.id)
        records = Record.objects.filter(
            tenant_id=tenant_id  # Explicit filtering
        )
        """
        from src.models.user import User
        
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM
        user = User.objects.filter(id=user_id).first()
        
        if not user:
            return None
        
        return user.tenant_id

# ✅ CORRECT: Query pattern with explicit tenant_id filtering
# from src.core.tenant_service import TenantIsolationService
#
# def get_tenant_records(
#     current_user: User,
#     db: Session,
#     tenant_service: TenantIsolationService
# ):
#     """Get records for current user's tenant."""
#     # CRITICAL: Always filter by current_user.tenant_id
#     records = Model.objects.filter(Record).filter(
#         Record.tenant_id == current_user.tenant_id
#     ).all()
#     return records

# ❌ FORBIDDEN: Schema context pattern (no longer used)
# self.# Django QuerySet instead
        f"SET search_path TO {tenant.schema_name}, public")
# This pattern violated Row-Level Multitenancy requirements in approved architecture

