# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Tenant User Management Service
# backend/src/modules/*/services.py
# Reference: docs/architecture/application-architecture.md § 2.1
# Reference: docs/architecture/security-model.md
# CRITICAL: SARAISE uses Django ORM exclusively
# - Use Model.objects for queries (no database session needed)
# - Use @transaction.atomic for transactions

from django.db import transaction
from typing import List, Optional
from src.models.user import User
from src.models.user_quota import UserQuota

class TenantUserService:
    """
    Tenant user management service.
    
    CRITICAL: All operations use explicit tenant_id filtering
    for Row-Level Multitenancy data isolation.
    """
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use User.objects directly for all operations
        pass

    def create_tenant_user(
        self,
        tenant_id: int,
        user_data: dict
    ) -> User:
        """
        Create user for tenant.
        
        CRITICAL: Set tenant_id explicitly for Row-Level Multitenancy.
        """
        # Check user quota for tenant
        # ✅ CORRECT: Django ORM - use Model.objects.filter()
        quota = UserQuota.objects.filter(
            tenant_id=tenant_id
        ).first()
        
        if quota and quota.current_user_count >= quota.max_users:
            raise ValueError(f"User quota exceeded for tenant {tenant_id}")
        
        # Create user with explicit tenant_id
        user = User(
            **user_data,
            tenant_id=tenant_id  # CRITICAL: Explicit tenant isolation
        )
        
        # ✅ CORRECT: Django ORM - use instance.save()
        user.save()
        
        # Increment user count
        if quota:
            quota.current_user_count += 1
            # ✅ CORRECT: Django ORM - use instance.save()
            quota.save()
        
        return user

    def get_tenant_user(
        self,
        tenant_id: int,
        user_id: int
    ) -> Optional[User]:
        """
        Get user for tenant.
        
        CRITICAL: Filter by tenant_id explicitly (Row-Level Multitenancy).
        """
        # ✅ CORRECT: Django ORM - use Model.objects.filter()
        user = User.objects.filter(
            id=user_id,
            tenant_id=tenant_id  # CRITICAL: Tenant filter
        ).first()
        
        if not user:
            raise ValueError(f"User {user_id} not found in tenant {tenant_id}")
        
        return user

    def list_tenant_users(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> List[User]:
        """
        List users for tenant.
        
        CRITICAL: Filter by tenant_id explicitly (Row-Level Multitenancy).
        """
        # ✅ CORRECT: Django ORM - use Model.objects.filter() with slicing
        users = User.objects.filter(
            tenant_id=tenant_id  # CRITICAL: Tenant filter
        )[skip:skip+limit]
        
        return list(users)

    def update_tenant_user(
        self,
        tenant_id: int,
        user_id: int,
        user_data: dict
    ) -> User:
        """
        Update user in tenant.
        
        CRITICAL: Query uses tenant_id to prevent cross-tenant access.
        """
        # ✅ CORRECT: Django ORM - use Model.objects.filter()
        user = User.objects.filter(
            id=user_id,
            tenant_id=tenant_id  # CRITICAL: Tenant filter
        ).first()
        
        if not user:
            raise ValueError(f"User {user_id} not found in tenant {tenant_id}")
        
        for key, value in user_data.items():
            if key != "tenant_id":  # CRITICAL: Never allow tenant_id change
                setattr(user, key, value)
        
        # ✅ CORRECT: Django ORM - use instance.save()
        user.save()
        return user

    def delete_tenant_user(
        self,
        tenant_id: int,
        user_id: int
    ) -> bool:
        """
        Delete user from tenant.
        
        CRITICAL: Filter by tenant_id to prevent cross-tenant deletion.
        """
        # ✅ CORRECT: Django ORM - use Model.objects.filter()
        user = User.objects.filter(
            id=user_id,
            tenant_id=tenant_id  # CRITICAL: Tenant filter
        ).first()
        
        if not user:
            raise ValueError(f"User {user_id} not found in tenant {tenant_id}")
        
        # ✅ CORRECT: Django ORM - use instance.delete()
        user.delete()
        
        return True
