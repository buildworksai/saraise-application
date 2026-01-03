# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Step-Up Authentication for Sensitive Operations
# backend/src/core/step_up_auth.py
# Reference: docs/architecture/security-model.md § 4 (Sensitive Operations)
# Reference: docs/architecture/policy-engine-spec.md

from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.permissions import IsAuthenticated
from src.core.permissions import SessionAuthentication
from src.core.step_up_manager import StepUpManager
from src.core.auth import get_current_user_from_session


class StepUpAuthMixin:
    """
    Mixin for ViewSets that require step-up MFA verification for sensitive operations.
    
    Step-up auth provides additional authentication assurance for
    high-risk operations like tenant deletion, permission changes, etc.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.step_up_manager = StepUpManager()
    
    def require_step_up_auth(self, request: Request) -> bool:
        """
        Require step-up MFA verification for sensitive operations.
        
        Returns:
            bool: True if step-up auth verified
            
        Raises:
            PermissionDenied: If MFA code is missing or invalid
        """
        user = get_current_user_from_session(request)
        
        # Priority 1: Check header
        mfa_code = request.headers.get("X-MFA-Code")
        
        # Priority 2: Check JSON body
        if not mfa_code:
            try:
                body = request.data
                mfa_code = body.get("mfa_code")
            except:
                pass
        
        if not mfa_code:
            raise PermissionDenied(
                detail="MFA verification required. Provide code in X-MFA-Code header or mfa_code field.",
                code="MFA_REQUIRED"
            )
        
        # Verify TOTP code
        if not self.step_up_manager.verify_totp(user.id, mfa_code):
            raise PermissionDenied(
                detail="Invalid or expired MFA code",
                code="MFA_INVALID"
            )
        
        # Create step-up token for this request (proves MFA was just done)
        step_up_token = self.step_up_manager.create_step_up_token(user.id)
        request.step_up_token = step_up_token
        
        return True

# ✅ CORRECT: Step-up auth with Policy Engine
# Example usage in ViewSet:
#
# class TenantViewSet(StepUpAuthMixin, viewsets.ViewSet):
#     def destroy(self, request, pk=None, *args, **kwargs):
#         """Delete tenant (platform operation with step-up auth)."""
#         # Verify step-up MFA
#         self.require_step_up_auth(request)
#         
#         # Policy Engine authorization
#         user = get_current_user_from_session(request)
#         policy_engine = PolicyEngine()
#         decision = policy_engine.evaluate(
#             user_id=user.id,
#             tenant_id=None,
#             resource="platform.tenants",
#             action="delete",
#             context={
#                 "target_tenant_id": pk,
#                 "step_up_verified": True,
#                 "resource_type": "tenant"
#             }
#         )
#         
#         if not decision.allowed:
#             raise PermissionDenied(detail=decision.reason)
#         
#         # Perform deletion
#         tenant_service.delete_tenant(pk)
#         
#         # Audit log created by audit middleware
#         return Response({"status": "deleted", "tenant_id": pk}, status=status.HTTP_204_NO_CONTENT)
