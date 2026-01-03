# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Role hierarchy via Policy Engine
# backend/src/modules/audit/views.py
# Reference: docs/architecture/policy-engine-spec.md § 4
# Reference: docs/architecture/security-model.md § 3.2

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session


class RoleHierarchyViewSet(viewsets.ViewSet):
    """
    ViewSet demonstrating role hierarchy via Policy Engine.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
    
    def check_policy(self, action: str, resource: str, context: dict = None) -> None:
        """Authorize via Policy Engine."""
        user = get_current_user_from_session(self.request)
        decision = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=None,  # Platform-level operation
            resource=resource,
            action=action,
            context=context or {}
        )
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    @action(detail=False, methods=['get'], url_path='logs')
    def get_audit_logs(self, request):
        """
        Get audit logs - requires platform_auditor permission.
        Role hierarchy: platform_owner inherits platform_auditor permissions.
        
        Session provides ONLY identity (user_id, tenant_id).
        Policy Engine evaluates authorization:
        1. Queries user's platform roles from database (platform_owner, platform_auditor, etc.)
        2. Evaluates role hierarchy (platform_owner inherits platform_auditor)
        3. Checks permission: "audit.logs:view"
        4. Returns allow/deny decision
        """
        self.check_policy(
            action="view",
            resource="audit.logs",
            context={"resource_type": "platform_audit_logs"}
        )
        
        # Authorization passed - fetch audit logs
        # In real implementation, this would query AuditLog model
        return Response({"logs": []})
