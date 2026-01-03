# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Row-Level Multitenancy with Explicit tenant_id Filtering
# backend/src/modules/*/views.py
# Reference: docs/architecture/application-architecture.md § 2.1
# Reference: docs/architecture/security-model.md
# Reference: .agents/rules/13-row-level-multitenancy.md

from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from src.models.tenant_data import TenantData

# ============================================================================
# ✅ CORRECT: Row-Level Multitenancy with explicit tenant_id filtering
# ============================================================================

class TenantDataViewSet(viewsets.ViewSet):
    """
    Get tenant data with explicit tenant_id filtering.
    
    Architecture:
    - Session provides identity only (includes tenant_id)
    - Policy Engine evaluates authorization
    - CRITICAL: Explicit tenant_id filtering (NOT schema context)
    - All tenant-scoped tables have tenant_id column
    - Queries MUST filter by tenant_id
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get tenant data with explicit tenant_id filtering."""
        current_user = get_current_user_from_session(request)
        policy_engine = PolicyEngine()
        
        # Policy Engine authorization
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
        
        # CRITICAL: Explicit tenant_id filtering (Row-Level Multitenancy)
        # DO NOT rely on schema context - always filter explicitly
        data = TenantData.objects.filter(tenant_id=current_user.tenant_id)
        return Response([{"id": d.id} for d in data])

# ============================================================================
# ❌ FORBIDDEN: Manual tenant_id in URL path (contradicts Row-Level Multitenancy)
# ============================================================================

# ❌ FORBIDDEN: DO NOT accept tenant_id as path parameter - use current_user.tenant_id
# class BadTenantDataViewSet(viewsets.ViewSet):
#     def list(self, request, tenant_id: str):
#         # VIOLATION: Allows cross-tenant data access if checking is missed
#         # VIOLATION: User could pass different tenant_id than their own
#         data = TenantData.objects.filter(tenant_id=tenant_id)
#         return Response([{"id": d.id} for d in data])
# 
# ✅ CORRECT: Always use current_user.tenant_id from session
# class GoodTenantDataViewSet(viewsets.ViewSet):
#     def list(self, request):
#         current_user = get_current_user_from_session(request)
#         # CORRECT: Uses tenant_id from authenticated session
#         data = TenantData.objects.filter(tenant_id=current_user.tenant_id)
#         return Response([{"id": d.id} for d in data])

