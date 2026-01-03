# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Database Operations with Row-Level Multitenancy
# backend/src/services/example.py
# Reference: docs/architecture/security-model.md § 2.1 (Row-Level Multitenancy)
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Optional
from src.models.user import User

def get_user_by_id(user_id: str, tenant_id: str) -> Optional[User]:
    """Get user with explicit tenant_id filtering.
    
    CRITICAL: All tenant-scoped queries MUST filter by tenant_id.
    See docs/architecture/security-model.md § 2.1.
    """
    # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
    return User.objects.filter(id=user_id, tenant_id=tenant_id).first()

@transaction.atomic
def create_user(user_data: dict, tenant_id: str) -> User:
    """Create user with explicit tenant_id assignment.
    
    CRITICAL: Must set tenant_id on creation for Row-Level Multitenancy.
    """
    # ✅ CORRECT: Django ORM - use Model.objects.create() instead of db.add()/commit()
    user = User.objects.create(**user_data, tenant_id=tenant_id)
    return user

