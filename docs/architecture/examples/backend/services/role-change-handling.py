# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Role Change Handling with Session Invalidation
# backend/src/core/role_change_handler.py
# Reference: docs/architecture/security-model.md § 2.4
#            docs/architecture/policy-engine-spec.md

from typing import List

def update_user_roles(
    user_id: str,
    new_roles: List[str],
    db,  # Django ORM Session
    audit_service,
    session_manager,
):
    """Update user roles and invalidate sessions.
    
    CRITICAL: When roles change, ALL user sessions must be invalidated.
    Policy Engine will re-evaluate authorization on next request.
    Sessions contain identity only (no roles cached).
    
    See docs/architecture/security-model.md § 2.4 (Hard Invariant).
    """
    
    # 1. Update roles in database
    role_service.update_user_roles(user_id, new_roles)

    # 2. Invalidate ALL user sessions (force re-login to sync authorization state)
    # Sessions contain identity only; Policy Engine evaluates authorization per-request
    session_manager.invalidate_user_sessions(user_id)

    # 3. Audit log the role change with SoD validation
    audit_service.log_role_change(
        user_id=user_id,
        old_roles=old_roles,
        new_roles=new_roles,
    )

