# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Role hierarchy via Policy Engine
# backend/src/modules/*/views.py
# Reference: docs/architecture/policy-engine-spec.md § 4
# Reference: docs/architecture/security-model.md § 3.2

from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from src.models.tenant import Tenant
from src.models.workflow import Workflow

# ============================================================================
# Platform-Level Operations with Role Hierarchy
# ============================================================================

class PlatformTenantViewSet(viewsets.ViewSet):
    """
    Create tenant (platform_owner only).
    Role hierarchy: platform_owner has all permissions.
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def create(self, request):
        """Create tenant (platform_owner only)."""
        current_user = get_current_user_from_session(request)
        policy_engine = PolicyEngine()
        
        decision = policy_engine.evaluate(
            user_id=current_user.id,
            tenant_id=None,
            resource="platform.tenants",
            action="create",
            context={"resource_type": "platform_tenants"}
        )
        
        if not decision.allowed:
            return Response(
                {"detail": decision.reason},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Create tenant logic (implementation depends on Tenant model)
        # tenant = Tenant.objects.create(...)
        return Response({"status": "created"}, status=status.HTTP_201_CREATED)


class PlatformAuditLogViewSet(viewsets.ViewSet):
    """
    Get audit logs (platform_auditor, platform_owner via inheritance).
    Policy Engine evaluates role hierarchy at request time.
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get audit logs (platform_auditor, platform_owner via inheritance)."""
        current_user = get_current_user_from_session(request)
        policy_engine = PolicyEngine()
        
        decision = policy_engine.evaluate(
            user_id=current_user.id,
            tenant_id=None,
            resource="platform.audit_logs",
            action="view",
            context={"resource_type": "platform_audit"}
        )
        
        if not decision.allowed:
            return Response(
                {"detail": decision.reason},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Fetch audit logs (implementation depends on audit log model)
        return Response({"logs": []})

# ============================================================================
# Tenant-Level Operations with Role Hierarchy
# ============================================================================

class TenantWorkflowViewSet(viewsets.ViewSet):
    """
    List workflows in tenant.
    Policy Engine checks: permission "workflows:view" + role hierarchy.
    tenant_admin inherits tenant_viewer permissions.
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """List workflows in tenant."""
        current_user = get_current_user_from_session(request)
        policy_engine = PolicyEngine()
        
        decision = policy_engine.evaluate(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            resource="tenant.workflows",
            action="view",
            context={"resource_type": "tenant_workflows"}
        )
        
        if not decision.allowed:
            return Response(
                {"detail": decision.reason},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # CRITICAL: Explicit tenant_id filtering (Row-Level Multitenancy)
        workflows = Workflow.objects.filter(tenant_id=current_user.tenant_id)
        return Response([{"id": w.id} for w in workflows])

