# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Sensitive Operations Protection
# backend/src/modules/*/views.py
# Reference: docs/architecture/security-model.md § 4
# Reference: docs/architecture/policy-engine-spec.md

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from src.core.permissions import SessionAuthentication
from src.core.step_up_auth import StepUpAuthMixin
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from .services import TenantService


class SensitiveOperationsViewSet(StepUpAuthMixin, viewsets.ViewSet):
    """
    ViewSet for sensitive operations requiring step-up authentication.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation) + Step-up MFA
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.tenant_service = None
    
    def get_tenant_service(self):
        if not self.tenant_service:
            self.tenant_service = TenantService()
        return self.tenant_service
    
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
    
    @action(detail=True, methods=['delete'], url_path='admin/tenants/(?P<tenant_id>[^/.]+)')
    def delete_tenant(self, request, tenant_id=None):
        """
        Delete tenant (platform_owner only with step-up MFA).
        
        Sensitive operation protection:
        1. Verify session identity (authentication)
        2. Verify step-up MFA (additional assurance for sensitive operation)
        3. Policy Engine checks permission + role
        4. Execute destructive operation
        5. Audit log created
        """
        # Verify step-up MFA
        self.require_step_up_auth(request)
        
        # Policy Engine authorization
        user = get_current_user_from_session(request)
        self.check_policy(
            action="delete",
            resource="platform.tenants",
            context={
                "target_tenant_id": tenant_id,
                "step_up_verified": True,
                "sensitive_operation": True
            }
        )
        
        # Perform tenant deletion
        service = self.get_tenant_service()
        service.delete_tenant(tenant_id)
        
        return Response({"status": "deleted", "tenant_id": tenant_id}, status=status.HTTP_204_NO_CONTENT)
