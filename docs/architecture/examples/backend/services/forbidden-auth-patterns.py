# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Forbidden authentication patterns
# backend/src/modules/*/views.py
# Reference: docs/architecture/security-model.md § 2 (AuthN vs AuthZ)
# Reference: docs/architecture/policy-engine-spec.md

from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from src.models.user import User
from src.models.user_data import UserData

# ============================================================================
# ❌ FORBIDDEN PATTERNS (DO NOT USE)
# ============================================================================

# ❌ FORBIDDEN: No authorization check (anyone can access)
# class SensitiveDataViewSet(viewsets.ViewSet):
#     def list(self, request):
#         # SECURITY VIOLATION: No Policy Engine check
#         return Response({"data": "anyone can access"})

# ❌ FORBIDDEN: Custom decorators (breaks architecture)
# from functools import wraps
# def require_custom_role(role):
#     def decorator(func):
#         @wraps(func)
#         def wrapper(*args, **kwargs):
#             # VIOLATION: Bypasses Policy Engine
#             return func(*args, **kwargs)
#         return wrapper
#     return decorator

# ❌ FORBIDDEN: Role checks in route logic (roles not in session)
# class DataViewSet(viewsets.ViewSet):
#     def list(self, request):
#         current_user = get_current_user_from_session(request)
#         # VIOLATION: is_admin not in session, roles not cached
#         if current_user.is_admin:
#             return Response({"data": "admin_data"})
#         return Response({"data": "user_data"})

# ❌ FORBIDDEN: Using old decorators (implied session caching)
# from src.core.auth_decorators import RequirePlatformOwner  # DEPRECATED
# class AdminDataViewSet(viewsets.ViewSet):
#     @RequirePlatformOwner  # VIOLATION: Implies session-cached roles
#     def list(self, request):
#         return Response({"data": "admin_data"})

# ============================================================================
# ✅ CORRECT PATTERNS (USE THESE)
# ============================================================================

class SensitiveDataViewSet(viewsets.ViewSet):
    """
    Get sensitive admin data (platform_owner only).
    
    ✅ CORRECT: Uses Policy Engine evaluation per request.
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get sensitive admin data (platform_owner only)."""
        current_user = get_current_user_from_session(request)
        policy_engine = PolicyEngine()
        
        decision = policy_engine.evaluate(
            user_id=current_user.id,
            tenant_id=None,
            resource="platform.sensitive_data",
            action="view",
            context={"resource_type": "sensitive_data"}
        )
        
        if not decision.allowed:
            return Response(
                {"detail": decision.reason},
                status=status.HTTP_403_FORBIDDEN
            )
        
        return Response({"data": "sensitive admin data"})


class UserDataViewSet(viewsets.ViewSet):
    """
    Get user data (tenant_user or higher).
    
    ✅ CORRECT: Uses Policy Engine + explicit tenant_id filtering.
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get user data (tenant_user or higher)."""
        current_user = get_current_user_from_session(request)
        policy_engine = PolicyEngine()
        
        decision = policy_engine.evaluate(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            resource="tenant.data",
            action="view",
            context={"resource_type": "user_data"}
        )
        
        if not decision.allowed:
            return Response(
                {"detail": decision.reason},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # CRITICAL: Explicit tenant_id filtering (Row-Level Multitenancy)
        user_data = UserData.objects.filter(tenant_id=current_user.tenant_id)
        return Response([{"id": d.id} for d in user_data])
