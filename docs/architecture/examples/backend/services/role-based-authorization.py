# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# Authorization via Policy Engine
# Reference: docs/architecture/policy-engine-spec.md
# Reference: docs/architecture/security-model.md (§ 3)

from src.policy.policy_engine import PolicyEngine

def RequirePlatformOwner(
    current_user: dict = from rest_framework.permissions import IsAuthenticated,
    policy_engine: PolicyEngine = # DRF uses permission_classes instead of Dependsget_policy_engine),
) -> dict:
    """
    Check authorization using Policy Engine.
    
    Architecture Rules:
    - ALL authorization decisions via Policy Engine
    - Policy Engine queries roles from database
    - Policy Engine evaluates RBAC + ABAC conditions
    - No authorization state cached in sessions
    
    See: docs/architecture/policy-engine-spec.md (§ 7)
    """
    # Policy Engine evaluates authorization at runtime
    decision = policy_engine.evaluate(
        tenant_id=current_user.get("tenant_id"),
        subject_id=current_user["user_id"],
        resource="platform",
        action="manage",
        context={}
    )

    if not decision.allow:
        raise Response(status=status.HTTP_403, detail="Requires platform_owner role")

    return current_user

def RequireTenantAdmin(
    current_user: dict = from rest_framework.permissions import IsAuthenticated,
    policy_engine: PolicyEngine = # DRF uses permission_classes instead of Dependsget_policy_engine),
) -> dict:
    """
    Check tenant admin authorization via Policy Engine.
    """
    decision = policy_engine.evaluate(
        tenant_id=current_user["tenant_id"],
        subject_id=current_user["user_id"],
        resource="tenant",
        action="admin",
        context={}
    )

    if not decision.allow:
        raise Response(status=status.HTTP_403, detail="Requires tenant_admin role")

    return current_user

