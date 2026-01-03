# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Metadata Permission Checker with Policy Engine
# backend/src/metadata/services/metadata_permission_checker.py
# Reference: docs/architecture/policy-engine-spec.md § 1 (Authorization as Runtime Decision)

from typing import Optional
from src.core.policy_engine import PolicyEngine

class MetadataPermissionChecker:
    def __init__(self, policy_engine: PolicyEngine):
        self.policy_engine = policy_engine
    
    def check_field_permission(
        self,
        user_id: str,
        tenant_id: str,
        entity_name: str,
        fieldname: str,
        action: str
    ) -> bool:
        """Check if user has permission to access field via Policy Engine.
        
        CRITICAL: Authorization evaluated by Policy Engine, NOT role lists.
        All decisions made at request time based on current RBAC + ABAC state.
        See docs/architecture/policy-engine-spec.md § 4.
        """
        decision = self.policy_engine.evaluate(
            user_id=user_id,
            tenant_id=tenant_id,
            resource=f"{entity_name}.fields",
            action=action,
            context={
                "entity_name": entity_name,
                "fieldname": fieldname,
                "resource_type": "field"
            }
        )
        return decision.allowed

