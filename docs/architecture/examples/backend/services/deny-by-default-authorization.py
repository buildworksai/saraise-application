# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Deny-by-Default Authorization via Policy Engine
# backend/src/modules/*/views.py
# Reference: docs/architecture/security-model.md § 1 (Deny by Default)
# Reference: docs/architecture/policy-engine-spec.md

from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from src.models.user import User

# ============================================================================
# ✅ CORRECT: Policy Engine evaluation (deny by default)
# ============================================================================

class PlatformUserViewSet(viewsets.ViewSet):
    """
    Get all users (platform_owner only, deny by default).
    
    Architecture:
    - Deny by default: If Policy Engine says no, access is denied
    - No implicit permissions - explicit Policy Engine evaluation required
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get all users (platform_owner only, deny by default)."""
        current_user = get_current_user_from_session(request)
        policy_engine = PolicyEngine()
        
        decision = policy_engine.evaluate(
            user_id=current_user.id,
            tenant_id=None,
            resource="platform.users",
            action="view",
            context={"resource_type": "platform_users"}
        )
        
        # Deny by default - if policy engine says no, access is denied
        if not decision.allowed:
            return Response(
                {"detail": f"Access denied: {decision.reason}"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Only reach here if Policy Engine explicitly allows
        users = User.objects.all()
        return Response([{"id": u.id, "email": u.email} for u in users])

# ============================================================================
# ❌ FORBIDDEN PATTERNS (DO NOT USE)
# ============================================================================

# ❌ FORBIDDEN: No authorization check (violates deny-by-default)
# This would allow anyone to access /admin/users without permission
# class BadUserViewSet(viewsets.ViewSet):
#     def list(self, request):
#         # SECURITY VIOLATION: No Policy Engine check
#         users = User.objects.all()
#         return Response([{"id": u.id, "email": u.email} for u in users])

# ❌ FORBIDDEN: Role check in route logic (use Policy Engine instead)
# class BadUserViewSet(viewsets.ViewSet):
#     def list(self, request):
#         current_user = get_current_user_from_session(request)
#         # VIOLATION: is_platform_owner not in session, roles not cached
#         if current_user.is_platform_owner:
#             users = User.objects.all()
#             return Response([{"id": u.id, "email": u.email} for u in users])
#         return Response(
#             {"detail": "Access denied"},
#             status=status.HTTP_403_FORBIDDEN
#         )

