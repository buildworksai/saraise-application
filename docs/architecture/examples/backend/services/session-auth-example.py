# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Session-based authentication with Policy Engine authorization
# backend/src/modules/*/views.py
# Reference: docs/architecture/authentication-and-session-management-spec.md
# Reference: docs/architecture/policy-engine-spec.md
# Reference: docs/architecture/security-model.md § 2.4

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from src.models.user import User
from src.models.tenant_data import TenantData

# ============================================================================
# Platform-Level Operations (tenant_id=None)
# ============================================================================

class PlatformUserViewSet(viewsets.ViewSet):
    """
    Platform-level user management (platform_owner only).
    
    Architecture:
    - Session provides ONLY identity (user_id, email, tenant_id, timestamps)
    - Policy Engine evaluates: permission "users:manage" + platform_owner role
    - No role caching in session - authorization evaluated per request
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get all users across all tenants (platform operation)."""
        current_user = get_current_user_from_session(request)
        policy_engine = PolicyEngine()
        
        # Policy Engine authorization check
        decision = policy_engine.evaluate(
            user_id=current_user.id,
            tenant_id=None,  # Platform operation
            resource="platform.users",
            action="manage",
            context={"resource_type": "platform_users", "operation": "list_all"}
        )
        
        if not decision.allowed:
            return Response(
                {"detail": f"Access denied: {decision.reason}"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Authorization passed - fetch all users (platform-level query, no tenant filter)
        users = User.objects.all()
        return Response([{"id": u.id, "email": u.email} for u in users])


class PlatformAuditLogViewSet(viewsets.ViewSet):
    """
    Platform audit logs (auditor access).
    
    Architecture:
    - Policy Engine checks: permission "audit.logs:view" + platform_auditor role
    - Role hierarchy: platform_owner inherits platform_auditor permissions
    - Authorization decision made at request time, not cached
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get platform audit logs."""
        current_user = get_current_user_from_session(request)
        policy_engine = PolicyEngine()
        
        decision = policy_engine.evaluate(
            user_id=current_user.id,
            tenant_id=None,  # Platform operation
            resource="platform.audit_logs",
            action="view",
            context={"resource_type": "platform_audit", "log_type": "all"}
        )
        
        if not decision.allowed:
            return Response(
                {"detail": decision.reason},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Fetch platform audit logs (implementation depends on audit log model)
        return Response({"logs": []})

# ============================================================================
# Tenant-Level Operations (tenant_id=current_user.tenant_id)
# ============================================================================

class TenantUserViewSet(viewsets.ViewSet):
    """
    Tenant-level user management.
    
    Architecture:
    - Session provides identity only (includes tenant_id)
    - Policy Engine evaluates: permission "users:view" + tenant_admin role
    - CRITICAL: Explicit tenant_id filtering (Row-Level Multitenancy)
    - No schema context - use explicit WHERE tenant_id = ?
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get users within current tenant."""
        current_user = get_current_user_from_session(request)
        policy_engine = PolicyEngine()
        
        # Policy Engine authorization check
        decision = policy_engine.evaluate(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            resource="tenant.users",
            action="view",
            context={"resource_type": "tenant_users", "tenant_id": current_user.tenant_id}
        )
        
        if not decision.allowed:
            return Response(
                {"detail": decision.reason},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # CRITICAL: Explicit tenant_id filtering (Row-Level Multitenancy)
        users = User.objects.filter(tenant_id=current_user.tenant_id)
        return Response([{"id": u.id, "email": u.email} for u in users])


class TenantDataViewSet(viewsets.ViewSet):
    """
    Tenant data access.
    
    Architecture:
    - Policy Engine evaluates: permission "data:view" + tenant_user role
    - Explicit tenant_id filtering ensures data isolation
    - Session does NOT cache permissions - Policy Engine queries on each request
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get tenant data (requires tenant_user permission)."""
        current_user = get_current_user_from_session(request)
        policy_engine = PolicyEngine()
        
        decision = policy_engine.evaluate(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            resource="tenant.data",
            action="view",
            context={"resource_type": "tenant_data"}
        )
        
        if not decision.allowed:
            return Response(
                {"detail": decision.reason},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # CRITICAL: Explicit tenant_id filtering
        data = TenantData.objects.filter(tenant_id=current_user.tenant_id)
        return Response([{"id": d.id} for d in data])

# ============================================================================
# Architecture Notes
# ============================================================================
# 
# 1. Sessions establish identity ONLY:
#    - user_id, email, tenant_id, created_at, last_accessed_at
#    - NO roles, NO permissions, NO ABAC attributes cached
#
# 2. Policy Engine evaluates ALL authorization:
#    - Queries user's roles from database (can cache internally)
#    - Evaluates RBAC (role hierarchy) + ABAC (attributes) + SoD (conflicts)
#    - Returns allow/deny decision with reason
#
# 3. Row-Level Multitenancy:
#    - All tenant-scoped tables have tenant_id column
#    - ALL queries MUST filter by tenant_id explicitly
#    - No schema context / search_path isolation
#
# 4. No Decorators for Authorization:
#    - Do NOT use RequirePlatformOwner, RequireTenantAdmin, etc.
#    - Use get_current_user_from_session + explicit Policy Engine evaluation
#    - Decorators implied session-cached roles (incorrect pattern)
# 
# References:
# - authentication-and-session-management-spec.md § 2.1, § 2.4
# - policy-engine-spec.md § 1, § 4
# - security-model.md § 2.4 "Session Is NOT an Authorization Cache"
# - application-architecture.md § 2.1 "Row-Level Multitenancy"
# ============================================================================

