# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Audit Logging for Sensitive Operations
# backend/src/modules/audit/services.py
# Reference: docs/architecture/security-model.md § 4
# Reference: docs/architecture/policy-engine-spec.md § 5 (SoD)

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from rest_framework.request import Request
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session
from src.core.audit_service import AuditService
from .services import AuthService
from .models import User
from django.db import transaction


class AuditLoggingViewSet(viewsets.ViewSet):
    """
    ViewSet for sensitive operations requiring audit logging.
    
    Authentication: Session-based (SessionAuthentication)
    Authorization: Policy Engine (runtime evaluation)
    Multitenancy: Row-level filtering by tenant_id
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_engine = PolicyEngine()
        self.audit_service = AuditService()
        self.auth_service = None
    
    def get_auth_service(self):
        if not self.auth_service:
            self.auth_service = AuthService()
        return self.auth_service
    
    def check_policy(self, action: str, resource: str, context: dict = None) -> None:
        """Authorize via Policy Engine."""
        user = get_current_user_from_session(self.request)
        decision = self.policy_engine.evaluate(
            user_id=user.id,
            tenant_id=user.tenant_id,
            resource=resource,
            action=action,
            context=context or {}
        )
        if not decision.allowed:
            raise PermissionDenied(detail=decision.reason)
    
    @action(detail=True, methods=['patch'], url_path='roles')
    def update_user_roles(self, request, pk=None):
        """
        Update user roles within tenant.
        
        Architecture:
        1. Policy Engine authorization check
        2. SoD validation (Segregation of Duties)
        3. Role assignment
        4. Audit log created
        """
        user_id = pk
        role_update = request.data
        
        user = get_current_user_from_session(request)
        
        # Policy Engine authorization - check permission + role
        self.check_policy(
            action="update",
            resource="tenant.user_roles",
            context={
                "target_user_id": user_id,
                "new_roles": role_update.get("roles", []),
                "resource_type": "user_roles"
            }
        )
        
        # Verify target user is in same tenant
        try:
            target_user = User.objects.get(
                id=user_id,
                tenant_id=user.tenant_id  # CRITICAL: Tenant filter
            )
        except User.DoesNotExist:
            raise NotFound(detail="User not found in your tenant")
        
        # SoD validation - check for conflicting roles
        new_roles = role_update.get("roles", [])
        sod_violations = self.policy_engine.validate_segregation_of_duties(
            user_id=user_id,
            tenant_id=user.tenant_id,
            proposed_roles=new_roles
        )
        
        if sod_violations:
            raise ValidationError(
                detail=f"SoD violation: {', '.join(sod_violations)}"
            )
        
        # Assign new roles
        auth_service = self.get_auth_service()
        with transaction.atomic():
            for role_name in new_roles:
                auth_service.assign_role(
                    user_id=user_id,
                    role_name=role_name,
                    tenant_id=user.tenant_id,
                    validate_sod=True
                )
        
        # REQUIRED: Audit log for sensitive operation
        # Captures: who made change, what was changed, when, why (via metadata)
        self.audit_service.log_event(
            actor_sub=user.id,
            actor_email=user.email,
            tenant_id=user.tenant_id,
            resource="user_roles",
            action="update",
            result="success",
            metadata={
                "target_user_id": user_id,
                "new_roles": new_roles,
                "sod_validated": True
            },
            request=request
        )
        
        return Response({
            "status": "success",
            "user_id": user_id,
            "roles": new_roles
        })
