# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: SoD Validation in Role Assignment
# backend/src/core/role_assignment_service.py
# Reference: docs/architecture/policy-engine-spec.md § 8 (Segregation of Duties)

from django.db import transaction
from src.core.role_assignment_service import RoleAssignmentService
from src.core.policy_engine import PolicyEngine

class AuthorizationError(Exception):
    """Authorization validation error"""
    pass

# SoD validation is automatic in assign_role()
# Example usage:

def assign_role_with_sod_check(
    policy_engine: PolicyEngine,
    user_id: str,
    tenant_id: str,
    role_name: str
):
    # ✅ CORRECT: Django ORM - no database session needed
    # Use Model.objects directly for all operations
    """Assign role with SoD validation.
    
    Segregation of Duties (SoD) is validated against user's existing roles.
    Conflicting roles are rejected.
    
    Reference: docs/architecture/policy-engine-spec.md § 8
    """
    role_assignment_service = RoleAssignmentService(tenant_id=tenant_id)
    
    try:
        # assign_role() automatically validates SoD constraints
        user_role = role_assignment_service.assign_role(
            user_id=user_id,
            role_name=role_name,
            validate_sod=True  # Default: True
        )
        
        # Log role assignment for audit trail
        policy_engine.log_action(
            user_id=user_id,
            tenant_id=tenant_id,
            action="role.assign",
            resource=f"users.{user_id}.roles",
            result="success",
            context={"role_name": role_name}
        )
        
        return user_role
        
    except AuthorizationError as e:
        # SoD violation detected
        # Error: "SoD violation: Role 'invoice_approver' conflicts with existing role 'invoice_creator'"
        # See docs/architecture/policy-engine-spec.md § 8 for SoD rules
        
        # Log failed attempt for audit trail
        policy_engine.log_action(
            user_id=user_id,
            tenant_id=tenant_id,
            action="role.assign",
            resource=f"users.{user_id}.roles",
            result="failure",
            context={
                "role_name": role_name,
                "reason": str(e),
                "violation_type": "segregation_of_duties"
            }
        )
        
        raise AuthorizationError(
            f"Cannot assign role '{role_name}': {str(e)}"
        )

